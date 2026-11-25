"""Cliente do VLM local (Qwen3-VL via Ollama), com JSON garantido por schema e cache.

O Ollama aceita um JSON Schema no campo `format`, e a geração fica presa a esse
schema. Temperatura 0 e seed fixa deixam a resposta reproduzível. Cada resposta
fica em cache por (modelo, versão do prompt, conteúdo), então reprocessar sai de graça.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from pathlib import Path
from typing import TypeVar

import requests
from pydantic import BaseModel, ValidationError

from .config import CACHE

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODELO_PADRAO = os.getenv("VLM_MODEL", "qwen3-vl:8b-instruct")

M = TypeVar("M", bound=BaseModel)


def _rastreio():
    """Com STONE_TRACE=1 (as evals em tests/evals ligam), cada chamada vira um span `llm` do deepeval.
    Sem a variável, o deepeval nem é importado: a API e a demo ficam como estão."""
    if os.getenv("STONE_TRACE") != "1":
        return lambda f: f
    from deepeval.tracing import observe
    return observe(type="llm", model=MODELO_PADRAO)


def _b64(caminho: Path) -> str:
    return base64.b64encode(caminho.read_bytes()).decode()


def _chave(*partes: str) -> str:
    return hashlib.sha256("\x1f".join(partes).encode()).hexdigest()[:32]


@_rastreio()
def gerar_json(schema: type[M], sistema: str, prompt: str, imagens: list[Path] | None = None,
               modelo: str = MODELO_PADRAO, versao: str = "v1", usar_cache: bool = True,
               tentativas: int = 3, num_ctx: int = int(os.getenv("VLM_NUM_CTX", "4096")),
               num_predict: int = int(os.getenv("VLM_NUM_PREDICT", "1024")),
               temperatura: float = 0, seed: int = 42, opcoes: dict | None = None) -> tuple[M, dict]:
    """Chama o modelo e devolve (objeto validado, metadados com tempo e tokens).

    opcoes: opções extras do Ollama (ex.: repeat_penalty), que entram na chave do cache.
    temperatura/seed: o padrão (0, 42) é reproduzível. Revisões do agente usam um pouco de
    temperatura, senão o modelo devolve a versão anterior idêntica."""
    imagens = imagens or []
    hashes = [hashlib.sha256(p.read_bytes()).hexdigest() for p in imagens]
    # o padrão fica fora da chave, para o cache já gravado continuar valendo
    amostra = [] if (temperatura, seed) == (0, 42) else [f"t={temperatura};s={seed}"]
    if opcoes:
        amostra.append(json.dumps(opcoes, sort_keys=True))
    chave = _chave(modelo, versao, schema.__name__, sistema, prompt, *hashes, *amostra)
    arquivo = CACHE / "vlm" / f"{chave}.json"
    if usar_cache and arquivo.exists():
        salvo = json.loads(arquivo.read_text(encoding="utf-8"))
        return schema.model_validate(salvo["resposta"]), {**salvo["meta"], "cache": True}

    corpo = {
        "model": modelo,
        "messages": [{"role": "system", "content": sistema},
                     {"role": "user", "content": prompt, "images": [_b64(p) for p in imagens]}],
        "format": schema.model_json_schema(),
        "stream": False,
        # num_ctx igual em todas as chamadas: mudar o valor faz o Ollama recarregar o modelo (~10 s).
        # num_predict corta geração em loop (uma chamada sem limite levou 5m50s e saiu inválida).
        "options": {"temperature": temperatura, "seed": seed, "num_ctx": num_ctx, "num_predict": num_predict, **(opcoes or {})},
        "keep_alive": "30m",
    }
    erro: Exception | None = None
    for tentativa in range(tentativas):
        inicio = time.time()
        try:
            r = requests.post(f"{OLLAMA_URL}/api/chat", json=corpo, timeout=600)
            r.raise_for_status()
            dados = r.json()
            obj = schema.model_validate_json(dados["message"]["content"])
        except (requests.RequestException, ValidationError, KeyError) as e:
            erro = e
            time.sleep(2 * (tentativa + 1))
            continue
        meta = {"modelo": modelo, "versao": versao, "segundos": round(time.time() - inicio, 2),
                "tokens_entrada": dados.get("prompt_eval_count"), "tokens_saida": dados.get("eval_count"),
                "cache": False}
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(json.dumps({"resposta": obj.model_dump(mode="json"), "meta": meta},
                                      ensure_ascii=False), encoding="utf-8")
        return obj, meta
    raise RuntimeError(f"VLM falhou depois de {tentativas} tentativas: {erro}")
