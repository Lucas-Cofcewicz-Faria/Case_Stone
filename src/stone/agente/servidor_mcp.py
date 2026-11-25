"""Servidor MCP (FastMCP) com as ferramentas do agente: qualquer cliente MCP consulta a base,
os padrões e o avaliador, ou pede um criativo completo.

Uso (stdio):
  python -m stone.agente.servidor_mcp
Cada chamada fica registrada em data/logs/mcp.jsonl.
"""
from __future__ import annotations

import json
import time
from functools import wraps

from fastmcp import FastMCP

from ..config import DATA
from . import ferramentas as F

LOG = DATA / "logs" / "mcp.jsonl"
mcp = FastMCP("case-stone")


def _logado(fn):
    @wraps(fn)
    def inner(*a, **kw):
        t0 = time.time()
        out = fn(*a, **kw)
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "ferramenta": fn.__name__, "args": kw,
                                "segundos": round(time.time() - t0, 2)}, ensure_ascii=False, default=str) + "\n")
        return out
    return inner


@mcp.tool
@_logado
def padroes_do_segmento(segmento: str | None = None) -> dict:
    """Padrões e antipadrões do top 10% de conversa. Segmentos: alimentacao, beleza, varejo_e_vendas,
    mei_e_contabilidade, pagamentos, gestao_e_financas, artesanato_e_festas (vazio = base inteira)."""
    return F.padroes(segmento)


@mcp.tool
@_logado
def referencias_do_segmento(segmento: str | None = None, n: int = 5, texto: str | None = None) -> list[dict]:
    """Posts reais do top 10% de conversa do segmento, um por perfil; `texto` prioriza títulos com essas palavras."""
    return F.referencias(segmento, n, texto)


@mcp.tool
@_logado
def avaliar_rascunho(titulo: str, legenda: str = "", roteiro: str = "", duracao_s: int | None = None) -> dict:
    """Nota de aderência 0–100 de um rascunho, com padrões cumpridos, antipadrões, sugestões e referências."""
    return F.avaliar_rascunho(titulo, legenda, roteiro, duracao_s)


@mcp.tool
@_logado
def avaliar_post(post_id: str) -> dict:
    """Nota de aderência de um post que já está na base."""
    return F.avaliar_post(post_id)


@mcp.tool
@_logado
def consultar_base(sql: str) -> list[dict]:
    """SQL só de leitura. Tabelas: perfis, posts, comentarios, rubrica (json com os campos da rubrica)."""
    return F.consultar_base(sql)


@mcp.tool
@_logado
def gerar_criativo(pedido: str) -> str:
    """Roda o agente completo: entende o pedido, busca padrões e referências, gera, avalia e revisa."""
    from .grafo import rodar
    return rodar(pedido)["resposta"]


if __name__ == "__main__":
    mcp.run()
