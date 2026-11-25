"""GET com cache em disco e backoff exponencial (429/5xx), compartilhado pelos coletores.

Toda resposta bruta fica salva em data/raw/<fonte>/, para a coleta ser
reproduzível e para uma nova execução não gastar cota de novo.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import requests

from ..config import RAW


class ErroAPI(RuntimeError):
    def __init__(self, status: int, corpo: Any):
        super().__init__(f"HTTP {status}: {str(corpo)[:300]}")
        self.status = status
        self.corpo = corpo


def _chave(url: str, params: dict[str, Any], segredos: set[str]) -> str:
    limpo = {k: v for k, v in sorted(params.items()) if k not in segredos}
    return hashlib.sha256(json.dumps([url, limpo], ensure_ascii=False).encode()).hexdigest()[:24]


def get_json(url: str, params: dict[str, Any], *, fonte: str, segredos: set[str],
             usar_cache: bool = True, tentativas: int = 6, espera_base: float = 2.0) -> dict:
    pasta: Path = RAW / fonte
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"{_chave(url, params, segredos)}.json"
    if usar_cache and arquivo.exists():
        return json.loads(arquivo.read_text(encoding="utf-8"))["resposta"]

    for tentativa in range(tentativas):
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code == 200:
            dados = resp.json()
            registro = {
                "url": url,
                "params": {k: v for k, v in params.items() if k not in segredos},
                "coletado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "resposta": dados,
            }
            arquivo.write_text(json.dumps(registro, ensure_ascii=False), encoding="utf-8")
            return dados
        if resp.status_code in (429, 500, 502, 503, 504) and tentativa < tentativas - 1:
            time.sleep(espera_base * 2 ** tentativa)
            continue
        try:
            corpo = resp.json()
        except ValueError:
            corpo = resp.text
        raise ErroAPI(resp.status_code, corpo)
    raise ErroAPI(-1, "tentativas esgotadas")
