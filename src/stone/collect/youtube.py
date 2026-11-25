"""Coleta de Shorts pela YouTube Data API v3 (rota oficial, prevista no TAPI).

Custo de cota por canal (cota diária padrão: 10.000 unidades):
  channels.list = 1 · playlistItems.list = 1 por 50 vídeos · videos.list = 1 por 50
  commentThreads.list = 1 por vídeo (até 100 comentários)
Não usamos search.list (100 unidades), como recomenda o TAPI.

Uso:
  python -m stone.collect.youtube @canal1 @canal2 --max-videos 150 --comentarios 50
  python -m stone.collect.youtube --seeds data/seeds/perfis.csv
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone

import pandas as pd

from ..config import SHORTS_MAX_SECONDS, YOUTUBE_API_KEY, faixa_de
from ..db import conectar, upsert
from ..schema import Comentario, Perfil, Post
from .http import ErroAPI, get_json

API = "https://www.googleapis.com/youtube/v3"


def _get(recurso: str, **params) -> dict:
    if not YOUTUBE_API_KEY:
        sys.exit("Defina YOUTUBE_API_KEY no arquivo .env (veja .env.example).")
    params["key"] = YOUTUBE_API_KEY
    return get_json(f"{API}/{recurso}", params, fonte="youtube", segredos={"key"})


def duracao_segundos(iso: str | None) -> int | None:
    """Converte duração ISO 8601 (PT1M05S, P0D, PT2H) em segundos."""
    if not iso:
        return None
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", iso)
    if not m:
        return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def buscar_canal(handle: str) -> dict | None:
    handle = handle if handle.startswith(("@", "UC")) else f"@{handle}"
    filtro = {"id": handle} if handle.startswith("UC") else {"forHandle": handle}
    dados = _get("channels", part="snippet,statistics,contentDetails", **filtro)
    itens = dados.get("items", [])
    return itens[0] if itens else None


def _ids_da_playlist(playlist_id: str, limite: int) -> list[str]:
    ids: list[str] = []
    token = None
    while len(ids) < limite:
        params = {"part": "contentDetails", "playlistId": playlist_id, "maxResults": 50}
        if token:
            params["pageToken"] = token
        dados = _get("playlistItems", **params)
        ids += [i["contentDetails"]["videoId"] for i in dados.get("items", [])]
        token = dados.get("nextPageToken")
        if not token:
            break
    return ids[:limite]


def ids_de_shorts(canal: dict, limite: int) -> tuple[list[str], bool]:
    """Tenta a playlist de Shorts do canal (UUSH…); se não existir, usa os uploads.

    Retorna (ids, veio_da_playlist_de_shorts). A playlist UUSH não é documentada
    oficialmente; quando ela falha, os Shorts são filtrados depois pela duração.
    """
    channel_id = canal["id"]
    try:
        ids = _ids_da_playlist("UUSH" + channel_id[2:], limite)
        if ids:
            return ids, True
    except ErroAPI as e:
        if e.status not in (400, 403, 404):
            raise
    uploads = canal["contentDetails"]["relatedPlaylists"]["uploads"]
    return _ids_da_playlist(uploads, limite), False


def detalhes_videos(ids: list[str]) -> list[dict]:
    videos = []
    for i in range(0, len(ids), 50):
        dados = _get("videos", part="snippet,statistics,contentDetails", id=",".join(ids[i:i + 50]))
        videos += dados.get("items", [])
    return videos


def comentarios_do_video(video_id: str, limite: int) -> list[dict]:
    if limite <= 0:
        return []
    try:
        dados = _get("commentThreads", part="snippet", videoId=video_id,
                     maxResults=min(limite, 100), order="relevance", textFormat="plainText")
    except ErroAPI as e:
        if e.status == 403:  # comentários desativados no vídeo
            return []
        raise
    return dados.get("items", [])[:limite]


def _int(valor) -> int | None:
    return int(valor) if valor not in (None, "") else None


def coletar_canal(handle: str, max_videos: int, n_comentarios: int,
                  segmento: str | None = None, origem: str | None = None) -> dict:
    agora = datetime.now(timezone.utc)
    canal = buscar_canal(handle)
    if canal is None:
        return {"handle": handle, "erro": "canal não encontrado"}

    sn, st = canal["snippet"], canal.get("statistics", {})
    handle_ok = (sn.get("customUrl") or handle).lstrip("@")
    inscritos = None if st.get("hiddenSubscriberCount") else _int(st.get("subscriberCount"))
    perfil = Perfil(handle=handle_ok, plataforma="youtube", nome=sn.get("title"),
                    seguidores=inscritos, total_posts=_int(st.get("videoCount")),
                    bio=sn.get("description"), segmento=segmento, origem=origem,
                    faixa=faixa_de(inscritos), coletado_em=agora)

    ids, da_playlist_shorts = ids_de_shorts(canal, max_videos)
    posts, comentarios = [], []
    for v in detalhes_videos(ids):
        dur = duracao_segundos(v["contentDetails"].get("duration"))
        if not da_playlist_shorts and (dur is None or dur > SHORTS_MAX_SECONDS):
            continue
        vs, vst = v["snippet"], v.get("statistics", {})
        thumbs = vs.get("thumbnails", {})
        thumb = (thumbs.get("maxres") or thumbs.get("high") or thumbs.get("default") or {}).get("url")
        posts.append(Post(
            post_id=v["id"], plataforma="youtube", handle=handle_ok,
            url=f"https://www.youtube.com/shorts/{v['id']}", tipo="short",
            publicado_em=vs["publishedAt"], titulo=vs.get("title"), legenda=vs.get("description"),
            curtidas=_int(vst.get("likeCount")), comentarios=_int(vst.get("commentCount")),
            views=_int(vst.get("viewCount")), duracao_s=dur, thumb_url=thumb, coletado_em=agora,
        ))
        if (_int(vst.get("commentCount")) or 0) > 0:
            for c in comentarios_do_video(v["id"], n_comentarios):
                top = c["snippet"]["topLevelComment"]
                cs = top["snippet"]
                comentarios.append(Comentario(
                    comentario_id=top["id"], post_id=v["id"], plataforma="youtube",
                    texto=cs.get("textOriginal") or cs.get("textDisplay") or "",
                    curtidas=_int(cs.get("likeCount")), publicado_em=cs.get("publishedAt"),
                ))

    with conectar() as con:
        upsert(con, [perfil])
        upsert(con, posts)
        upsert(con, comentarios)
    return {"handle": handle_ok, "inscritos": inscritos, "shorts": len(posts),
            "comentarios": len(comentarios), "fonte_ids": "UUSH" if da_playlist_shorts else "uploads+duração"}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("handles", nargs="*", help="@handle ou ID UC… do canal")
    ap.add_argument("--seeds", help="CSV com colunas handle, plataforma, segmento, origem")
    ap.add_argument("--max-videos", type=int, default=150)
    ap.add_argument("--comentarios", type=int, default=50, help="comentários por vídeo (0 = nenhum)")
    a = ap.parse_args(argv)

    alvos = [{"handle": h} for h in a.handles]
    if a.seeds:
        seeds = pd.read_csv(a.seeds).fillna("")
        alvos += seeds[seeds["plataforma"] == "youtube"].to_dict("records")
    if not alvos:
        ap.error("informe handles ou --seeds")

    for alvo in alvos:
        try:
            r = coletar_canal(alvo["handle"], a.max_videos, a.comentarios,
                              alvo.get("segmento") or None, alvo.get("origem") or None)
        except ErroAPI as e:
            r = {"handle": alvo["handle"], "erro": str(e)}
        print(r, flush=True)


if __name__ == "__main__":
    main()
