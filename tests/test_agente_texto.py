from stone.agente.grafo import _ordem, problemas_texto

BOM = {
    "titulo": "Quanto cobrar por um bolo de aniversário?",
    "texto_na_tela": "Seu preço paga seu tempo?",
    "legenda": "Muita confeiteira cobra só o ingrediente. Faz a conta comigo no vídeo. "
               "Comenta TABELA que eu te mando a planilha.",
    "roteiro": ["Close nas mãos decorando o bolo. Fala: Sabe quanto cobrar por esse?",
                "Mesa com ingredientes e calculadora. Fala: soma o leite, o chocolate e a embalagem.",
                "Relógio na parede. Fala: e as quatro horas que você passou aqui?"],
}


def test_criativo_limpo_nao_tem_problemas():
    assert problemas_texto(BOM) == []


def test_pega_cenas_repetidas_e_pecas_copiadas():
    ruim = {
        "titulo": "Bolo de aniversário que a gente NÃO pode deixar de fazer!",
        "texto_na_tela": "Bolo de aniversário que a gente NÃO pode deixar de fazer!",
        "legenda": "Bolo de aniversário que a gente NÃO pode deixar de fazer! 🎂",
        "roteiro": ["Corta o bolo com a faca de bolo, põe a cobertura e o recheio.",
                    "Faz o bolo com a cobertura e o recheio.",
                    "Faz o bolo com a cobertura e o recheio."],
    }
    p = " | ".join(problemas_texto(ruim))
    assert "cenas repetidas" in p
    assert "texto na tela repete o título" in p
    assert "legenda só repete o título" in p
    assert "não tem falas" in p


def test_monologo_conta_como_fala():
    monologo = dict(BOM, roteiro=["Oi, artesã! Hoje eu vou te mostrar como resolvi a nota fiscal.",
                                  "A gente sabe que o MEI precisa emitir nota.",
                                  "Me conta nos comentários como você faz hoje."])
    assert problemas_texto(monologo) == []
    mudo = dict(BOM, roteiro=["Close nas mãos decorando o bolo.", "Mesa com ingredientes e calculadora.",
                              "Bolo pronto na vitrine."])
    assert any("não tem falas" in p for p in problemas_texto(mudo))


def test_versao_aprovada_vence_nota_maior_com_problema():
    aprovada = {"nota": 64, "problemas": []}
    com_problema = {"nota": 80, "problemas": ["cenas repetidas"]}
    baixa_limpa = {"nota": 40, "problemas": []}
    assert _ordem(aprovada) > _ordem(com_problema)
    assert _ordem(baixa_limpa) > _ordem(com_problema)
    assert _ordem({"nota": 70, "problemas": []}) > _ordem(aprovada)


def test_problema_leve_nao_derruba_nota_maior():
    capa_longa = {"nota": 73, "problemas": ["o texto na tela repete o título: escreva outra frase curta para a capa"]}
    assert _ordem(capa_longa) > _ordem({"nota": 34, "problemas": []})


def test_duracao_vem_das_falas_nao_do_numero_declarado():
    from stone.agente.grafo import estimar_duracao
    curto = ["Close no bolo. Fala: Quanto você cobra por esse?",
             "Mesa com notas. Fala: Soma tudo, até a embalagem.",
             "Rosto da confeiteira. Fala: Comenta TABELA que eu te mando."]
    assert estimar_duracao(curto) <= 15
    longo = ["Fala: " + "palavra " * 100, "Fala: " + "palavra " * 100]
    assert 70 <= estimar_duracao(longo) <= 90
    assert estimar_duracao(["Fala: " + "x " * 1000]) == 180


def test_ausencias_nunca_aparecem_como_padrao_a_seguir():
    from stone.agente import ferramentas as F
    from stone.evaluator import AUSENCIAS
    for seg in [None, "alimentacao", "beleza", "servicos_e_outros"]:
        p = F.padroes(seg)
        for v in ("top10", "top_perfil"):
            assert not {x["atributo"] for x in p[v]["fazer"]} & AUSENCIAS


def test_restricao_inventada_nao_entra_e_imagem_vira_frase():
    from stone.agente.grafo import _frase, _restricoes
    pedido = "Post do Impulso p/ dono de food truck: caixa some todo mês; tom empático, CTA claro, máx. 30s."
    assert _restricoes({"restricoes": "tom empático, CTA claro, máx. 30s"}, pedido)
    assert _restricoes({"restricoes": "não é varejo, nem contabilidade, nem pagamentos"}, pedido) == ""
    assert _frase("predio-com-portaria") == "Predio com portaria"


def test_impulso_como_app_e_problema_grave_e_fala_repetida_sai():
    from stone.agente.grafo import _limpar_fala, graves
    cr = dict(BOM, gancho="Você sabe quanto cobrar?", cta="Comenta TABELA",
              roteiro=BOM["roteiro"] + ["Dona abrindo o app do Impulso Stone. Fala: olha esse botão"])
    assert any("app" in p for p in graves(problemas_texto(cr)))
    assert problemas_texto(dict(BOM, gancho="Oi", cta="Comenta")) == []
    assert _limpar_fala("Dois faltaram hoje. Fala: Dois faltaram hoje.") == "Dois faltaram hoje."
