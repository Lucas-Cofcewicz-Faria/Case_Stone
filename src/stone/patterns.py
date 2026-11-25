"""Padrões do top 10%: o lift de cada atributo da rubrica e os perfis em destaque.

Lift de um atributo = % dos posts do top 10% que têm o atributo ÷ % do resto que tem.
Lift 2 = aparece duas vezes mais no top do que no resto. Junto vai o número de
posts que sustentam o padrão e um teste simples (log da razão de chances, z), para
não chamar de padrão algo que aparece em 3 posts.

Só entram posts rankeáveis (300+ views), os mesmos que definem o top 10%.

Uso:
  python -m stone.patterns          # gera data/padroes.csv e data/padroes.md
"""
from __future__ import annotations

import json
import math
import sqlite3

import pandas as pd

from .config import DATA, DB_PATH
from .llm import MODELO_PADRAO
from .rubric import PROMPT_VERSAO, normalizar_hook

# campos categóricos viram "campo=valor"; booleanos viram "campo" (só o True)
CATEGORICOS = ["formato_video", "tipo_hook", "tema_principal", "pilar_impulso", "tom", "tipo_cta",
               "tipo_post", "duracao_faixa", "legenda_tamanho"]
BOOLEANOS = ["tem_rosto", "criador_e_empreendedor_real", "prova_social", "usa_linguagem_regional",
             "tem_cta", "oferta_ou_beneficio_explicito"]
# notas 0–10 viram faixas, porque o modelo concentra as notas no meio da escala
NOTAS = {"forca_hook_0a10": [(0, 4, "baixa"), (5, 6, "media"), (7, 10, "alta")],
         "clareza_mensagem_0a10": [(0, 5, "baixa"), (6, 7, "media"), (8, 10, "alta")]}

MIN_POSTS_TOP = 8        # padrão precisa de pelo menos 8 posts do top com o atributo
LIFT_FORTE = 1.25        # padrão: aparece 25%+ mais no top
LIFT_ANTI = 0.80         # antipadrão: aparece 20%+ menos no top
Z_MIN = 1.96             # ~95% de confiança


def _faixa_nota(campo: str, valor) -> str | None:
    if valor is None or pd.isna(valor):
        return None
    for lo, hi, nome in NOTAS[campo]:
        if lo <= int(valor) <= hi:
            return nome
    return None


def atributos(rub: dict) -> set[str]:
    """Transforma uma rubrica (dict) no conjunto de atributos usados nos padrões."""
    out = set()
    for c in CATEGORICOS:
        v = rub.get(c)
        if v is not None and not (isinstance(v, float) and pd.isna(v)):
            out.add(f"{c}={v}")
    for c in BOOLEANOS:
        if rub.get(c) is True:
            out.add(c)
    for c in NOTAS:
        f = _faixa_nota(c, rub.get(c))
        if f:
            out.add(f"{c}={f}")
    return out


def carregar_rubricas(con: sqlite3.Connection, modelo: str = MODELO_PADRAO,
                      versao: str = PROMPT_VERSAO) -> pd.DataFrame:
    """Uma linha por post: campos da rubrica achatados + tipo_post, duração e legenda."""
    linhas = []
    for pid, plat, js, tipo, dur, leg in con.execute(
            "select post_id, plataforma, json, tipo_post, duracao_faixa, legenda_tamanho "
            "from rubrica where modelo=? and versao=?", (modelo, versao)):
        d = normalizar_hook(json.loads(js))
        d.update(post_id=pid, plataforma=plat, tipo_post=tipo, duracao_faixa=dur, legenda_tamanho=leg)
        linhas.append(d)
    return pd.DataFrame(linhas)


def montar_base(con: sqlite3.Connection | None = None) -> pd.DataFrame:
    """Base de posts (métricas) + rubrica + conjunto de atributos de cada post."""
    fechar = con is None
    con = con or sqlite3.connect(DB_PATH)
    try:
        rub = carregar_rubricas(con)
    finally:
        if fechar:
            con.close()
    base = pd.read_parquet(DATA / "base_posts.parquet")
    df = base.merge(rub, on=["post_id", "plataforma"], how="inner", suffixes=("", "_rub"))
    df["atributos"] = [atributos(r) for r in df.to_dict("records")]
    return df


def _z_log_odds(a: int, b: int, c: int, d: int) -> float:
    """z da razão de chances com correção de Haldane (soma 0,5 em cada célula)."""
    a, b, c, d = a + .5, b + .5, c + .5, d + .5
    return math.log((a * d) / (b * c)) / math.sqrt(1 / a + 1 / b + 1 / c + 1 / d)


def calcular_lift(df: pd.DataFrame, alvo: str = "top10") -> pd.DataFrame:
    """Lift de todos os atributos. `df` precisa de `atributos` (set) e da coluna booleana `alvo`."""
    df = df[df["rankeavel"]] if "rankeavel" in df else df
    top = df[df[alvo]]
    resto = df[~df[alvo]]
    n_top, n_resto = len(top), len(resto)
    if not n_top or not n_resto:
        return pd.DataFrame()
    cont_top = pd.Series([a for s in top["atributos"] for a in s]).value_counts()
    cont_resto = pd.Series([a for s in resto["atributos"] for a in s]).value_counts()
    linhas = []
    for attr in sorted(set(cont_top.index) | set(cont_resto.index)):
        a, c = int(cont_top.get(attr, 0)), int(cont_resto.get(attr, 0))
        pt, pr = a / n_top, c / n_resto
        lift = (pt + 1e-9) / (pr + 1e-9) if pr else float("inf")
        z = _z_log_odds(a, n_top - a, c, n_resto - c)
        campo = attr.split("=")[0]
        tipo = ("padrao" if lift >= LIFT_FORTE and a >= MIN_POSTS_TOP and z >= Z_MIN else
                "antipadrao" if lift <= LIFT_ANTI and (c * n_top / n_resto) >= MIN_POSTS_TOP and z <= -Z_MIN
                else "neutro")
        linhas.append({"atributo": attr, "campo": campo, "posts_top": a, "posts_resto": c,
                       "pct_top": round(100 * pt, 1), "pct_resto": round(100 * pr, 1),
                       "lift": round(lift, 2), "z": round(z, 2), "tipo": tipo})
    return pd.DataFrame(linhas).sort_values(["tipo", "lift"], ascending=[True, False]).reset_index(drop=True)


def lift_por_grupo(df: pd.DataFrame, coluna: str, min_top: int = 15) -> dict[str, pd.DataFrame]:
    """Lift calculado dentro de cada grupo (ex.: segmento, plataforma), quando o grupo tem top suficiente."""
    out = {}
    for g, parte in df[df["rankeavel"]].groupby(coluna):
        if parte["top10"].sum() >= min_top:
            out[str(g)] = calcular_lift(parte)
    return out


def perfis_em_destaque(df: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    """Perfis com mais posts no top 10%, com a mediana de conversa e de lift no próprio perfil."""
    r = df[df["rankeavel"]]
    g = r.groupby(["handle", "plataforma"]).agg(
        nome=("nome", "first"), segmento=("segmento", "first"), faixa=("faixa", "first"),
        seguidores=("seguidores", "first"), posts=("post_id", "size"), posts_top10=("top10", "sum"),
        conversa_mediana=("conversa", "median"))
    g["pct_no_top10"] = (100 * g["posts_top10"] / g["posts"]).round(1)
    g["conversa_mediana"] = g["conversa_mediana"].round(2)
    return g[g["posts_top10"] > 0].sort_values(["posts_top10", "pct_no_top10"], ascending=False).head(n).reset_index()


def relatorio_md(lift: pd.DataFrame, destaque: pd.DataFrame, df: pd.DataFrame) -> str:
    r = df[df["rankeavel"]]
    cols = ["atributo", "posts_top", "pct_top", "pct_resto", "lift", "z"]
    linhas = ["# Padrões do top 10% (métrica conversa)", "",
              f"{len(r)} posts rankeáveis com rubrica, {int(r['top10'].sum())} no top 10%. "
              f"Lift = % no top ÷ % no resto. Padrão: lift ≥ {LIFT_FORTE}, {MIN_POSTS_TOP}+ posts no top e z ≥ {Z_MIN}. "
              f"Antipadrão: lift ≤ {LIFT_ANTI} e z ≤ −{Z_MIN}.", "",
              "Os padrões descrevem o que é mais comum entre os posts que geram conversa. "
              "São associações, não causas, e não prometem resultado.", "",
              "## Padrões fortes", "", lift[lift["tipo"] == "padrao"][cols].to_markdown(index=False), "",
              "## Antipadrões", "",
              lift[lift["tipo"] == "antipadrao"].sort_values("lift")[cols].to_markdown(index=False), "",
              "## Perfis em destaque", "", destaque.to_markdown(index=False), ""]
    return "\n".join(linhas)


def main() -> None:
    df = montar_base()
    lift = calcular_lift(df)
    destaque = perfis_em_destaque(df)
    lift.to_csv(DATA / "padroes.csv", index=False, encoding="utf-8")
    (DATA / "padroes.md").write_text(relatorio_md(lift, destaque, df), encoding="utf-8")
    print(relatorio_md(lift, destaque, df))


if __name__ == "__main__":
    main()
