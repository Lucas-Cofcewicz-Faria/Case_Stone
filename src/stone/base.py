"""Monta a base de análise a partir do SQLite e gera o relatório de qualidade.

Passos:
  1. lê perfis, posts e comentários;
  2. classifica a intenção dos comentários e estima comentários com intenção
     por post (taxa da amostra lida × total de comentários do post);
  3. aplica os critérios declarados: posts com 14+ dias e perfis ativos nos
     últimos 12 meses;
  4. calcula ER, EQ, lift e top 10% (stone.metrics);
  5. salva data/base_posts.parquet e data/qualidade.md.

Uso:
  python -m stone.base
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pandas as pd

from .config import CONVERSA_SENSITIVITY, DATA, DB_PATH, MAX_TOP_POR_PERFIL, MIN_POST_AGE_DAYS, MIN_VIEWS
from .intent import intencao_por_post
from .metrics import calcular, filtrar_maduros, sensibilidade


def carregar(con: sqlite3.Connection) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    perfis = pd.read_sql("select * from perfis", con)
    posts = pd.read_sql("select * from posts", con)
    comentarios = pd.read_sql("select * from comentarios", con)
    return perfis, posts, comentarios


def montar(perfis: pd.DataFrame, posts: pd.DataFrame, comentarios: pd.DataFrame,
           agora: datetime | None = None) -> tuple[pd.DataFrame, dict]:
    agora = agora or datetime.now(timezone.utc)
    q: dict = {"posts_coletados": len(posts), "perfis_coletados": len(perfis)}

    # atividade: perfil com pelo menos um post nos últimos 12 meses
    pub = pd.to_datetime(posts["publicado_em"], utc=True)
    ultimo = posts.assign(pub=pub).groupby(["handle", "plataforma"])["pub"].max()
    ativos = ultimo[ultimo >= pd.Timestamp(agora - timedelta(days=365))].index
    q["perfis_inativos"] = sorted(f"{h} ({p})" for h, p in set(ultimo.index) - set(ativos))
    posts = posts.set_index(["handle", "plataforma"]).loc[lambda d: d.index.isin(ativos)].reset_index()

    maduros = filtrar_maduros(posts, agora)
    q["posts_descartados_menos_14_dias"] = len(posts) - len(maduros)

    if len(comentarios):
        intencao = intencao_por_post(comentarios)
        maduros = maduros.merge(intencao, on=["post_id", "plataforma"], how="left")
        maduros["comentarios_intencao"] = (maduros["taxa_intencao"] * maduros["comentarios"]).round()
    else:
        maduros["comentarios_intencao"] = float("nan")

    df = calcular(maduros, perfis)
    df = df.merge(perfis[["handle", "plataforma", "faixa", "segmento", "origem", "nome"]],
                  on=["handle", "plataforma"], how="left")

    q.update({
        "posts_na_base": len(df),
        "posts_rankeaveis": int(df["rankeavel"].sum()),
        "posts_abaixo_do_minimo_de_views": int((df["conversa"].notna() & ~df["rankeavel"]).sum()),
        "curtidas_ocultas": int(df["curtidas"].isna().sum()),
        "posts_com_intencao_estimada": int(df["intencao_conhecida"].sum()),
        "comentarios_lidos": len(comentarios),
        "perfis_na_base": df[["handle", "plataforma"]].drop_duplicates().shape[0],
        "por_plataforma": df["plataforma"].value_counts().to_dict(),
        "perfis_por_faixa": df.drop_duplicates(["handle", "plataforma"])["faixa"].value_counts().to_dict(),
        "periodo": (str(pd.to_datetime(df["publicado_em"], utc=True).min().date()) if len(df) else None,
                    str(pd.to_datetime(df["publicado_em"], utc=True).max().date()) if len(df) else None),
        "posts_no_top10": int(df["top10"].sum()),
        "perfis_no_top10": int(df.loc[df["top10"], "handle"].nunique()),
        "top10_por_faixa": df.loc[df["top10"], "faixa"].value_counts().to_dict(),
        "sobreposicao_top10_conversa_vs_er": _jaccard(df, "top10", "top10_er"),
        "spearman_conversa_vs_er": round(df[["conversa", "er"]].corr("spearman").iloc[0, 1], 3) if len(df) else None,
    })
    if df["rankeavel"].any():
        q["sensibilidade_pesos"] = sensibilidade(maduros, perfis, CONVERSA_SENSITIVITY)
    return df, q


def _jaccard(df: pd.DataFrame, a: str, b: str) -> float | None:
    sa, sb = set(df.loc[df[a], "post_id"]), set(df.loc[df[b], "post_id"])
    return round(len(sa & sb) / len(sa | sb), 3) if (sa | sb) else None


def relatorio_md(q: dict) -> str:
    linhas = ["# Relatório de qualidade da base", "",
              f"Gerado em {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC.", "",
              "| Item | Valor |", "|---|---|"]
    for k, v in q.items():
        if k == "sensibilidade_pesos":
            continue
        linhas.append(f"| {k.replace('_', ' ')} | {v} |")
    if "sensibilidade_pesos" in q:
        linhas += ["", "## Sensibilidade do peso de intenção", "",
                   "Quanto o top 10% de conversa muda com outro peso para comentários com intenção (Jaccard contra o primeiro cenário).", "",
                   q["sensibilidade_pesos"].to_markdown(index=False)]
    linhas += ["", "## Critérios aplicados", "",
               "- Métrica principal: conversa = (comentários + 2·comentários com intenção) ÷ views × 1000. Curtidas não entram.",
               f"- Ranking só com {MIN_VIEWS}+ views; no máximo {MAX_TOP_POR_PERFIL} posts por perfil no top 10%.",
               "- ER (curtidas + comentários) ÷ seguidores, recomendada no TAPI, é calculada e comparada lado a lado.",
               f"- Só posts com {MIN_POST_AGE_DAYS}+ dias de publicação.",
               "- Só perfis com pelo menos um post nos últimos 12 meses.",
               "- Posts com curtidas ocultas ou perfil sem seguidores ficam fora do ranking de ER (a conversa não usa curtidas).",
               "- Comentários com intenção = taxa de intenção na amostra lida × total de comentários do post.",
               "- Seguidores e inscritos são os da data da coleta, não os da data do post."]
    return "\n".join(linhas) + "\n"


def main() -> None:
    con = sqlite3.connect(DB_PATH)
    df, q = montar(*carregar(con))
    con.close()
    df.to_parquet(DATA / "base_posts.parquet", index=False)
    (DATA / "qualidade.md").write_text(relatorio_md(q), encoding="utf-8")
    print(relatorio_md(q))


if __name__ == "__main__":
    main()
