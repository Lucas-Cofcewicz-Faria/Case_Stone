"""Classificação de intenção nos comentários (indicador indireto de lead, TAPI 6.1).

Versão 1: regras explicáveis em português, com texto normalizado (minúsculo e
sem acento). Cada comentário recebe um único tipo, pela ordem de prioridade:

  contato       quer comprar, contratar ou falar ("quero", "qual o link", "chama no direct")
  participacao  quer entrar ou se inscrever ("como participo", "me inscrevi", "eu quero participar")
  duvida        pergunta prática sobre o negócio ("como faço", "funciona para MEI?")
  marcacao      marca outra pessoa (@fulano): sinal de compartilhamento
  elogio        reação genérica ("top", "amei", só emoji)
  outro         o resto

`tem_intencao` = contato, participacao ou duvida. Esse é o número que entra no EQ.
"""
from __future__ import annotations

import re
import unicodedata

import pandas as pd

TIPOS_COM_INTENCAO = {"contato", "participacao", "duvida"}


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sem_acento.lower()).strip()


def _re(*padroes: str) -> re.Pattern:
    return re.compile("|".join(f"(?:{p})" for p in padroes))


CONTATO = _re(
    r"\bqual (?:e )?o (?:link|site|valor|preco|whats|zap|contato|numero)",
    r"\b(?:link|site|contato|whats ?app|zap|telefone|numero)\b.*\?",
    r"\bquanto (?:custa|e|fica|cobra|sai)\b",
    r"^(?:e |e o |qual o |qual e o )?(?:valor|preco|orcamento)\b.*\?",
    r"\bonde (?:compro|comprar|encontro|acho|vende|consigo)\b",
    r"\b(?:chama|me chama|manda|me manda|mande)\b.*\b(?:dm|direct|inbox|privado|pv|whats|zap)\b",
    r"\b(?:tenho interesse|interessad[oa]|quero (?:comprar|contratar|saber (?:mais|o valor|o preco)|o link|a maquininha|o curso|a planilha|uma?))\b",
    r"\bquero\b\s*[!.]*$",
    r"\bcomo (?:compro|contrato|adquiro|pe[cç]o)\b",
    r"\b(?:tem|voces tem|vende[ms]?) (?:o |a |uns |umas )?(?:curso|mentoria|planilha|consultoria|ebook|material)s?\b",
)
PARTICIPACAO = _re(
    r"\bcomo (?:faco para |faco pra |eu )?(?:participo|participar|me inscrevo|me inscrever|entro|entrar)\b",
    r"\b(?:quero|gostaria de|queria) (?:participar|me inscrever|entrar|fazer parte|uma vaga)\b",
    r"\bme inscrevi\b|\binscricao\b|\binscricoes\b|\bvagas?\b.*\?",
    r"\b(?:eu|eu tambem) (?:topo|to dentro|estou dentro|participo)\b",
)
DUVIDA = _re(
    r"\bcomo (?:faco|fazer|faz|calculo|calcular|precifico|precificar|organizo|organizar|abro|abrir|declaro|declarar|emito|emitir|consigo|funciona)\b",
    r"\b(?:serve|vale|funciona|da|pode) (?:pra|para) (?:mei|quem|loja|salao|restaurante|autonomo|pequen)",
    r"\b(?:alguem sabe|tenho uma duvida|minha duvida|uma duvida|me tira uma duvida|me ajuda|me ajudem|socorro)\b",
    r"\b(?:posso|preciso|devo|tenho que|tem que|tem q)\b.*\?",
    r"\b(?:qual|quais|quando|qdo|onde|por que|porque|o que|quanto)\b.*\?",
    r"\bpreciso (?:de )?(?:ajuda|comprovante|saber|entender|declarar|emitir|abrir|fechar|regularizar)\b",
    r"^(?:\S+\s+){3,}\S*\?",  # pergunta com 4+ palavras
)
MARCACAO = re.compile(r"@[\w.]{2,}")
ELOGIO = _re(
    r"^(?:top|show|amei|amo|lindo|linda|perfeito|perfeita|maravilhos[oa]|parabens|incrivel|excelente|otimo|otima|muito bom|muito boa|sensacional|arrasou|verdade|isso mesmo|exatamente|concordo|amem|gratidao|obrigad[oa])\b",
)
SO_EMOJI = re.compile(r"^[\W_\d]*$")


def classificar(texto: str) -> str:
    if not (texto or "").strip():
        return "outro"
    t = normalizar(texto)
    if not t or SO_EMOJI.match(t):
        return "elogio"  # só emoji ou símbolos: reação
    sem_mencao = MARCACAO.sub("", t).strip()
    if CONTATO.search(sem_mencao):
        return "contato"
    if PARTICIPACAO.search(sem_mencao):
        return "participacao"
    if DUVIDA.search(sem_mencao):
        return "duvida"
    if MARCACAO.search(t):
        return "marcacao"
    if ELOGIO.search(t):
        return "elogio"
    return "outro"


def classificar_df(comentarios: pd.DataFrame) -> pd.DataFrame:
    df = comentarios.copy()
    df["tipo_intencao"] = df["texto"].map(classificar)
    df["tem_intencao"] = df["tipo_intencao"].isin(TIPOS_COM_INTENCAO)
    return df


def intencao_por_post(comentarios: pd.DataFrame) -> pd.DataFrame:
    """Agrega por post: comentários lidos, quantos têm intenção e a taxa.

    A taxa é aplicada sobre o total de comentários do post no EQ, porque a API
    devolve uma amostra (os mais relevantes) e não todos.
    """
    df = classificar_df(comentarios)
    g = df.groupby(["post_id", "plataforma"])
    return pd.DataFrame({
        "comentarios_lidos": g.size(),
        "comentarios_com_intencao_lidos": g["tem_intencao"].sum(),
        "marcacoes_lidas": g["tipo_intencao"].apply(lambda s: (s == "marcacao").sum()),
    }).assign(taxa_intencao=lambda d: d["comentarios_com_intencao_lidos"] / d["comentarios_lidos"]).reset_index()
