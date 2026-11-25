"""Coletores testados com respostas falsas da API (sem rede e sem cota)."""
import sqlite3

import pytest

import stone.db
from stone.collect import instagram_bd, youtube
from stone.collect.http import ErroAPI


@pytest.fixture
def db_tmp(tmp_path, monkeypatch):
    caminho = tmp_path / "teste.db"
    monkeypatch.setattr(stone.db, "DB_PATH", caminho)
    return caminho


@pytest.mark.parametrize("iso,seg", [("PT45S", 45), ("PT1M5S", 65), ("PT3M", 180),
                                     ("PT1H2M3S", 3723), ("P0D", 0), (None, None), ("xx", None)])
def test_duracao_iso(iso, seg):
    assert youtube.duracao_segundos(iso) == seg


@pytest.mark.parametrize("mt,prod,esperado", [("VIDEO", "REELS", "reels"), ("CAROUSEL_ALBUM", "FEED", "carrossel"),
                                              ("IMAGE", "FEED", "imagem"), ("VIDEO", "FEED", "reels")])
def test_tipo_instagram(mt, prod, esperado):
    assert instagram_bd.tipo_do_post(mt, prod) == esperado


def _canal():
    return {"id": "UCabc123", "snippet": {"title": "Canal MPE", "customUrl": "@canalmpe", "description": "dicas p/ MEI"},
            "statistics": {"subscriberCount": "8000", "videoCount": "300"},
            "contentDetails": {"relatedPlaylists": {"uploads": "UUabc123"}}}


def _video(vid, dur, curt="10", com="2"):
    return {"id": vid, "snippet": {"publishedAt": "2026-09-01T12:00:00Z", "title": f"v{vid}", "description": "",
                                   "thumbnails": {"high": {"url": f"https://i/{vid}.jpg"}}},
            "statistics": {"viewCount": "1000", "likeCount": curt, "commentCount": com},
            "contentDetails": {"duration": dur}}


def test_youtube_sem_playlist_de_shorts_filtra_por_duracao(db_tmp, monkeypatch):
    def falso(recurso, **p):
        if recurso == "channels":
            return {"items": [_canal()]}
        if recurso == "playlistItems":
            if p["playlistId"].startswith("UUSH"):
                raise ErroAPI(404, "playlistNotFound")
            return {"items": [{"contentDetails": {"videoId": v}} for v in ("a", "b")]}
        if recurso == "videos":
            return {"items": [_video("a", "PT40S"), _video("b", "PT12M")]}
        if recurso == "commentThreads":
            return {"items": [{"snippet": {"topLevelComment": {"id": "c1", "snippet": {
                "textOriginal": "quero saber como faço", "likeCount": 1, "publishedAt": "2026-09-02T00:00:00Z"}}}}]}
        raise AssertionError(recurso)

    monkeypatch.setattr(youtube, "_get", falso)
    r = youtube.coletar_canal("@canalmpe", max_videos=10, n_comentarios=5)
    assert r == {"handle": "canalmpe", "inscritos": 8000, "shorts": 1, "comentarios": 1, "fonte_ids": "uploads+duração"}

    con = sqlite3.connect(db_tmp)
    assert con.execute("select faixa, seguidores from perfis").fetchone() == ("micro", 8000)
    assert con.execute("select post_id, tipo, duracao_s from posts").fetchall() == [("a", "short", 40)]
    assert con.execute("select texto from comentarios").fetchone() == ("quero saber como faço",)


def test_youtube_comentarios_desativados_nao_quebra(db_tmp, monkeypatch):
    def falso(recurso, **p):
        if recurso == "channels":
            return {"items": [_canal()]}
        if recurso == "playlistItems":
            return {"items": [{"contentDetails": {"videoId": "a"}}]}
        if recurso == "videos":
            return {"items": [_video("a", "PT2M30S")]}
        if recurso == "commentThreads":
            raise ErroAPI(403, "commentsDisabled")
        raise AssertionError(recurso)

    monkeypatch.setattr(youtube, "_get", falso)
    r = youtube.coletar_canal("canalmpe", max_videos=10, n_comentarios=5)
    assert r["shorts"] == 1 and r["comentarios"] == 0 and r["fonte_ids"] == "UUSH"


def test_instagram_pagina_e_marca_curtidas_ocultas(db_tmp, monkeypatch):
    paginas = {
        None: {"username": "impulsostone", "name": "Impulso Stone", "followers_count": 3692, "media_count": 3,
               "media": {"data": [
                   {"id": "1", "caption": "Empreendedor(a), queremos...", "like_count": 39, "comments_count": 113,
                    "media_type": "VIDEO", "media_product_type": "REELS", "permalink": "https://ig/p/1",
                    "timestamp": "2026-08-21T15:00:00+0000"},
                   {"id": "2", "caption": "Carrossel", "comments_count": 4, "media_type": "CAROUSEL_ALBUM",
                    "media_product_type": "FEED", "permalink": "https://ig/p/2", "timestamp": "2026-08-01T15:00:00+0000"}],
                   "paging": {"cursors": {"after": "CUR1"}, "next": "https://..."}}},
        "CUR1": {"username": "impulsostone", "followers_count": 3692,
                 "media": {"data": [{"id": "3", "like_count": 12, "comments_count": 0, "media_type": "IMAGE",
                                     "media_product_type": "FEED", "permalink": "https://ig/p/3",
                                     "timestamp": "2026-07-01T15:00:00+0000"}],
                           "paging": {"cursors": {"after": "CUR2"}}}},
    }
    monkeypatch.setattr(instagram_bd, "_consulta", lambda u, limite, depois: paginas[depois])
    r = instagram_bd.coletar_perfil("impulsostone", max_posts=100)
    assert r == {"handle": "impulsostone", "seguidores": 3692, "posts": 3, "curtidas_ocultas": 1}

    con = sqlite3.connect(db_tmp)
    assert con.execute("select tipo from posts order by post_id").fetchall() == [("reels",), ("carrossel",), ("imagem",)]


def test_corrigir_hook_troca_rotulo_pela_capa_ou_titulo():
    from stone.categorizar import corrigir_hook
    from stone.rubric import RubricaVLM
    base = dict(descricao_visual="x", texto_na_tela="", formato_video="talking_head", hook_primeiros_3s="pergunta",
                tipo_hook="pergunta", forca_hook_0a10=5, tema_principal="gestao", pilar_impulso="nenhum", tem_rosto=True,
                criador_e_empreendedor_real=False, prova_social=False, tom="informal", usa_linguagem_regional=False,
                clareza_mensagem_0a10=7, tem_cta=False, tipo_cta="nenhum", oferta_ou_beneficio_explicito=False,
                elementos_top5=["a"])
    assert corrigir_hook(RubricaVLM(**base), "Você sabe precificar?").hook_primeiros_3s == "Você sabe precificar?"
    capa = RubricaVLM(**{**base, "hook_primeiros_3s": "10", "texto_na_tela": "3 ERROS NO CAIXA\nMEI"})
    assert corrigir_hook(capa, "t").hook_primeiros_3s == "3 ERROS NO CAIXA"
    ok = RubricaVLM(**{**base, "hook_primeiros_3s": "Seu dinheiro some no fim do mês?"})
    assert corrigir_hook(ok, "t").hook_primeiros_3s == "Seu dinheiro some no fim do mês?"


def test_normalizar_hook_pergunta_vence_dor():
    from stone.rubric import normalizar_hook
    # o caso do ar-condicionado: o modelo disse "dor" para uma abertura que é pergunta
    assert normalizar_hook({"tipo_hook": "dor", "hook_primeiros_3s": "Orçamento de ar-condicionado: vale a pena?"})["tipo_hook"] == "pergunta"
    # dor afirmada continua dor; outros tipos não mudam
    assert normalizar_hook({"tipo_hook": "dor", "hook_primeiros_3s": "Seu dinheiro some no fim do mês."})["tipo_hook"] == "dor"
    assert normalizar_hook({"tipo_hook": "curiosidade", "hook_primeiros_3s": "Sabe o que é isso?"})["tipo_hook"] == "curiosidade"
