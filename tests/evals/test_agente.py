"""Evals do agente de criativos (LangGraph + Qwen3-VL local), julgadas pelo Claude.

Rodar (precisa do Ollama e de ANTHROPIC_API_KEY no .env; ~1–3 min de GPU por pedido):
  .venv\\Scripts\\deepeval test run tests/evals/test_agente.py --identifier rodada-1 -i
Depois: .venv\\Scripts\\python tests/evals/relatorio.py   (juiz × nota interna, por pedido)
"""
import json
import time
from pathlib import Path

import pytest
from deepeval import assert_test
from deepeval.dataset import EvaluationDataset, Golden
from deepeval.integrations.langchain import CallbackHandler
from deepeval.tracing import observe, update_current_trace

from metrics import AGENTE_TRACE_METRICS, FATOS
from stone.agente.grafo import rodar

AQUI = Path(__file__).parent
SAIDAS = AQUI / "saidas.jsonl"   # o que o agente entregou em cada pedido, para o relatorio.py

dataset = EvaluationDataset()
dataset.add_goldens_from_json_file(file_path=str(AQUI / ".dataset.json"))


def texto_do_criativo(cr: dict) -> str:
    """O que o juiz lê: o criativo em si, sem a nota interna nem as referências (para não enviesar)."""
    cenas = "\n".join(f"{i}. {c}" for i, c in enumerate(cr["roteiro"], 1))
    return (f"Título: {cr['titulo']}\nGancho (0–3 s): {cr['gancho']}\n"
            f"Formato: {cr['formato']} · {cr['duracao_s']} s\nTexto na tela: {cr['texto_na_tela']}\n"
            f"Roteiro:\n{cenas}\nLegenda: {cr['legenda']}\nCTA: {cr['cta']}\n"
            f"Justificativa do agente: {cr['justificativa']}")


@observe(type="agent")
def agente_rastreado(pedido: str) -> str:
    t0 = time.time()
    s = rodar(pedido, callbacks=[CallbackHandler()])
    cr, av = s["melhor"]["criativo"], s["melhor"]["avaliacao"]
    saida = texto_do_criativo(cr)
    meta = {"segmento": s["plano"]["segmento"], "confianca": s["padroes"]["confianca"],
            "nota_aderencia": av["nota"], "versoes": [h["nota"] for h in s["historico"]],
            "problemas_texto": av.get("problemas", []), "segundos": round(time.time() - t0)}
    update_current_trace(input=pedido, output=saida, context=FATOS, metadata=meta,
                         tags=[s["plano"]["segmento"]])
    with SAIDAS.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"pedido": pedido, "criativo": cr, **meta}, ensure_ascii=False) + "\n")
    return saida


@pytest.mark.parametrize("golden", dataset.goldens, ids=lambda g: g.input[:60])
def test_agente(golden: Golden):
    agente_rastreado(golden.input)
    assert_test(golden=golden, metrics=AGENTE_TRACE_METRICS)
