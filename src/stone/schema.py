"""Modelos de dados validados com Pydantic (uma única forma para Instagram e YouTube)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Plataforma = Literal["instagram", "youtube"]
TipoPost = Literal["reels", "carrossel", "imagem", "short", "video"]


class Perfil(BaseModel):
    handle: str
    plataforma: Plataforma
    nome: str | None = None
    seguidores: int | None = Field(default=None, ge=0)
    total_posts: int | None = Field(default=None, ge=0)
    bio: str | None = None
    segmento: str | None = None
    origem: str | None = None
    faixa: str | None = None
    coletado_em: datetime


class Post(BaseModel):
    post_id: str
    plataforma: Plataforma
    handle: str
    url: str
    tipo: TipoPost
    publicado_em: datetime
    legenda: str | None = None
    titulo: str | None = None
    curtidas: int | None = Field(default=None, ge=0)   # None = curtidas ocultas
    comentarios: int | None = Field(default=None, ge=0)
    views: int | None = Field(default=None, ge=0)
    duracao_s: int | None = Field(default=None, ge=0)
    thumb_url: str | None = None
    media_url: str | None = None
    coletado_em: datetime


class Comentario(BaseModel):
    comentario_id: str
    post_id: str
    plataforma: Plataforma
    texto: str
    curtidas: int | None = Field(default=None, ge=0)
    publicado_em: datetime | None = None
    origem: Literal["api", "manual"] = "api"
