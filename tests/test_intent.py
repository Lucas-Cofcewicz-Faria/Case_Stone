import pandas as pd
import pytest

from stone.intent import classificar, intencao_por_post


@pytest.mark.parametrize("texto,tipo", [
    # contato / compra
    ("Qual o link?", "contato"),
    ("qual é o valor da mentoria", "contato"),
    ("Quanto custa essa maquininha?", "contato"),
    ("Quero!", "contato"),
    ("tenho interesse, me chama no direct", "contato"),
    ("onde compro essa planilha", "contato"),
    ("Vocês tem curso de precificação?", "contato"),
    # participação
    ("Como faço para participar?", "participacao"),
    ("Eu quero participar!! 🙋‍♀️", "participacao"),
    ("me inscrevi ontem", "participacao"),
    ("Eu quero", "contato"),
    # dúvida prática
    ("Como faço pra calcular o preço do bolo?", "duvida"),
    ("Isso serve pra MEI também?", "duvida"),
    ("posso emitir nota sendo MEI?", "duvida"),
    ("alguém sabe se a taxa muda no crédito", "duvida"),
    ("Preciso de ajuda", "duvida"),
    ("Preciso comprovante renda sou mei", "duvida"),
    ("E qdo compra fora do estado? Tem q pagar ICMS como oME?", "duvida"),
    ("Oi tudo bem? Você tem cursos de DRE e outros relatórios contabeis?", "contato"),
    # marcação
    ("@maria_doces olha isso", "marcacao"),
    # elogio / reação
    ("Top demais", "elogio"),
    ("👏👏👏", "elogio"),
    ("Parabéns pelo conteúdo", "elogio"),
    ("verdade", "elogio"),
    # outro
    ("Eu comecei vendendo na rua também", "outro"),
    ("", "outro"),
])
def test_classificar(texto, tipo):
    assert classificar(texto) == tipo


def test_marcacao_com_pergunta_vira_intencao():
    assert classificar("@joao como faço pra abrir o MEI?") == "duvida"


def test_intencao_por_post_agrega_taxa():
    df = pd.DataFrame([
        {"post_id": "a", "plataforma": "youtube", "texto": "qual o link?"},
        {"post_id": "a", "plataforma": "youtube", "texto": "top"},
        {"post_id": "a", "plataforma": "youtube", "texto": "@ana olha"},
        {"post_id": "a", "plataforma": "youtube", "texto": "como faço pra participar"},
        {"post_id": "b", "plataforma": "youtube", "texto": "amei"},
    ])
    out = intencao_por_post(df).set_index("post_id")
    assert out.loc["a", "comentarios_lidos"] == 4
    assert out.loc["a", "comentarios_com_intencao_lidos"] == 2
    assert out.loc["a", "marcacoes_lidas"] == 1
    assert out.loc["a", "taxa_intencao"] == pytest.approx(0.5)
    assert out.loc["b", "taxa_intencao"] == 0
