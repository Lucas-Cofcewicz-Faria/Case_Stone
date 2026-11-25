"""Rubrica de categorização (TAPI 6.2), preenchida pelo VLM com JSON garantido.

Campos que dá para calcular dos dados (tipo_post, duracao_faixa, legenda_tamanho)
são calculados em código, não pelo modelo. O modelo só preenche o que exige
leitura de imagem e texto. Campos que dependem do vídeo (ritmo de cortes, os 3s
iniciais falados) ficam para o nível 2, com frames e transcrição.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PROMPT_VERSAO = "rubrica-v2"

FormatoVideo = Literal["talking_head", "tutorial", "bastidores", "antes_depois", "humor_esquete",
                       "depoimento", "lista_dicas", "trend", "noticia_explicacao", "outro"]
TipoHook = Literal["pergunta", "promessa", "dor", "numero", "polemica", "curiosidade", "sem_gancho"]
Tema = Literal["vendas", "financas", "marketing", "atendimento", "gestao", "motivacao",
               "ferramentas_maquininha", "historia_de_empreendedor", "burocracia_mei", "outro"]
PilarImpulso = Literal["educacao_financeira", "gestao_e_vendas", "historias_reais", "especialistas",
                       "comunidade", "nenhum"]
Tom = Literal["informal", "tecnico", "inspiracional", "humoristico"]
TipoCTA = Literal["comentar", "salvar", "link_na_bio", "dm", "seguir", "compartilhar", "participar",
                  "comprar", "nenhum"]


class RubricaVLM(BaseModel):
    """O que o modelo preenche. A ordem dos campos guia o raciocínio do modelo."""
    descricao_visual: str = Field(description="1 frase: o que aparece na imagem (pessoas, cenário, texto).")
    texto_na_tela: str = Field(description="Texto escrito na imagem, transcrito. Vazio se não houver.")
    formato_video: FormatoVideo
    hook_primeiros_3s: str = Field(description="Frase de abertura copiada do título ou do texto da capa (palavras, nunca número).")
    tipo_hook: TipoHook
    forca_hook_0a10: int = Field(ge=0, le=10)
    tema_principal: Tema
    pilar_impulso: PilarImpulso
    tem_rosto: bool
    criador_e_empreendedor_real: bool = Field(description="A pessoa mostra o próprio negócio (loja, cozinha, salão).")
    prova_social: bool = Field(description="Mostra resultado, número, cliente ou depoimento real.")
    tom: Tom
    usa_linguagem_regional: bool
    clareza_mensagem_0a10: int = Field(ge=0, le=10)
    tem_cta: bool
    tipo_cta: TipoCTA
    oferta_ou_beneficio_explicito: bool
    elementos_top5: list[str] = Field(min_length=1, max_length=5,
                                      description="Os até 5 elementos que mais explicam o post, curtos.")


SISTEMA = """Você é um analista de conteúdo para micro e pequenos empreendedores (MPEs) brasileiros.
Recebe a capa (thumbnail) de um vídeo curto e o texto do post. Classifica o post numa rubrica fixa.
Responda só com o JSON pedido, em português. Baseie-se apenas na imagem e no texto; não invente.

formato_video (escolha o mais específico):
- talking_head: pessoa falando para a câmera, opinião ou conselho
- tutorial: ensina um passo a passo ("como fazer", cálculo, configuração)
- lista_dicas: N dicas, erros ou itens ("3 erros", "5 dicas")
- noticia_explicacao: explica uma notícia, regra ou mudança (lei, imposto, MEI, Pix)
- depoimento: cliente ou empreendedor conta a própria experiência
- bastidores: mostra a rotina ou o negócio funcionando (cozinha, loja, salão)
- antes_depois: compara um antes e um depois
- humor_esquete: cena encenada ou piada
- trend: SÓ se usar um áudio, formato ou meme viral conhecido
- outro

tipo_hook: pergunta ("Você sabe...?"), promessa ("Como vender o dobro"), dor ("Seu dinheiro some?"),
numero ("3 erros..."), polemica ("Ninguém te conta..."), curiosidade (mistério sem pergunta), sem_gancho.
forca_hook_0a10: 0 = sem gancho; 5 = comum; 8 = forte e específico para o público; 10 = raríssimo. Use a escala toda.

tema_principal: vendas, financas (preço, caixa, lucro, crédito), marketing (redes, anúncio),
atendimento, gestao (equipe, processo, estratégia), motivacao (frase inspiracional genérica),
ferramentas_maquininha (SÓ maquininha, taxa de cartão, conta PJ, app de pagamento),
historia_de_empreendedor, burocracia_mei (MEI, CNPJ, imposto, nota fiscal, declaração), outro.

pilar_impulso: educacao_financeira (precificação, custos, caixa, lucro); gestao_e_vendas (atendimento,
pós-venda, estratégia comercial); historias_reais (trajetórias); especialistas (oficina, mentoria);
comunidade (convite, interação, oportunidade); nenhum.

tem_cta: true só se o texto ou a imagem pedirem uma ação explícita. "comenta EU QUERO" = tipo_cta comentar.
"""


def montar_prompt(titulo: str | None, legenda: str | None, plataforma: str, duracao_s: int | None) -> str:
    legenda = (legenda or "").strip()
    if len(legenda) > 1500:
        legenda = legenda[:1500] + " […]"
    return (f"Plataforma: {plataforma}\n"
            f"Duração: {duracao_s if duracao_s is not None else 'desconhecida'} s\n"
            f"Título: {titulo or '(sem título)'}\n"
            f"Legenda/descrição:\n{legenda or '(vazia)'}\n\n"
            "Classifique este post na rubrica.")


def normalizar_hook(rub: dict) -> dict:
    """Gancho que abre com pergunta é `pergunta`, mesmo quando o assunto é uma dor.

    O exemplo de `dor` no prompt ("Seu dinheiro some?") também é pergunta, então o modelo às vezes
    troca um pelo outro. Na base, aberturas terminadas em "?" saíram `pergunta` 1.045 vezes e `dor` 29:
    a regra fixa a convenção da maioria e vale igual para a base e para os rascunhos.
    """
    if rub.get("tipo_hook") == "dor" and str(rub.get("hook_primeiros_3s") or "").strip().endswith("?"):
        return {**rub, "tipo_hook": "pergunta"}
    return rub


def duracao_faixa(segundos: int | None) -> str | None:
    if segundos is None:
        return None
    for limite, nome in [(15, "ate_15s"), (30, "15_30s"), (60, "30_60s"), (180, "60_180s")]:
        if segundos <= limite:
            return nome
    return "mais_180s"


def legenda_tamanho(texto: str | None) -> str:
    n = len((texto or "").split())
    return "vazia" if n == 0 else "curta" if n <= 30 else "media" if n <= 120 else "longa"
