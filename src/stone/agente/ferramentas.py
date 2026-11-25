"""Ferramentas do agente: as mesmas funções servem ao grafo LangGraph e ao servidor MCP.

Tudo lê a base local (SQLite + parquet) e o avaliador; nada aqui chama a internet.
"""
from __future__ import annotations

import re
import sqlite3
from functools import lru_cache

import pandas as pd

from ..config import DB_PATH
from ..evaluator import AUSENCIAS, Modelo, avaliar, marcar_top_perfil, rubricar_texto, treinar
from ..patterns import calcular_lift, montar_base
from ..rubric import duracao_faixa

# segmentos do playbook → segmentos da base (curadoria na coleta)
SEGMENTOS = {
    "alimentacao": ["alimentação"],
    "beleza": ["beleza"],
    "varejo_e_vendas": ["varejo", "vendas", "vendas online", "negócio online", "comércio local", "marketing digital"],
    "mei_e_contabilidade": ["MEI", "contabilidade MEI", "contabilidade", "abertura e gestão"],
    "pagamentos": ["maquininha", "maquininha e conta PJ"],
    "gestao_e_financas": ["gestão", "gestão financeira", "educação financeira", "empreendedorismo", "setor/educação MPE"],
    "artesanato_e_festas": ["festas e artesanato"],
}
SEM_SEGMENTO = "servicos_e_outros"  # sem recorte próprio na base
MIN_TOP_SEGMENTO = 15     # abaixo disso, o padrão do segmento não é confiável e vale o geral
COLUNAS_REF = ["post_id", "titulo", "url", "nome", "segmento", "conversa", "views", "comentarios",
               "formato_video", "tipo_hook", "hook_primeiros_3s", "duracao_faixa", "tipo_cta"]


@lru_cache(maxsize=1)
def _base() -> pd.DataFrame:
    return marcar_top_perfil(montar_base())


@lru_cache(maxsize=1)
def _modelo() -> Modelo:
    return treinar(_base())


def _do_segmento(segmento: str | None) -> pd.DataFrame:
    df = _base()
    if segmento and segmento in SEGMENTOS:
        return df[df["segmento"].isin(SEGMENTOS[segmento])]
    return df


def padroes(segmento: str | None = None, n: int = 6) -> dict:
    """Padrões e antipadrões do top 10%, do segmento quando há dados suficientes, senão os gerais."""
    parte = _do_segmento(segmento)
    r = parte[parte["rankeavel"]]
    n_top = int(r["top10"].sum())
    usa_segmento = segmento in SEGMENTOS and n_top >= MIN_TOP_SEGMENTO
    fonte = parte if usa_segmento else _base()
    saida = {"segmento": segmento, "posts_top_no_segmento": n_top,
             "fonte_dos_padroes": "segmento" if usa_segmento else "base inteira",
             # padrão geral (sem segmento próprio) é menos específico para o negócio: confiança baixa
             "confianca": "baixa" if not usa_segmento else "alta" if n_top >= 40 else "media"}
    for alvo in ("top10", "top_perfil"):
        lift = calcular_lift(fonte, alvo)
        # no segmento a amostra é menor: aceita padrões "neutros" com lift claro e 5+ posts
        # ausência ("sem gancho", "cta nenhum", "força baixa") nunca é receita, mesmo com lift alto:
        # o avaliador já não dá crédito a elas, e no prompt do agente viravam "faça um post sem CTA"
        pos = lift[(lift["lift"] >= 1.2) & (lift["posts_top"] >= 5) & ~lift["atributo"].isin(AUSENCIAS)]
        pos = pos.sort_values("z", ascending=False).head(n)
        neg = lift[(lift["lift"] <= 0.8) & (lift["posts_resto"] >= 10)].sort_values("z").head(n)
        cols = ["atributo", "lift", "posts_top", "z", "tipo"]
        saida[alvo] = {"fazer": pos[cols].to_dict("records"), "evitar": neg[cols].to_dict("records")}
    return saida


def referencias(segmento: str | None = None, n: int = 5, texto: str | None = None) -> list[dict]:
    """Posts do top 10% do segmento com mais conversa, um por perfil. `texto` filtra por palavra no título."""
    parte = _do_segmento(segmento)
    top = parte[parte["top10"]]
    if texto:
        palavras = [p for p in re.findall(r"\w{4,}", texto.lower())]
        if palavras:
            casa = top["titulo"].fillna("").str.lower().map(lambda t: sum(p in t for p in palavras))
            top = top.assign(_casa=casa).sort_values(["_casa", "conversa"], ascending=False)
    else:
        top = top.sort_values("conversa", ascending=False)
    top = top.drop_duplicates("handle").head(n)
    out = top[[c for c in COLUNAS_REF if c in top]].copy()
    out["conversa"] = out["conversa"].round(2)
    return out.to_dict("records")


def avaliar_rascunho(titulo: str, legenda: str = "", roteiro: str = "", duracao_s: int | None = None) -> dict:
    """Aplica a mesma rubrica da base ao rascunho (só texto) e devolve nota, padrões, sugestões e referências."""
    corpo = legenda if not roteiro else f"{legenda}\n\nRoteiro:\n{roteiro}"
    rub = rubricar_texto(titulo, corpo, "youtube")
    rub["tipo_post"] = "short"
    rub["duracao_faixa"] = duracao_faixa(duracao_s)
    # trava independente do modelo: menos de 4 palavras diferentes não é uma mensagem
    palavras = set(re.findall(r"\w{3,}", f"{titulo} {legenda} {roteiro}".lower()))
    if len(palavras) < 4:
        rub["clareza_mensagem_0a10"] = 0
        rub["forca_hook_0a10"] = 0
    av = avaliar(_modelo(), rub)
    # a rubrica inteira volta junto, para o extrato listar todos os lançamentos que somam a nota
    av["rubrica_do_rascunho"] = {k: v for k, v in rub.items() if k not in ("descricao_visual", "elementos_top5")}
    return av


def avaliar_post(post_id: str) -> dict:
    """Avalia um post que já está na base."""
    df = _base()
    linha = df[df["post_id"] == post_id]
    if linha.empty:
        return {"erro": f"post {post_id} não está na base com rubrica"}
    return avaliar(_modelo(), linha.iloc[0].to_dict())


SQL_PERMITIDO = re.compile(r"^\s*(select|with)\b", re.I)


def consultar_base(sql: str, limite: int = 50) -> list[dict]:
    """SQL só de leitura no SQLite (tabelas perfis, posts, comentarios, rubrica)."""
    if not SQL_PERMITIDO.match(sql) or ";" in sql.strip().rstrip(";"):
        return [{"erro": "só uma consulta SELECT por vez"}]
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        return pd.read_sql(sql, con).head(limite).to_dict("records")
    except Exception as e:  # erro de SQL volta para o agente corrigir
        return [{"erro": str(e)}]
    finally:
        con.close()
