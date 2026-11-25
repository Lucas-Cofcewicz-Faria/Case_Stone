"""Caminhos, chaves e parâmetros declarados do projeto."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATA = ROOT / "data"
RAW = DATA / "raw"
CACHE = DATA / "cache"
DB_PATH = DATA / "stone.db"

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
IG_USER_ID = os.getenv("IG_USER_ID", "")
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN", "")
GRAPH_API_VERSION = os.getenv("GRAPH_API_VERSION", "v24.0")

# Critérios declarados (vão para o README)
MIN_POST_AGE_DAYS = 14          # métricas estabilizadas (TAPI, seção 5)
TOP_PERCENTILE = 0.90           # alto desempenho = 10% superiores
SHORTS_MAX_SECONDS = 180        # Shorts podem ter até 3 min

# Métrica principal: conversa = (comentários + 2·intenção) ÷ views × 1000
CONVERSA_PESO_INTENCAO = 2.0
CONVERSA_SENSITIVITY = [2.0, 1.0, 4.0]   # pesos de intenção testados
MIN_VIEWS = 300                          # menos que isso é ruído (1000 cortava metade dos micro)
TOP_POR_FAIXA = True                     # top 10% dentro de cada faixa (micro/médio/grande)
MAX_TOP_POR_PERFIL = 15                  # nenhum perfil domina o top 10%

# EQ por seguidores (comparação; correlação 0,99 com o ER na base de 18/11)
EQ_WEIGHTS = {"curtidas": 1.0, "comentarios": 5.0, "comentarios_intencao": 10.0}

# Faixas de tamanho de perfil (TAPI/aula: micro até 10 mil, médio 10–100 mil)
FAIXAS = [(10_000, "micro"), (100_000, "medio"), (float("inf"), "grande")]


def faixa_de(seguidores: int | None) -> str | None:
    if seguidores is None:
        return None
    for limite, nome in FAIXAS:
        if seguidores <= limite:
            return nome
    return None
