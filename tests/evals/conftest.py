"""Ambiente das evals do agente: spans do deepeval ligados, nada vai para a nuvem."""
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
os.environ.setdefault("STONE_TRACE", "1")             # stone.llm vira span `llm` em cada chamada ao Qwen
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "1")
os.environ.setdefault("ENV_DIR_PATH", str(RAIZ))      # o deepeval lê ANTHROPIC_API_KEY do .env da raiz
sys.path[:0] = [str(RAIZ / "src"), str(Path(__file__).parent)]
