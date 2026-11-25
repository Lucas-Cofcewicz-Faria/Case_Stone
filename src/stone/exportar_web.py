"""Exporta os dados estáticos do demo web (web/public/data/).

  galaxia.json  → um ponto por post: posição 3D, brilho (conversa), top 10%, segmento, título
  exemplos.json → posts do top 10% já avaliados, para o modo demo sem GPU
  resumo.json   → números da base, padrões gerais e validação

Posição: cada segmento é um braço da galáxia (ângulo fixo); dentro do braço, o post
se desloca pelos 3 primeiros componentes (SVD) dos atributos da rubrica, então posts
parecidos ficam perto. Uso: python -m stone.exportar_web
"""
from __future__ import annotations

import json
import math

import numpy as np

from .agente import ferramentas as F
from .api import _limpo, exemplos
from .config import ROOT

SAIDA = ROOT / "web" / "public" / "data"


def galaxia() -> dict:
    df = F._base().reset_index(drop=True)
    grupos = list(F.SEGMENTOS)
    seg_de = {s: i for i, g in enumerate(grupos) for s in F.SEGMENTOS[g]}
    df["g"] = df["segmento"].map(seg_de).fillna(len(grupos)).astype(int)

    vocab = sorted({a for s in df["atributos"] for a in s})
    idx = {a: i for i, a in enumerate(vocab)}
    X = np.zeros((len(df), len(vocab)), np.float32)
    for i, s in enumerate(df["atributos"]):
        X[i, [idx[a] for a in s]] = 1
    X -= X.mean(0)
    _, _, vt = np.linalg.svd(X, full_matrices=False)
    comp = X @ vt[:3].T
    comp /= np.abs(comp).max(0) + 1e-9

    rng = np.random.default_rng(7)
    n_g = len(grupos) + 1
    pts = []
    pct = df["conversa"].rank(pct=True).fillna(0)
    for i, r in df.iterrows():
        ang = 2 * math.pi * r["g"] / n_g
        raio = 0.55 + 0.32 * comp[i, 0] + rng.normal(0, 0.05)
        # espiral: o braço gira com o raio
        a = ang + 1.4 * raio + 0.35 * comp[i, 1]
        x, y = raio * math.cos(a), raio * math.sin(a)
        z = 0.22 * comp[i, 2] + rng.normal(0, 0.03)
        pts.append([round(x, 4), round(y, 4), round(z, 4), int(r["g"]), round(float(pct[i]), 3),
                    1 if r["top10"] else 0, r["post_id"], (r["titulo"] or "")[:70], (r["nome"] or "").strip(),
                    None if not r["rankeavel"] else round(float(r["conversa"]), 2)])
    return {"campos": ["x", "y", "z", "grupo", "brilho", "top10", "id", "titulo", "perfil", "conversa"],
            "grupos": grupos + ["outros"], "pontos": pts}


def resumo() -> dict:
    df = F._base()
    r = df[df["rankeavel"]]
    from .evaluator import validar
    aucs, quintis = validar(df)
    return {"posts": len(df), "rankeaveis": int(len(r)), "top10": int(r["top10"].sum()),
            "perfis": int(df["handle"].nunique()), "comentarios_lidos": None,
            "padroes": F.padroes(None), "auc": aucs.to_dict("records"), "quintis": quintis.to_dict("records")}


def main() -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    for nome, dados in [("galaxia", galaxia()), ("exemplos", exemplos(8)), ("resumo", resumo())]:
        (SAIDA / f"{nome}.json").write_text(json.dumps(_limpo(dados), ensure_ascii=False, separators=(",", ":")),
                                            encoding="utf-8")
        print(nome, (SAIDA / f"{nome}.json").stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
