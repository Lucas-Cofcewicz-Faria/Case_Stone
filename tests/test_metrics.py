from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from stone.config import faixa_de
from stone.metrics import calcular, filtrar_maduros, sensibilidade


def _perfis(*itens):
    return pd.DataFrame([{"handle": h, "plataforma": "youtube", "seguidores": s} for h, s in itens])


def _post(pid, handle="p", curtidas=10, comentarios=0, views=1000, intencao=np.nan):
    return {"post_id": pid, "handle": handle, "plataforma": "youtube", "curtidas": curtidas,
            "comentarios": comentarios, "views": views, "comentarios_intencao": intencao}


def test_er_do_tapi_exemplo_da_aula():
    # Aula 1: A tem 1 mi e 10 mil curtidas (1%); B tem 5 mil e 500 curtidas (10%)
    posts = pd.DataFrame([_post("a", "grande", 10_000), _post("b", "micro", 500)])
    df = calcular(posts, _perfis(("grande", 1_000_000), ("micro", 5_000))).set_index("post_id")
    assert df.loc["a", "er"] == pytest.approx(0.01)
    assert df.loc["b", "er"] == pytest.approx(0.10)


def test_viral_sem_conversa_perde_para_post_com_conversa():
    # Caso real da base: 10 mi de views, 17 mil curtidas e 2 comentários num canal de 13,9 mil
    posts = pd.DataFrame([
        _post("viral", "allman", curtidas=17_222, comentarios=2, views=10_176_387, intencao=0),
        _post("conversa", "allman", curtidas=109, comentarios=40, views=1_211, intencao=20),
    ])
    df = calcular(posts, _perfis(("allman", 13_900))).set_index("post_id")
    assert df.loc["viral", "er"] > df.loc["conversa", "er"]          # ER premia o viral
    assert df.loc["conversa", "conversa"] > 100 * df.loc["viral", "conversa"]
    assert df.loc["conversa", "conversa"] == pytest.approx((40 + 2 * 20) / 1211 * 1000)


def test_curtidas_nao_entram_na_conversa():
    posts = pd.DataFrame([_post("1", curtidas=10, comentarios=5), _post("2", curtidas=9999, comentarios=5)])
    df = calcular(posts, _perfis(("p", 1000))).set_index("post_id")
    assert df.loc["1", "conversa"] == df.loc["2", "conversa"]


def test_minimo_de_views_para_rankear():
    posts = pd.DataFrame([_post("pouco", comentarios=10, views=200), _post("ok", comentarios=1, views=300)])
    df = calcular(posts, _perfis(("p", 1000))).set_index("post_id")
    assert not df.loc["pouco", "rankeavel"] and not df.loc["pouco", "top10"]
    assert df.loc["ok", "rankeavel"]


def test_curtidas_ocultas_ficam_fora_do_er_mas_nao_da_conversa():
    posts = pd.DataFrame([_post("x", curtidas=None, comentarios=10)])
    df = calcular(posts, _perfis(("p", 1000))).set_index("post_id")
    assert not df.loc["x", "rankeavel_er"]
    assert df.loc["x", "rankeavel"]


def test_top10_respeita_limite_por_perfil():
    # "dominante" tem os 20 melhores posts; com limite 3, as outras vagas vão para os demais
    posts = [_post(f"d{i}", "dominante", comentarios=100 + i) for i in range(20)]
    posts += [_post(f"o{i}", f"outro{i % 8}", comentarios=i) for i in range(80)]
    perfis = _perfis(("dominante", 1000), *[(f"outro{i}", 1000) for i in range(8)])
    df = calcular(pd.DataFrame(posts), perfis, max_por_perfil=3)
    top = df[df["top10"]]
    assert len(top) == 10
    assert (top["handle"] == "dominante").sum() == 3
    assert set(top.loc[top["handle"] == "dominante", "post_id"]) == {"d19", "d18", "d17"}


def test_top10_sem_limite_pega_os_10_porcento_superiores():
    posts = pd.DataFrame([_post(str(i), comentarios=i) for i in range(1, 101)])
    df = calcular(posts, _perfis(("p", 1000)), max_por_perfil=None)
    assert df["top10"].sum() == 10
    assert set(df.query("top10")["comentarios"]) == set(range(91, 101))


def test_top10_e_calculado_dentro_de_cada_faixa():
    # micro tem conversa menor que grande, mas leva os seus 10% próprios
    posts = [_post(f"g{i}", "grande", comentarios=50 + i) for i in range(20)]
    posts += [_post(f"m{i}", "micro", comentarios=i) for i in range(20)]
    df = calcular(pd.DataFrame(posts), _perfis(("grande", 500_000), ("micro", 3_000)), max_por_perfil=None)
    top = df[df["top10"]]
    assert set(top["post_id"]) == {"g19", "g18", "m19", "m18"}
    sem = calcular(pd.DataFrame(posts), _perfis(("grande", 500_000), ("micro", 3_000)), max_por_perfil=None, por_faixa=False)
    assert set(sem.loc[sem["top10"], "post_id"]) == {"g19", "g18", "g17", "g16"}


def test_lift_compara_com_a_mediana_do_proprio_perfil():
    posts = pd.DataFrame([_post(str(i), comentarios=c) for i, c in enumerate([10, 10, 10, 40])])
    df = calcular(posts, _perfis(("p", 1000))).set_index("post_id")
    assert df.loc["3", "lift"] == pytest.approx(4.0)
    assert df.loc["0", "lift"] == pytest.approx(1.0)


def test_intencao_desconhecida_nao_soma():
    posts = pd.DataFrame([_post("1", comentarios=2, intencao=2), _post("2", comentarios=2)])
    df = calcular(posts, _perfis(("p", 1000))).set_index("post_id")
    assert df.loc["1", "conversa"] == pytest.approx(6.0)
    assert df.loc["2", "conversa"] == pytest.approx(2.0)
    assert not df.loc["2", "intencao_conhecida"]


def test_filtrar_maduros_exige_14_dias():
    agora = datetime(2026, 11, 18, tzinfo=timezone.utc)
    posts = pd.DataFrame({"publicado_em": ["2026-11-10T00:00:00Z", "2026-11-04T00:00:00Z", "2026-10-01T00:00:00Z"]})
    assert len(filtrar_maduros(posts, agora)) == 2


def test_sensibilidade_identica_para_mesmo_peso():
    posts = pd.DataFrame([_post(str(i), comentarios=i % 9, intencao=i % 3) for i in range(1, 51)])
    out = sensibilidade(posts, _perfis(("p", 1000)), [2.0, 2.0])
    assert out["jaccard_vs_primeiro"].tolist() == [1.0, 1.0]


def test_faixas_de_perfil():
    assert faixa_de(3692) == "micro"
    assert faixa_de(50_000) == "medio"
    assert faixa_de(2_000_000) == "grande"
    assert faixa_de(None) is None
