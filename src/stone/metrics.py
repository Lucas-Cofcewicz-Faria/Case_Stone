"""Métricas de engajamento.

Métrica principal do projeto (decidida em 18/11, ver README):
  conversa = (comentários + 2·comentários com intenção) ÷ views × 1000
  "De cada mil pessoas que viram, quantas comentaram ou pediram algo."
  Curtidas não entram. Views entram só como denominador (alcance), nunca como mérito.
  Critérios: mínimo de MIN_VIEWS views para entrar no ranking, top 10% calculado
  dentro de cada faixa de perfil (micro/médio/grande, evita viés de sobrevivência)
  e no máximo MAX_TOP_POR_PERFIL posts de um mesmo perfil no top 10%.

Métricas de comparação (calculadas e reportadas lado a lado):
  ER (recomendada no TAPI) = (curtidas + comentários) ÷ seguidores
  EQ = (curtidas + 5·comentários + 10·intenção) ÷ seguidores

Por que não dividir por seguidores na principal: em Shorts e Reels o algoritmo
entrega o post a quem não segue o perfil (no Impulso, 93,9% das views vêm de não
seguidores). Normalizado por seguidores, um viral com milhões de views e quase
nenhum comentário vai para o topo. Na base de 18/11, ER e EQ tiveram correlação
de Spearman 0,99: o peso maior para comentários não mudava o ranking.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .config import (CONVERSA_PESO_INTENCAO, EQ_WEIGHTS, MAX_TOP_POR_PERFIL, MIN_POST_AGE_DAYS,
                     MIN_VIEWS, TOP_PERCENTILE, TOP_POR_FAIXA, faixa_de)


def filtrar_maduros(posts: pd.DataFrame, agora: datetime | None = None,
                    min_dias: int = MIN_POST_AGE_DAYS) -> pd.DataFrame:
    """Mantém só posts com pelo menos `min_dias` de publicação."""
    agora = agora or datetime.now(timezone.utc)
    publicado = pd.to_datetime(posts["publicado_em"], utc=True)
    return posts[(pd.Timestamp(agora) - publicado).dt.days >= min_dias].copy()


def _top_com_limite(df: pd.DataFrame, coluna: str, elegivel: pd.Series, limite: int | None) -> pd.Series:
    """Marca os 10% melhores entre os elegíveis, com no máximo `limite` posts por perfil.

    Quando um perfil bate o limite, a vaga passa para o próximo post do ranking,
    então o top continua com 10% dos elegíveis.
    """
    candidatos = df[elegivel].sort_values(coluna, ascending=False)
    n_top = math.ceil(len(candidatos) * (1 - TOP_PERCENTILE))
    marcados, contagem = [], {}
    for idx, (h, p) in zip(candidatos.index, zip(candidatos["handle"], candidatos["plataforma"])):
        if len(marcados) >= n_top:
            break
        if limite is not None and contagem.get((h, p), 0) >= limite:
            continue
        contagem[(h, p)] = contagem.get((h, p), 0) + 1
        marcados.append(idx)
    return df.index.isin(marcados)


def calcular(posts: pd.DataFrame, perfis: pd.DataFrame,
             pesos: dict[str, float] = EQ_WEIGHTS,
             peso_intencao: float = CONVERSA_PESO_INTENCAO,
             min_views: int = MIN_VIEWS,
             max_por_perfil: int | None = MAX_TOP_POR_PERFIL,
             por_faixa: bool = TOP_POR_FAIXA) -> pd.DataFrame:
    """Recebe posts e perfis e devolve posts com as métricas e as marcações de top 10%.

    `posts` precisa de: post_id, handle, plataforma, curtidas, comentarios e,
    opcionalmente, views e comentarios_intencao.
    """
    df = posts.merge(perfis[["handle", "plataforma", "seguidores"]],
                     on=["handle", "plataforma"], how="left")

    curt = df["curtidas"].astype("float")
    com = df["comentarios"].astype("float")
    views = (df["views"] if "views" in df else pd.Series(np.nan, index=df.index)).astype("float")
    intencao = (df["comentarios_intencao"] if "comentarios_intencao" in df
                else pd.Series(np.nan, index=df.index)).astype("float")
    seg = df["seguidores"].astype("float").where(lambda s: s > 0)

    df["intencao_conhecida"] = intencao.notna()
    df["er"] = (curt + com) / seg
    df["eq"] = (pesos["curtidas"] * curt + pesos["comentarios"] * com
                + pesos["comentarios_intencao"] * intencao.fillna(0)) / seg
    df["conversa"] = (com + peso_intencao * intencao.fillna(0)) / views.where(views > 0) * 1000
    df["taxa_conversa"] = com / curt.where(curt > 0)

    df["rankeavel_er"] = df["er"].notna()
    df["rankeavel"] = df["conversa"].notna() & (views >= min_views)

    mediana = df[df["rankeavel"]].groupby(["handle", "plataforma"])["conversa"].median()
    df = df.join(mediana.rename("conversa_mediana_perfil"), on=["handle", "plataforma"])
    df["lift"] = df["conversa"] / df["conversa_mediana_perfil"].where(df["conversa_mediana_perfil"] > 0)

    grupo = df["seguidores"].map(faixa_de) if por_faixa else pd.Series("todos", index=df.index)
    df["grupo_ranking"] = grupo.fillna("sem_faixa")
    df["percentil"] = df["conversa"].where(df["rankeavel"]).groupby(df["grupo_ranking"]).rank(pct=True)
    df["percentil_er"] = df["er"].rank(pct=True)
    df["top10"] = False
    for _, idx in df.groupby("grupo_ranking").groups.items():
        parte = df.loc[idx]
        df.loc[idx, "top10"] = _top_com_limite(parte, "conversa", parte["rankeavel"], max_por_perfil)
    df["top10_er"] = df["rankeavel_er"] & (df["percentil_er"] > TOP_PERCENTILE)
    df["top10_eq"] = _top_com_limite(df, "eq", df["eq"].notna(), None)
    return df


def sensibilidade(posts: pd.DataFrame, perfis: pd.DataFrame, cenarios: list[float]) -> pd.DataFrame:
    """Compara o top 10% para cada peso de intenção com o do primeiro cenário (Jaccard)."""
    tops = [set(calcular(posts, perfis, peso_intencao=p).query("top10")["post_id"]) for p in cenarios]
    base = tops[0]
    return pd.DataFrame([{"peso_intencao": p, "n_top": len(t),
                          "jaccard_vs_primeiro": round(len(base & t) / len(base | t), 3) if (base | t) else 1.0}
                         for p, t in zip(cenarios, tops)])
