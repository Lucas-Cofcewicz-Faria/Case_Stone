"""Agente de criativos (LangGraph): entende o pedido, busca padrões e referências, gera,
avalia e revisa se a nota ficar baixa, e responde com justificativa e aviso de confiança.

  entender → padroes → referencias → gerar → avaliar ─(nota baixa ou texto com problema, até MAX)→ gerar
                                                    └──────────────────────────────────→ responder

Uso:
  python -m stone.agente.grafo "Post do Impulso para confeiteiras que vendem bolo por encomenda"
"""
from __future__ import annotations

import json
import re
import sys
import time
import unicodedata
from typing import Literal, TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from ..config import DATA
from ..llm import gerar_json
from ..rubric import FormatoVideo, TipoCTA, TipoHook
from . import ferramentas as F

# o tema e o pilar vêm do pedido: o avaliador pode sugerir trocar, mas o agente não muda o assunto do negócio
CAMPOS_FIXOS = {"tema_principal", "pilar_impulso", "legenda_tamanho", "duracao_faixa"}
PALAVRAS_POR_S = 2.5   # fala em português, ~150 palavras por minuto
NOTA_MIN = 60          # abaixo disso o agente revisa
MAX_TENTATIVAS = 3
LOG = DATA / "logs" / "agente.jsonl"

# "servicos_e_outros" não tem recorte na base: usa os padrões e referências da base inteira
Segmento = Literal[tuple(F.SEGMENTOS) + (F.SEM_SEGMENTO,)]  # type: ignore[valid-type]


class Plano(BaseModel):
    segmento: Segmento
    negocio: str = Field(description="O tipo de negócio dos empreendedores que o post quer alcançar, "
                                     "em poucas palavras (ex.: confeitaria por encomenda).")
    objetivo: str = Field(description="O que o post deve provocar nesses empreendedores: comentar uma dúvida, "
                                      "pedir um material, contar a própria experiência, se inscrever.")
    publico: str = Field(description="Os EMPREENDEDORES desse segmento que devem se reconhecer no post, com a dor "
                                     "do dia a dia (ex.: confeiteiras que vendem em casa e não sabem quanto cobrar).")
    problema: str = Field(description="O problema ou objetivo ESPECÍFICO do pedido, com as palavras do pedido "
                                      "(ex.: 'atender os prédios da região', 'agenda vazia na terça e na quarta'). "
                                      "É o assunto central do post.")
    restricoes: str = Field(description="Exigências explícitas do pedido (duração máxima, tom, CTA, elementos "
                                        "obrigatórios), copiadas do pedido. Vazio se não houver.")


class Cena(BaseModel):
    o_que_aparece: str = Field(description="Uma frase com palavras separadas por espaço: pessoa, lugar ou objeto "
                                           "do dia a dia do negócio (ex.: 'Close nas mãos da confeiteira decorando "
                                           "o bolo'). Nunca uma tela de app do Impulso ou da Stone.")
    fala: str = Field(description="O que a pessoa diz nesta cena, entre 1 e 3 frases, uma vez só.")


class Criativo(BaseModel):
    titulo: str = Field(description="Título do vídeo curto, como apareceria no feed.")
    gancho: str = Field(description="Frase falada ou escrita nos primeiros 3 segundos.")
    tipo_hook: TipoHook
    formato: FormatoVideo
    duracao_s: int = Field(ge=10, le=180)
    roteiro: list[Cena] = Field(min_length=3, max_length=7,
                                description="Cenas em ordem; cada uma mostra e diz algo NOVO e avança a mensagem.")
    texto_na_tela: str = Field(description="Texto da capa, no máximo 8 palavras. Diferente do título.")
    legenda: str = Field(description="Legenda do post (2–4 frases), com a chamada para ação no fim. "
                                     "NÃO repita o roteiro nem o texto na tela.")
    cta: str = Field(description="A ação pedida, literal (ex.: 'Comenta QUERO que eu te mando a tabela').")
    tipo_cta: TipoCTA
    justificativa: str = Field(description="2–3 frases ligando as escolhas aos padrões e referências recebidos.")


class Estado(TypedDict, total=False):
    pedido: str
    plano: dict
    padroes: dict
    referencias: list[dict]
    criativo: dict
    avaliacao: dict
    tentativas: int
    melhor: dict           # {"criativo", "avaliacao"} com a maior nota até agora
    historico: list[dict]
    resposta: str


SISTEMA_PLANO = """Você planeja vídeos curtos (Shorts/Reels) do Impulso Stone, o programa da Stone que apoia
micro e pequenos empreendedores brasileiros. O pedido diz QUAIS empreendedores o post quer alcançar
(ex.: "confeitaria por encomenda" = donos de confeitaria por encomenda). Leia o pedido e extraia o plano.
Classifique o segmento pelo TIPO DE NEGÓCIO desses empreendedores, não pela forma jurídica
(ser MEI não faz o negócio ser de contabilidade). Segmentos:
- alimentacao: comida e bebida (confeitaria, restaurante, lanchonete, marmita, pizzaria)
- beleza: salão, barbearia, estética, manicure, maquiagem
- varejo_e_vendas: loja física ou online que revende produtos
- mei_e_contabilidade: só quando o negócio É contabilidade, abertura de empresa ou burocracia
- pagamentos: só quando o negócio É de maquininha ou conta PJ
- gestao_e_financas: só quando o negócio É consultoria de gestão ou educação financeira
- artesanato_e_festas: artesanato, decoração de festas, bolo fake, lembrancinhas
- servicos_e_outros: serviços locais e o que não couber acima (lavanderia, oficina mecânica,
  manutenção de ar-condicionado, academia, pet shop, eletricista, conserto)
Responda só com o JSON."""

SISTEMA_CRIATIVO = """Você é roteirista de vídeos curtos do Impulso Stone, o programa da Stone que apoia
micro e pequenos empreendedores brasileiros. O vídeo é publicado pelo Impulso e fala com os EMPREENDEDORES
do segmento do plano (o público), não com os clientes deles. Parta do PROBLEMA CENTRAL do plano, como ele
aparece no dia a dia desse negócio, e entregue algo útil e concreto sobre ele (um passo prático ou um
exemplo da rotina). Pode citar o Impulso como quem ensina, sem virar anúncio de produto.
NÃO invente apps, telas, botões, funções, taxas, preços ou regras (da Stone, do Impulso ou do governo): o
Impulso é um programa de conteúdo e capacitação, não um aplicativo, e não aparece como tela no vídeo.
Não faça contas nem cite porcentagens: o vídeo ensina o passo, quem comenta pede o cálculo.
Fatos que valem: todo MEI paga o DAS, um valor fixo por mês, mesmo sem vender ou vendendo pouco (não é cobrado
por venda); o MEI emite a nota de serviço de graça pelo Emissor Nacional do governo (emitir nota não tem taxa).
Se o roteiro promete mostrar algo (uma lista, um passo a passo), mostre de fato.
O ASSUNTO do post é o problema do plano: não troque por outro tema (nota do MEI, preço, DAS) que o pedido
não citou. Siga as exigências do pedido (duração máxima, tom, CTA).
O objetivo NÃO é viralizar nem ganhar curtidas: é fazer a pessoa COMENTAR, PERGUNTAR ou PEDIR algo
(engajamento qualificado). Use os padrões da base (o que aparece mais nos posts que geram conversa),
evite os antipadrões e inspire-se nas referências sem copiar. Fale como o empreendedor fala, em português do Brasil.
O CTA precisa pedir uma ação concreta e fácil de comentar. Título, texto na tela, roteiro e legenda
são peças DIFERENTES: não copie a mesma frase entre eles. Responda só com o JSON."""


def _log(evento: str, dados: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "evento": evento, **dados},
                           ensure_ascii=False, default=str) + "\n")


def _palavras(texto: str) -> set[str]:
    sem_acento = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
    return set(re.findall(r"[a-z0-9]{3,}", sem_acento))


def _parecidos(a: str, b: str, limite: float = 0.75) -> bool:
    """Quase a mesma frase: a maior parte das palavras da mais curta aparece na outra."""
    pa, pb = _palavras(a), _palavras(b)
    return bool(pa and pb) and len(pa & pb) / min(len(pa), len(pb)) >= limite


def problemas_texto(cr: dict) -> list[str]:
    """Checagem de texto independente do avaliador. O modelo de 8B às vezes repete cenas ou copia a
    mesma frase em várias peças, e a rubrica não pune isso. Cada problema vira motivo de revisão."""
    out = []
    cenas = cr["roteiro"]
    if any(_parecidos(cenas[i], cenas[j], 0.8) for i in range(len(cenas)) for j in range(i + 1, len(cenas))):
        out.append("há cenas repetidas no roteiro: cada cena precisa mostrar e dizer algo novo")
    if _parecidos(cr["texto_na_tela"], cr["titulo"]):
        out.append("o texto na tela repete o título: escreva outra frase curta para a capa")
    if _parecidos(cr["legenda"], cr["titulo"]) and len(_palavras(cr["legenda"])) <= len(_palavras(cr["titulo"])) + 4:
        out.append("a legenda só repete o título: escreva 2 a 4 frases novas que terminem no pedido")
    if len(cr["texto_na_tela"].split()) > 10:
        out.append("o texto na tela passa de 8 palavras")
    if len(cr["legenda"].split()) > 70:
        out.append("a legenda está longa: 2 a 4 frases curtas, o vídeo explica e a legenda só pede a ação")
    # fala = marcador explícito, aspas, dois-pontos, ou cena escrita como monólogo (você / eu / a gente / oi)
    fala = r"fala|narra|diz|pergunta|[\"'“:]|\b(voc[eê]|eu|a gente|oi)\b"
    if not any(re.search(fala, c, re.I) for c in cenas):
        out.append("o roteiro não tem falas: diga o que a pessoa fala em cada cena")
    # o 8B inventava "app do Impulso" com telas e botões (rodada 2 das evals): o Impulso não é aplicativo
    tudo = " ".join([*(str(cr.get(k, "")) for k in ("titulo", "gancho", "legenda", "cta")), *cenas])
    if re.search(r"\b(app|aplicativo|tela|bot[aã]o)\s+(d[oa]\s+)?(impulso|stone)\b", tudo, re.I):
        out.append("o post mostra o Impulso como app (tela, botão): o Impulso é um programa de conteúdo")
    return out


def _limpar_fala(fala: str) -> str:
    """'X. Fala: X' → 'X': o 8B às vezes repete a fala inteira dentro do mesmo campo."""
    partes, vistas = [], set()
    for p in re.split(r"\s*\bFala\s*:\s*", fala.strip(), flags=re.I):
        chave = " ".join(p.lower().split())[:60]
        if p.strip() and chave not in vistas:
            vistas.add(chave)
            partes.append(p.strip())
    return " ".join(partes)


def _frase(texto: str) -> str:
    """'predio-com-portaria' → 'Predio com portaria': às vezes o 8B escreve a imagem como nome de arquivo."""
    t = texto.strip().rstrip(".")
    if " " not in t:
        t = re.sub(r"[-_]+", " ", t)
    return t[:1].upper() + t[1:]


def _restricoes(plano: dict, pedido: str) -> str:
    """Só vale se foi copiada do pedido: o 8B às vezes preenche o campo com texto que o pedido não tem."""
    r = (plano.get("restricoes") or "").strip()
    pr = _palavras(r)
    return r if pr and len(pr & _palavras(pedido)) / len(pr) >= 0.6 else ""


def estimar_duracao(roteiro: list[str]) -> int:
    """Duração pelo que é FALADO, não pelo número que o modelo declara.

    A faixa de duração pesa muito na nota (15–30 s ≈ 25, 60–180 s ≈ 68 com o resto igual) e o modelo declarava
    120 s em quase tudo. Conta as palavras das falas (depois de "Fala:"/"Narra:" ou entre aspas; sem marcador,
    metade da cena) a ~2,5 palavras/s, com pelo menos 3 s por cena."""
    palavras = 0
    for cena in roteiro:
        m = re.search(r"(?:fala|narra\w*|diz)\s*:\s*(.+)", cena, re.I | re.S)
        aspas = re.findall(r"[\"“'‘]([^\"”'’]{3,})[\"”'’]", cena)
        if m:
            palavras += len(m.group(1).split())
        elif aspas:
            palavras += sum(len(a.split()) for a in aspas)
        else:
            palavras += len(cena.split()) // 2
    return int(min(180, max(10, round(palavras / PALAVRAS_POR_S), 3 * len(roteiro))))


class Capa(BaseModel):
    texto_na_tela: str = Field(description="Frase da capa com 3 a 7 palavras, diferente do título.")


class Legenda(BaseModel):
    legenda: str = Field(description="2 ou 3 frases curtas (até 45 palavras no total), sem repetir o título, "
                                     "terminando no pedido de comentário.")


SISTEMA_ACABAMENTO = """Você revisa uma peça de um post curto do Impulso Stone para empreendedores.
Reescreva só o campo pedido, em português do Brasil, no mesmo tom do post. Responda só com o JSON."""


def acabamento(cr: dict) -> dict:
    """Conserta capa e legenda com uma chamada curta e focada (~5 s), sem reescrever o criativo inteiro.
    Numa revisão completa o modelo de 8B quase nunca conserta esses dois campos."""
    cr = dict(cr)
    if _parecidos(cr["texto_na_tela"], cr["titulo"]) or len(cr["texto_na_tela"].split()) > 10:
        capa, _ = gerar_json(Capa, SISTEMA_ACABAMENTO,
                             f"Título do post: {cr['titulo']}\nGancho: {cr['gancho']}\n"
                             f"Capa atual (longa ou igual ao título): {cr['texto_na_tela']}\n"
                             "Escreva uma capa nova de 3 a 7 palavras que NÃO repita o título.",
                             versao="agente-capa-v1")
        cr["texto_na_tela"] = capa.texto_na_tela
    legenda_copia = (_parecidos(cr["legenda"], cr["titulo"])
                     and len(_palavras(cr["legenda"])) <= len(_palavras(cr["titulo"])) + 4)
    if legenda_copia or len(cr["legenda"].split()) > 70:
        leg, _ = gerar_json(Legenda, SISTEMA_ACABAMENTO,
                            f"Título do post: {cr['titulo']}\nPedido no fim (CTA): {cr['cta']}\n"
                            f"Legenda atual (longa ou igual ao título): {cr['legenda']}\n"
                            "Escreva uma legenda nova de 2 ou 3 frases curtas que termine no pedido.",
                            versao="agente-legenda-v1")
        cr["legenda"] = leg.legenda
    return cr


def _legivel(attr: str) -> str:
    return attr.replace("=", ": ").replace("_", " ")


def entender(s: Estado) -> Estado:
    plano, _ = gerar_json(Plano, SISTEMA_PLANO, s["pedido"], versao="agente-plano-v5")
    _log("entender", {"pedido": s["pedido"], "plano": plano.model_dump()})
    return {"plano": plano.model_dump(), "tentativas": 0, "historico": []}


def buscar_padroes(s: Estado) -> Estado:
    p = F.padroes(s["plano"]["segmento"])
    _log("padroes", {"segmento": p["segmento"], "fonte": p["fonte_dos_padroes"], "confianca": p["confianca"]})
    return {"padroes": p}


def buscar_referencias(s: Estado) -> Estado:
    refs = F.referencias(s["plano"]["segmento"], n=5, texto=s["plano"]["negocio"])
    _log("referencias", {"n": len(refs), "ids": [r["post_id"] for r in refs]})
    return {"referencias": refs}


# o assunto vem do pedido e a duração sai das falas (estimar_duracao): esses padrões não entram no prompt,
# senão o modelo troca o problema do pedido pelo tema que mais pontua (nota do MEI) e declara 120 s em tudo
FORA_DO_PROMPT = ("tema_principal=", "pilar_impulso=", "duracao_faixa=")


def _prompt_criativo(s: Estado) -> str:
    p, pl = s["padroes"], s["plano"]
    def lista(chave):
        return sorted({_legivel(x["atributo"]) for v in ("top10", "top_perfil") for x in p[v][chave]
                       if not x["atributo"].startswith(FORA_DO_PROMPT)})
    fazer, evitar = lista("fazer"), lista("evitar")
    refs = "\n".join(f"- \"{r['titulo']}\" ({r['nome']}, {r['conversa']} comentários por mil views; "
                     f"gancho: {r.get('hook_primeiros_3s')})" for r in s["referencias"])
    partes = [f"Negócio: {pl['negocio']}\nPROBLEMA CENTRAL (o assunto do post): {pl.get('problema') or pl['objetivo']}\n"
              f"Objetivo: {pl['objetivo']}\nPúblico: {pl['publico']}"
              + (f"\nExigências do pedido: {_restricoes(pl, s['pedido'])}" if _restricoes(pl, s["pedido"]) else ""),
              f"Padrões que aparecem mais nos posts que geram conversa: {', '.join(fazer) or 'nenhum claro'}",
              f"Antipadrões (aparecem menos): {', '.join(evitar) or 'nenhum claro'}",
              f"Referências reais do segmento:\n{refs or '(sem referências)'}"]
    if s.get("avaliacao"):
        av, cr = s["avaliacao"], s["criativo"]
        sug = "; ".join(f"{_legivel(x['campo'])}: trocar {x['de']} por {x['para']}" for x in av["sugestoes"]
                        if x["campo"] not in CAMPOS_FIXOS)
        anti = ", ".join(_legivel(x["atributo"]) for x in av["antipadroes"])
        probs = "; ".join(av.get("problemas", []))
        motivo = f"nota {av['nota']}/100" + (f", abaixo de {NOTA_MIN}" if av["nota"] < NOTA_MIN else "")
        partes.append(f"VERSÃO ANTERIOR ({motivo}):\n{json.dumps(cr, ensure_ascii=False)}\n"
                      + (f"Problemas de texto que PRECISAM sair: {probs}.\n" if probs else "")
                      + f"Ajustes sugeridos pelo avaliador: {sug or 'nenhum'}. "
                      f"Antipadrões presentes: {anti or 'nenhum'}. Escreva uma versão NOVA aplicando os ajustes: "
                      "título, texto na tela e legenda com frases diferentes das anteriores, "
                      "sem perder a clareza da mensagem nem o negócio do pedido.")
    return "\n\n".join(partes) + "\n\nEscreva o criativo."


def gerar(s: Estado) -> Estado:
    n = s.get("tentativas", 0) + 1
    # a 1ª versão é reproduzível; nas revisões, um pouco de temperatura evita que o modelo copie a anterior
    amostra = {} if n == 1 else {"temperatura": 0.6, "seed": 42 + n}
    prompt = _prompt_criativo(s)
    # penalidade de repetição leve: sem ela o modelo de 8B às vezes repete a mesma cena até o fim do roteiro.
    # Forte demais, ela pune aspas e vírgulas do JSON e a resposta não fecha; aí cai para a chamada sem penalidade.
    try:
        cr, meta = gerar_json(Criativo, SISTEMA_CRIATIVO, prompt, versao=f"agente-criativo-v8-t{n}",
                              opcoes={"repeat_penalty": 1.08, "repeat_last_n": 128}, num_predict=1536,
                              tentativas=1, **amostra)
    except RuntimeError:
        cr, meta = gerar_json(Criativo, SISTEMA_CRIATIVO, prompt, versao=f"agente-criativo-v8-t{n}", **amostra)
    bruto = cr.model_dump()
    # o schema separa imagem e fala (o 8B escrevia só a fala); o resto do sistema segue com uma string por cena
    bruto["roteiro"] = [f"{_frase(c['o_que_aparece'])}. Fala: {_limpar_fala(c['fala'])}" for c in bruto["roteiro"]]
    criativo = acabamento(bruto)
    criativo["duracao_declarada_s"] = criativo["duracao_s"]
    criativo["duracao_s"] = estimar_duracao(criativo["roteiro"])
    _log("gerar", {"tentativa": n, "segundos": meta["segundos"], "titulo": cr.titulo,
                   "acabamento": [k for k in ("texto_na_tela", "legenda") if criativo[k] != getattr(cr, k)]})
    return {"criativo": criativo, "tentativas": n}


def avaliar(s: Estado) -> Estado:
    cr = s["criativo"]
    av = F.avaliar_rascunho(cr["titulo"], f"{cr['texto_na_tela']}\n{cr['legenda']}",
                            "\n".join(cr["roteiro"]), cr["duracao_s"])
    av["problemas"] = problemas_texto(cr)
    av["graves"] = graves(av["problemas"])
    av["tentativa"] = s["tentativas"]
    hist = s.get("historico", []) + [{"tentativa": s["tentativas"], "nota": av["nota"], "titulo": cr["titulo"],
                                      "problemas": len(av["problemas"])}]
    melhor = s.get("melhor")
    if not melhor or _ordem(av) > _ordem(melhor["avaliacao"]):
        melhor = {"criativo": cr, "avaliacao": av}
    _log("avaliar", {"tentativa": s["tentativas"], "nota": av["nota"], "problemas": av["problemas"],
                     "sugestoes": [x["campo"] for x in av["sugestoes"]]})
    return {"avaliacao": av, "historico": hist, "melhor": melhor}


# capa e legenda longa são consertadas no acabamento; se sobrarem, só viram aviso ("revise antes de usar")
LEVES = ("o texto na tela", "a legenda está longa")


def graves(problemas: list[str]) -> list[str]:
    """Problemas que estragam o post (cenas repetidas, legenda copiada, roteiro sem fala)."""
    return [p for p in problemas if not p.startswith(LEVES)]


def _ordem(av: dict) -> tuple:
    """Qual versão entregar: aprovada (nota ≥ 60 e sem problema grave) > sem problema grave > maior nota."""
    limpo = not graves(av.get("problemas", []))
    return (limpo and av["nota"] >= NOTA_MIN, limpo, av["nota"])


def decidir(s: Estado) -> str:
    av = s["avaliacao"]
    revisar = av["nota"] < NOTA_MIN or bool(graves(av.get("problemas", [])))
    return "gerar" if revisar and s["tentativas"] < MAX_TENTATIVAS else "responder"


def responder(s: Estado) -> Estado:
    cr, av, p = s["melhor"]["criativo"], s["melhor"]["avaliacao"], s["padroes"]
    n_top = p["posts_top_no_segmento"]
    if s["plano"]["segmento"] == F.SEM_SEGMENTO:
        baixa = ("> Confiança baixa: este tipo de negócio não tem recorte na base, então os padrões usados "
                 "são os da base inteira.\n")
    else:
        baixa = (f"> Confiança baixa: o segmento tem só {n_top} {'post' if n_top == 1 else 'posts'} "
                 "no top 10% da base, então os padrões usados são os da base inteira.\n")
    aviso_conf = {"alta": "", "media": "", "baixa": baixa}[p["confianca"]]
    linhas = [f"# {cr['titulo']}", aviso_conf,
              f"**Gancho (0–3s):** {cr['gancho']}  ", f"**Formato:** {cr['formato']} · {cr['duracao_s']}s  ",
              f"**Texto na tela:** {cr['texto_na_tela']}", "", "**Roteiro**",
              *[f"{i}. {c}" for i, c in enumerate(cr["roteiro"], 1)], "",
              f"**Legenda:** {cr['legenda']}", "", f"**CTA:** {cr['cta']}", "",
              f"## Aderência: {av['nota']}/100",
              *([f"> Revise antes de usar: {'; '.join(av['problemas'])}.", ""] if av.get("problemas") else []),
              "Versões testadas: " + ", ".join(f"v{h['tentativa']} = {h['nota']}" for h in s["historico"]), "",
              "Padrões cumpridos: " + (", ".join(f"{_legivel(x['atributo'])} (lift {x['lift']})"
                                                 for x in av["padroes_cumpridos"]) or "nenhum padrão forte"),
              "Antipadrões: " + (", ".join(_legivel(x["atributo"]) for x in av["antipadroes"]) or "nenhum"), "",
              f"**Por quê:** {cr['justificativa']}", "", "## Referências reais (top 10% de conversa)",
              *[f"- [{r['titulo']}]({r['url']}) · {r['nome']} · {r['conversa']} por mil views" for r in s["referencias"]],
              "", f"_{av['aviso']}_"]
    texto = "\n".join(linhas)
    _log("responder", {"nota_final": av["nota"], "tentativas": s["tentativas"]})
    return {"resposta": texto}


def construir():
    g = StateGraph(Estado)
    for nome, fn in [("entender", entender), ("padroes", buscar_padroes), ("referencias", buscar_referencias),
                     ("gerar", gerar), ("avaliar", avaliar), ("responder", responder)]:
        g.add_node(nome, fn)
    g.set_entry_point("entender")
    g.add_edge("entender", "padroes")
    g.add_edge("padroes", "referencias")
    g.add_edge("referencias", "gerar")
    g.add_edge("gerar", "avaliar")
    g.add_conditional_edges("avaliar", decidir, {"gerar": "gerar", "responder": "responder"})
    g.add_edge("responder", END)
    return g.compile()


def rodar(pedido: str, callbacks: list | None = None) -> Estado:
    """callbacks: handlers do LangChain (ex.: o CallbackHandler do deepeval nas evals em tests/evals)."""
    return construir().invoke({"pedido": pedido}, config={"callbacks": callbacks} if callbacks else None)


if __name__ == "__main__":
    pedido = " ".join(sys.argv[1:]) or "Post do Impulso para confeiteiras que vendem bolo por encomenda"
    print(rodar(pedido)["resposta"])
