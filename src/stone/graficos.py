"""Gráficos do mapeamento em SVG puro (sem matplotlib), para o playbook e o README.

  1. padroes.svg  · lift dos atributos com diferença significativa (|z| ≥ 1,96) entre o top 10% e o resto
  2. quintis.svg  · conversa mediana por quintil da nota do avaliador (validação cruzada)

Uso:
  python -m stone.graficos      # lê data/padroes.csv e data/avaliador_validacao.md, grava playbook/graficos/
"""
from __future__ import annotations

import math
import re
from html import escape

import pandas as pd

from .config import DATA

SAIDA = DATA.parent / "playbook" / "graficos"

# paleta de referência (skill dataviz): diverging azul ↔ vermelho, tinta e linhas recessivas
SUPERFICIE, TINTA, TINTA2, MUDO = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRADE, EIXO = "#e1e0d9", "#c3c2b7"
AZUL, VERMELHO = "#2a78d6", "#e34948"
FONTE = "font-family='Inter, Segoe UI, Helvetica, Arial, sans-serif'"

NOMES = {
    "tema_principal=burocracia_mei": "Tema: burocracia do MEI (DAS, nota, CNPJ)",
    "legenda_tamanho=curta": "Legenda curta",
    "duracao_faixa=60_180s": "Duração de 60 a 180 s",
    "tipo_hook=pergunta": "Gancho em forma de pergunta",
    "tom=informal": "Tom informal, de conversa",
    "tom=inspiracional": "Tom inspiracional",
    "tipo_hook=promessa": "Gancho de promessa (\"você vai…\")",
    "tema_principal=gestao": "Tema: gestão genérica",
}


def _svg(w: int, h: int, corpo: list[str], titulo: str) -> str:
    return (f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}' viewBox='0 0 {w} {h}' "
            f"role='img' aria-label='{escape(titulo)}' {FONTE}>\n<title>{escape(titulo)}</title>\n"
            f"<rect width='{w}' height='{h}' fill='{SUPERFICIE}'/>\n" + "\n".join(corpo) + "\n</svg>\n")


def _barra_h(x0: float, x1: float, y: float, alt: float, cor: str) -> str:
    """Barra horizontal com a ponta de dados arredondada (4px) e o lado da linha de base reto."""
    r = min(4, abs(x1 - x0) / 2)
    if x1 >= x0:
        d = (f"M{x0},{y} H{x1 - r} Q{x1},{y} {x1},{y + r} V{y + alt - r} Q{x1},{y + alt} {x1 - r},{y + alt} "
             f"H{x0} Z")
    else:
        d = (f"M{x0},{y} H{x1 + r} Q{x1},{y} {x1},{y + r} V{y + alt - r} Q{x1},{y + alt} {x1 + r},{y + alt} "
             f"H{x0} Z")
    return f"<path d='{d}' fill='{cor}'/>"


def grafico_padroes(pad: pd.DataFrame) -> str:
    sig = pad[pad["z"].abs() >= 1.96].copy()
    sig = sig[sig["atributo"].isin(NOMES)].sort_values("lift", ascending=False)
    w, esq, dir_, topo, linha = 900, 330, 170, 92, 38
    h = topo + linha * len(sig) + 64
    # escala log centrada em lift = 1 (dobro e metade ficam à mesma distância)
    lo, hi = math.log(0.4), math.log(1.6)
    px = lambda v: esq + (math.log(v) - lo) / (hi - lo) * (w - esq - dir_)
    c = [f"<text x='24' y='36' font-size='19' font-weight='600' fill='{TINTA}'>O que aparece mais (e menos) "
         f"nos posts que geram conversa</text>",
         f"<text x='24' y='60' font-size='13' fill='{TINTA2}'>Lift = % dos posts do top 10% com o atributo ÷ % no resto "
         f"da base. Só atributos com diferença significativa (|z| ≥ 1,96). 2.618 posts, 263 no top.</text>"]
    for v in (0.5, 0.75, 1.0, 1.25, 1.5):
        x = px(v)
        c.append(f"<line x1='{x:.1f}' y1='{topo - 8}' x2='{x:.1f}' y2='{h - 50}' "
                 f"stroke='{EIXO if v == 1 else GRADE}' stroke-width='{1.5 if v == 1 else 1}'/>")
        c.append(f"<text x='{x:.1f}' y='{h - 30}' font-size='12' fill='{MUDO}' text-anchor='middle'>"
                 f"{str(v).replace('.', ',')}×</text>")
    c.append(f"<text x='{px(1):.1f}' y='{h - 12}' font-size='12' fill='{TINTA2}' text-anchor='middle'>"
             f"← menos no top · igual · mais no top →</text>")
    for i, r in enumerate(sig.itertuples()):
        y = topo + i * linha
        cor = AZUL if r.lift >= 1 else VERMELHO
        c.append(f"<text x='{esq - 14}' y='{y + 17}' font-size='14' fill='{TINTA}' text-anchor='end'>"
                 f"{escape(NOMES[r.atributo])}</text>")
        c.append(_barra_h(px(1), px(r.lift), y + 4, 18, cor))
        lado = px(max(r.lift, 1)) + 10
        c.append(f"<text x='{lado:.1f}' y='{y + 17}' font-size='13' fill='{TINTA}'>"
                 f"<tspan font-weight='600'>{str(r.lift).replace('.', ',')}×</tspan>"
                 f"<tspan fill='{MUDO}'>  {r.pct_top:.0f}% vs {r.pct_resto:.0f}%</tspan></text>")
    return _svg(w, h, c, "Lift dos atributos significativos no top 10% de conversa")


def _quintis() -> pd.DataFrame:
    txt = (DATA / "avaliador_validacao.md").read_text(encoding="utf-8")
    linhas = re.findall(r"^\|\s*(\d)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|$", txt, re.M)
    return pd.DataFrame([(int(q), float(m), float(t)) for q, m, t, _ in linhas],
                        columns=["quintil", "conversa_mediana", "pct_top10"])


def grafico_quintis(q: pd.DataFrame) -> str:
    w, h, esq, base, topo = 760, 400, 70, 320, 100
    larg = (w - esq - 40) / len(q)
    vmax = 1.6
    py = lambda v: base - v / vmax * (base - topo)
    c = [f"<text x='24' y='36' font-size='19' font-weight='600' fill='{TINTA}'>Nota maior, mais conversa "
         f"(mas o sinal é fraco)</text>",
         f"<text x='24' y='60' font-size='13' fill='{TINTA2}'>Conversa mediana (comentários + 2·intenção por mil views) "
         f"por quintil da nota, em perfis fora do treino.</text>",
         f"<text x='24' y='78' font-size='13' fill='{TINTA2}'>AUC da validação cruzada por perfil: 0,55 "
         f"(0,5 = acaso).</text>"]
    for v in (0, 0.5, 1.0, 1.5):
        y = py(v)
        c.append(f"<line x1='{esq}' y1='{y:.1f}' x2='{w - 30}' y2='{y:.1f}' "
                 f"stroke='{EIXO if v == 0 else GRADE}' stroke-width='1'/>")
        c.append(f"<text x='{esq - 10}' y='{y + 4:.1f}' font-size='12' fill='{MUDO}' text-anchor='end'>"
                 f"{str(v).replace('.', ',')}</text>")
    for i, r in enumerate(q.itertuples()):
        x = esq + i * larg + larg * 0.22
        bw = larg * 0.56
        y = py(r.conversa_mediana)
        rr = 4
        c.append(f"<path d='M{x:.1f},{base} V{y + rr:.1f} Q{x:.1f},{y:.1f} {x + rr:.1f},{y:.1f} H{x + bw - rr:.1f} "
                 f"Q{x + bw:.1f},{y:.1f} {x + bw:.1f},{y + rr:.1f} V{base} Z' fill='{AZUL}'/>")
        c.append(f"<text x='{x + bw / 2:.1f}' y='{y - 8:.1f}' font-size='13' font-weight='600' fill='{TINTA}' "
                 f"text-anchor='middle'>{str(r.conversa_mediana).replace('.', ',')}</text>")
        rot = {1: "1º (nota baixa)", 5: "5º (nota alta)"}.get(r.quintil, f"{r.quintil}º")
        c.append(f"<text x='{x + bw / 2:.1f}' y='{base + 20}' font-size='12' fill='{TINTA2}' "
                 f"text-anchor='middle'>{rot}</text>")
        c.append(f"<text x='{x + bw / 2:.1f}' y='{base + 37}' font-size='11' fill='{MUDO}' "
                 f"text-anchor='middle'>{str(r.pct_top10).replace('.', ',')}% no top</text>")
    return _svg(w, h, c, "Conversa mediana por quintil da nota do avaliador")


def main() -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    (SAIDA / "padroes.svg").write_text(grafico_padroes(pd.read_csv(DATA / "padroes.csv")), encoding="utf-8")
    (SAIDA / "quintis.svg").write_text(grafico_quintis(_quintis()), encoding="utf-8")
    print(f"gráficos em {SAIDA}")


if __name__ == "__main__":
    main()
