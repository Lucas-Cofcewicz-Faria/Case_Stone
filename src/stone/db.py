"""Base SQLite: criação das tabelas e upsert a partir dos modelos Pydantic."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator

from pydantic import BaseModel

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS perfis (
    handle TEXT NOT NULL, plataforma TEXT NOT NULL, nome TEXT,
    seguidores INTEGER, total_posts INTEGER, bio TEXT, segmento TEXT,
    origem TEXT, faixa TEXT, coletado_em TEXT NOT NULL,
    PRIMARY KEY (handle, plataforma)
);
CREATE TABLE IF NOT EXISTS posts (
    post_id TEXT NOT NULL, plataforma TEXT NOT NULL, handle TEXT NOT NULL,
    url TEXT, tipo TEXT, publicado_em TEXT, legenda TEXT, titulo TEXT,
    curtidas INTEGER, comentarios INTEGER, views INTEGER, duracao_s INTEGER,
    thumb_url TEXT, media_url TEXT, coletado_em TEXT NOT NULL,
    PRIMARY KEY (post_id, plataforma)
);
CREATE TABLE IF NOT EXISTS comentarios (
    comentario_id TEXT NOT NULL, post_id TEXT NOT NULL, plataforma TEXT NOT NULL,
    texto TEXT NOT NULL, curtidas INTEGER, publicado_em TEXT, origem TEXT,
    PRIMARY KEY (comentario_id, plataforma)
);
CREATE INDEX IF NOT EXISTS ix_posts_handle ON posts(handle, plataforma);
CREATE INDEX IF NOT EXISTS ix_coment_post ON comentarios(post_id);
"""

TABELAS = {"Perfil": "perfis", "Post": "posts", "Comentario": "comentarios"}


@contextmanager
def conectar(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    path = path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def upsert(con: sqlite3.Connection, itens: Iterable[BaseModel]) -> int:
    n = 0
    for item in itens:
        tabela = TABELAS[type(item).__name__]
        linha = item.model_dump(mode="json")
        cols = ", ".join(linha)
        marcas = ", ".join("?" for _ in linha)
        con.execute(
            f"INSERT OR REPLACE INTO {tabela} ({cols}) VALUES ({marcas})",
            list(linha.values()),
        )
        n += 1
    return n
