from datetime import datetime, timezone

import pandas as pd

from stone.base import montar, relatorio_md

AGORA = datetime(2026, 11, 18, tzinfo=timezone.utc)


def _dados():
    perfis = pd.DataFrame([
        {"handle": "ativo", "plataforma": "youtube", "seguidores": 1000, "faixa": "micro", "segmento": "MEI", "origem": "x", "nome": "A"},
        {"handle": "parado", "plataforma": "youtube", "seguidores": 5000, "faixa": "micro", "segmento": "MEI", "origem": "x", "nome": "P"},
    ])
    posts = pd.DataFrame([
        {"post_id": "novo", "handle": "ativo", "plataforma": "youtube", "publicado_em": "2026-11-15T00:00:00Z", "curtidas": 10, "comentarios": 1, "views": 2000},
        {"post_id": "a1", "handle": "ativo", "plataforma": "youtube", "publicado_em": "2026-10-01T00:00:00Z", "curtidas": 10, "comentarios": 10, "views": 2000},
        {"post_id": "a2", "handle": "ativo", "plataforma": "youtube", "publicado_em": "2026-09-01T00:00:00Z", "curtidas": 50, "comentarios": 0, "views": 2000},
        {"post_id": "velho", "handle": "parado", "plataforma": "youtube", "publicado_em": "2024-01-01T00:00:00Z", "curtidas": 99, "comentarios": 9, "views": 2000},
    ])
    comentarios = pd.DataFrame([
        {"post_id": "a1", "plataforma": "youtube", "texto": "qual o link?"},
        {"post_id": "a1", "plataforma": "youtube", "texto": "top"},
    ])
    return perfis, posts, comentarios


def test_montar_aplica_criterios_e_estima_intencao():
    df, q = montar(*_dados(), agora=AGORA)
    assert set(df["post_id"]) == {"a1", "a2"}          # sem post novo e sem perfil inativo
    assert q["perfis_inativos"] == ["parado (youtube)"]
    assert q["posts_descartados_menos_14_dias"] == 1
    a1 = df.set_index("post_id").loc["a1"]
    assert a1["comentarios_intencao"] == 5              # 50% de 10 comentários
    assert a1["eq"] == (10 + 5 * 10 + 10 * 5) / 1000
    assert a1["conversa"] == (10 + 2 * 5) / 2000 * 1000
    assert "Sensibilidade" in relatorio_md(q)
