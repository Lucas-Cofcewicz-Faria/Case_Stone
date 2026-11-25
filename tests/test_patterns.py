import numpy as np
import pandas as pd

from stone.evaluator import _auc, avaliar, marcar_top_perfil, treinar
from stone.patterns import atributos, calcular_lift


def _rub(**kw):
    base = {"formato_video": "tutorial", "tipo_hook": "pergunta", "tema_principal": "vendas",
            "tem_rosto": True, "tem_cta": False, "forca_hook_0a10": 8, "clareza_mensagem_0a10": 5}
    base.update(kw)
    return base


def test_atributos_categoricos_booleanos_e_faixas():
    a = atributos(_rub())
    assert "formato_video=tutorial" in a and "tem_rosto" in a and "tem_cta" not in a
    assert "forca_hook_0a10=alta" in a and "clareza_mensagem_0a10=baixa" in a


def _base(n=200, seed=1):
    rng = np.random.default_rng(seed)
    linhas = []
    for i in range(n):
        pergunta = i % 2 == 0
        conversa = rng.uniform(0, 1) + (2 if pergunta and rng.uniform() < .6 else 0)
        rub = _rub(tipo_hook="pergunta" if pergunta else "promessa")
        linhas.append({"post_id": str(i), "handle": f"h{i % 10}", "plataforma": "youtube", "rankeavel": True,
                       "conversa": conversa, "titulo": f"t{i}", "url": f"u{i}", "nome": f"h{i % 10}",
                       "atributos": atributos(rub), **rub})
    df = pd.DataFrame(linhas)
    df["top10"] = df["conversa"] >= df["conversa"].quantile(.9)
    return marcar_top_perfil(df)


def test_lift_acha_o_atributo_plantado():
    lift = calcular_lift(_base()).set_index("atributo")
    assert lift.loc["tipo_hook=pergunta", "tipo"] == "padrao"
    assert lift.loc["tipo_hook=promessa", "lift"] < 1


def test_avaliador_da_nota_maior_e_sugere_a_troca():
    m = treinar(_base())
    bom, ruim = avaliar(m, _rub(tipo_hook="pergunta")), avaliar(m, _rub(tipo_hook="promessa"))
    assert bom["nota"] > ruim["nota"]
    assert any(s["campo"] == "tipo_hook" and s["para"] == "pergunta" for s in ruim["sugestoes"])
    assert bom["referencias"] and "aviso" in bom


def test_auc():
    assert _auc(np.array([1, 1, 0, 0]), np.array([.9, .8, .2, .1])) == 1.0
    assert _auc(np.array([1, 0]), np.array([.1, .9])) == 0.0


def test_post_sem_conteudo_tira_zero():
    m = treinar(_base())
    vazio = _rub(tipo_hook="sem_gancho", forca_hook_0a10=0, clareza_mensagem_0a10=0, tema_principal="outro")
    av = avaliar(m, vazio)
    assert av["nota"] == 0 and av["sem_conteudo"] and av["motivo"]


def test_ausencia_nunca_soma_credito():
    from stone.evaluator import AUSENCIAS, pesos
    df = _base()
    # planta "sem gancho" no top: mesmo com lift alto, o peso fica <= 0
    df.loc[df["top10"], "atributos"] = df.loc[df["top10"], "atributos"].map(lambda s: s | {"tipo_hook=sem_gancho"})
    w = pesos(df, "top10")
    assert all(w.loc[a, "peso"] <= 0 for a in AUSENCIAS if a in w.index)
