"""Aplica a rubrica aos posts da base: baixa a thumbnail, chama o VLM e grava no SQLite.

Uso:
  python -m stone.categorizar --amostra 20 --modelo qwen3-vl:4b-instruct   # benchmark
  python -m stone.categorizar --top10 --resto 300                          # top 10% + amostra do resto
  python -m stone.categorizar --todos
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path

import pandas as pd
import requests

from .config import DATA, DB_PATH
from .llm import MODELO_PADRAO, gerar_json
from typing import get_args

from .rubric import (PROMPT_VERSAO, SISTEMA, RubricaVLM, TipoHook, duracao_faixa, legenda_tamanho, montar_prompt)

THUMBS = DATA / "media" / "thumbs"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS rubrica (
    post_id TEXT NOT NULL, plataforma TEXT NOT NULL, modelo TEXT NOT NULL, versao TEXT NOT NULL,
    json TEXT NOT NULL, tipo_post TEXT, duracao_faixa TEXT, legenda_tamanho TEXT,
    segundos REAL, criado_em TEXT NOT NULL,
    PRIMARY KEY (post_id, plataforma, modelo, versao)
);
"""


def baixar_thumb(post_id: str, url: str | None) -> Path | None:
    if not url:
        return None
    destino = THUMBS / f"{post_id}.jpg"
    if destino.exists():
        return destino
    # hqdefault (480x360) basta para ler texto e economiza tokens de imagem
    if "ytimg.com" in url:
        url = url.replace("maxresdefault", "hqdefault")
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
    except requests.RequestException:
        return None
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(r.content)
    return destino


def corrigir_hook(rub: RubricaVLM, titulo: str | None) -> RubricaVLM:
    """O modelo às vezes escreve o rótulo ("pergunta") ou um número no lugar da frase de abertura.

    Nesses casos, a frase vira a 1ª linha do texto da capa ou, sem texto na capa, o título.
    """
    h = (rub.hook_primeiros_3s or "").strip().lower()
    rotulos = set(get_args(TipoHook))
    if h in rotulos or h.isdigit() or len(h) < 4:
        capa = (rub.texto_na_tela or "").strip().splitlines()
        rub = rub.model_copy(update={"hook_primeiros_3s": (capa[0] if capa else (titulo or ""))[:150]})
    return rub


def categorizar_post(post: pd.Series, modelo: str) -> dict:
    thumb = baixar_thumb(post["post_id"], post.get("thumb_url"))
    prompt = montar_prompt(post.get("titulo"), post.get("legenda"), post["plataforma"], post.get("duracao_s"))
    rub, meta = gerar_json(RubricaVLM, SISTEMA, prompt, [thumb] if thumb else [], modelo=modelo, versao=PROMPT_VERSAO)
    rub = corrigir_hook(rub, post.get("titulo"))
    dur = None if pd.isna(post.get("duracao_s")) else int(post["duracao_s"])
    return {
        "post_id": post["post_id"], "plataforma": post["plataforma"], "modelo": modelo, "versao": PROMPT_VERSAO,
        "json": json.dumps(rub.model_dump(mode="json"), ensure_ascii=False),
        "tipo_post": post.get("tipo"), "duracao_faixa": duracao_faixa(dur),
        "legenda_tamanho": legenda_tamanho(f"{post.get('titulo') or ''} {post.get('legenda') or ''}"),
        "segundos": meta["segundos"], "criado_em": time.strftime("%Y-%m-%dT%H:%M:%S"), "_cache": meta["cache"],
    }


def selecionar(base: pd.DataFrame, a: argparse.Namespace) -> pd.DataFrame:
    if a.todos:
        return base
    if a.amostra:
        # amostra estratificada: metade do top 10%, metade do resto
        top = base[base["top10"]].sample(min(a.amostra // 2, base["top10"].sum()), random_state=7)
        resto = base[~base["top10"] & base["rankeavel"]].sample(a.amostra - len(top), random_state=7)
        return pd.concat([top, resto])
    partes = []
    if a.top10:
        partes.append(base[base["top10"]])
    if a.resto:
        partes.append(base[~base["top10"] & base["rankeavel"]].sample(a.resto, random_state=7))
    return pd.concat(partes) if partes else base.iloc[0:0]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modelo", default=MODELO_PADRAO)
    ap.add_argument("--amostra", type=int, default=0)
    ap.add_argument("--top10", action="store_true")
    ap.add_argument("--resto", type=int, default=0)
    ap.add_argument("--todos", action="store_true")
    a = ap.parse_args(argv)

    base = pd.read_parquet(DATA / "base_posts.parquet")
    alvo = selecionar(base, a)
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA_SQL)
    feitos = {r[0] for r in con.execute("select post_id from rubrica where modelo=? and versao=?",
                                        (a.modelo, PROMPT_VERSAO))}
    alvo = alvo[~alvo["post_id"].isin(feitos)]
    print(f"{len(alvo)} posts a categorizar com {a.modelo} ({len(feitos)} já feitos)", flush=True)

    tempos = []
    for i, (_, post) in enumerate(alvo.iterrows(), 1):
        try:
            linha = categorizar_post(post, a.modelo)
        except Exception as e:  # um post ruim não derruba o lote
            print(f"[{i}/{len(alvo)}] {post['post_id']} ERRO {e}", flush=True)
            continue
        cache = linha.pop("_cache")
        con.execute(f"INSERT OR REPLACE INTO rubrica ({', '.join(linha)}) VALUES ({', '.join('?' * len(linha))})",
                    list(linha.values()))
        con.commit()
        if not cache:
            tempos.append(linha["segundos"])
        if i % 10 == 0 or i == len(alvo):
            media = sum(tempos) / len(tempos) if tempos else 0
            print(f"[{i}/{len(alvo)}] média {media:.1f}s/post", flush=True)
    con.close()


if __name__ == "__main__":
    main()
