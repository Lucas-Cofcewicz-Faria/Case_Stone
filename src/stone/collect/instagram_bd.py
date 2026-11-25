"""Coleta do Instagram pela Graph API · Business Discovery (rota oficial).

Pré-requisitos (ainda pendentes no projeto):
  - uma conta Instagram profissional (Criador) ligada a uma Página do Facebook;
  - um app no Meta for Developers e um token de usuário com instagram_basic,
    pages_show_list e pages_read_engagement;
  - IG_USER_ID (ID da conta profissional) e IG_ACCESS_TOKEN no .env.

Só retorna contas profissionais (Business/Creator). Não traz o texto dos
comentários, só a contagem. Curtidas ocultas vêm sem like_count.

Uso:
  python -m stone.collect.instagram_bd impulsostone sebrae --max-posts 150
  python -m stone.collect.instagram_bd --seeds data/seeds/perfis.csv
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

import pandas as pd

from ..config import GRAPH_API_VERSION, IG_ACCESS_TOKEN, IG_USER_ID, faixa_de
from ..db import conectar, upsert
from ..schema import Perfil, Post
from .http import ErroAPI, get_json

CAMPOS_MIDIA = ("id,caption,like_count,comments_count,media_type,media_product_type,"
                "permalink,timestamp,media_url,thumbnail_url,view_count")


def _consulta(username: str, limite: int, depois: str | None) -> dict:
    if not (IG_USER_ID and IG_ACCESS_TOKEN):
        sys.exit("Defina IG_USER_ID e IG_ACCESS_TOKEN no .env (veja .env.example).")
    paginacao = f".after({depois})" if depois else ""
    campos = (f"business_discovery.username({username})"
              f"{{username,name,biography,followers_count,media_count,"
              f"media.limit({limite}){paginacao}{{{CAMPOS_MIDIA}}}}}")
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{IG_USER_ID}"
    return get_json(url, {"fields": campos, "access_token": IG_ACCESS_TOKEN},
                    fonte="instagram", segredos={"access_token"})["business_discovery"]


def tipo_do_post(media_type: str | None, product: str | None) -> str:
    if product == "REELS":
        return "reels"
    if media_type == "CAROUSEL_ALBUM":
        return "carrossel"
    if media_type == "VIDEO":
        return "reels"
    return "imagem"


def coletar_perfil(username: str, max_posts: int, segmento: str | None = None,
                   origem: str | None = None) -> dict:
    agora = datetime.now(timezone.utc)
    posts: list[Post] = []
    depois = None
    bd: dict = {}
    while len(posts) < max_posts:
        bd = _consulta(username, min(50, max_posts - len(posts)), depois)
        midia = bd.get("media", {})
        for m in midia.get("data", []):
            posts.append(Post(
                post_id=m["id"], plataforma="instagram", handle=bd["username"],
                url=m.get("permalink", ""),
                tipo=tipo_do_post(m.get("media_type"), m.get("media_product_type")),
                publicado_em=m["timestamp"], legenda=m.get("caption"),
                curtidas=m.get("like_count"), comentarios=m.get("comments_count"),
                views=m.get("view_count"), thumb_url=m.get("thumbnail_url") or m.get("media_url"),
                media_url=m.get("media_url"), coletado_em=agora,
            ))
        depois = midia.get("paging", {}).get("cursors", {}).get("after")
        if not depois or not midia.get("paging", {}).get("next"):
            break

    seguidores = bd.get("followers_count")
    perfil = Perfil(handle=bd.get("username", username), plataforma="instagram",
                    nome=bd.get("name"), seguidores=seguidores, total_posts=bd.get("media_count"),
                    bio=bd.get("biography"), segmento=segmento, origem=origem,
                    faixa=faixa_de(seguidores), coletado_em=agora)
    with conectar() as con:
        upsert(con, [perfil])
        upsert(con, posts)
    ocultas = sum(p.curtidas is None for p in posts)
    return {"handle": perfil.handle, "seguidores": seguidores, "posts": len(posts),
            "curtidas_ocultas": ocultas}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("usernames", nargs="*")
    ap.add_argument("--seeds", help="CSV com colunas handle, plataforma, segmento, origem")
    ap.add_argument("--max-posts", type=int, default=150)
    a = ap.parse_args(argv)

    alvos = [{"handle": u.lstrip("@")} for u in a.usernames]
    if a.seeds:
        seeds = pd.read_csv(a.seeds).fillna("")
        alvos += seeds[seeds["plataforma"] == "instagram"].to_dict("records")
    if not alvos:
        ap.error("informe usernames ou --seeds")

    for alvo in alvos:
        try:
            r = coletar_perfil(alvo["handle"], a.max_posts, alvo.get("segmento") or None,
                               alvo.get("origem") or None)
        except ErroAPI as e:
            r = {"handle": alvo["handle"], "erro": str(e)}
        print(r, flush=True)


if __name__ == "__main__":
    main()
