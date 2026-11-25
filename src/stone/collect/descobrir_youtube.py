"""Descoberta de canais do nicho MPE no YouTube (etapa de seleção de perfis).

search.list custa 100 unidades, então só é usado aqui, para descobrir canais.
A coleta dos vídeos (youtube.py) usa playlists, que custam 1 unidade.

Saída: data/seeds/candidatos_youtube.csv com inscritos, faixa, atividade e as
buscas que trouxeram cada canal. A curadoria final vai para perfis.csv.

Uso:
  python -m stone.collect.descobrir_youtube
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

import pandas as pd

from ..config import DATA, faixa_de
from .youtube import _get

# Buscas por vídeos curtos: trazem canais que de fato publicam Shorts para MPE.
BUSCAS_SHORTS = [
    "dicas para MEI",
    "como precificar produto pequeno negócio",
    "como vender mais no instagram loja",
    "empreendedora salão de beleza dicas",
    "confeitaria lucro precificação",
    "fluxo de caixa pequeno negócio",
    "empreendedorismo feminino dicas",
    "maquininha de cartão taxa empreendedor",
    "atendimento ao cliente pequeno comércio",
    "marketing para pequenos negócios",
]
# Buscas por canal: pegam perfis do setor (bancos, fintechs, educação).
BUSCAS_CANAIS = [
    "pequenos negócios empreendedorismo",
    "MEI microempreendedor",
    "educação financeira para empreendedores",
    "gestão de pequenas empresas",
]


def _buscar(q: str, tipo: str) -> list[str]:
    params = {"part": "snippet", "q": q, "type": tipo, "maxResults": 50,
              "regionCode": "BR", "relevanceLanguage": "pt"}
    if tipo == "video":
        params["videoDuration"] = "short"  # menos de 4 minutos
        params["publishedAfter"] = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
    dados = _get("search", **params)
    return [i["snippet"]["channelId"] for i in dados.get("items", [])]


def descobrir() -> pd.DataFrame:
    origem: dict[str, set[str]] = defaultdict(set)
    for q in BUSCAS_SHORTS:
        for cid in _buscar(q, "video"):
            origem[cid].add(q)
    for q in BUSCAS_CANAIS:
        for cid in _buscar(q, "channel"):
            origem[cid].add(f"canal: {q}")

    ids = list(origem)
    linhas = []
    for i in range(0, len(ids), 50):
        dados = _get("channels", part="snippet,statistics", id=",".join(ids[i:i + 50]))
        for c in dados.get("items", []):
            sn, st = c["snippet"], c.get("statistics", {})
            subs = None if st.get("hiddenSubscriberCount") else int(st.get("subscriberCount", 0))
            linhas.append({
                "channel_id": c["id"],
                "handle": (sn.get("customUrl") or "").lstrip("@"),
                "nome": sn.get("title"),
                "pais": sn.get("country"),
                "inscritos": subs,
                "videos": int(st.get("videoCount", 0)),
                "faixa": faixa_de(subs),
                "n_buscas": len(origem[c["id"]]),
                "buscas": " | ".join(sorted(origem[c["id"]])),
                "descricao": (sn.get("description") or "").replace("\n", " ")[:300],
            })
    df = pd.DataFrame(linhas).sort_values(["n_buscas", "inscritos"], ascending=False)
    saida = DATA / "seeds" / "candidatos_youtube.csv"
    df.to_csv(saida, index=False, encoding="utf-8")
    print(f"{len(df)} canais em {saida}")
    print(df["faixa"].value_counts(dropna=False).to_string())
    return df


if __name__ == "__main__":
    descobrir()
