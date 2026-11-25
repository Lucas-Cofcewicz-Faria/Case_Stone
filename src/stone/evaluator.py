"""Avaliador de aderência (TAPI 4.2): quanto um post ou rascunho se parece com o que gera conversa.

Não é modelo preditivo (TAPI 4.3 deixa isso fora do escopo). A nota diz quantos
traços do top o post tem, comparado com a base, e não promete resultado (TAPI 6.4).

Duas visões de "top", as duas reportadas:
  - top10: top 10% de conversa dentro da faixa de perfil (definição do case);
  - top_perfil: post nos 20% melhores do próprio perfil (perfis com 10+ posts).
    Controla o efeito do canal: separa "conteúdo bom" de "canal que engaja em tudo".

Como a nota sai:
  1. Cada atributo da rubrica recebe um peso = log(lift), encolhido para zero quando
     há poucos posts (peso · n/(n+20)). Atributo raro não manda na nota.
  2. Pontos do post = soma dos pesos dos atributos que ele tem, nas duas visões.
  3. Nota 0–100 = percentil dos pontos entre os posts da base.
  4. Sugestões: para cada campo, se existe um valor com peso bem maior que o atual,
     sugere a troca, com exemplos do top que têm esse valor.

Uso:
  python -m stone.evaluator validar          # AUC com validação cruzada (sem vazamento)
  python -m stone.evaluator impulso          # checagem externa nos criativos do Impulso (precisa do Ollama)
  python -m stone.evaluator post <post_id>   # avalia um post da base
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import DATA
from .patterns import BOOLEANOS, CATEGORICOS, NOTAS, atributos, calcular_lift, montar_base

ENCOLHIMENTO = 20         # posts "virtuais" no encolhimento do peso
MIN_PERFIL = 10           # perfis com menos posts não entram na visão top_perfil
PCT_PERFIL = 0.80         # top_perfil = acima do percentil 80 do próprio perfil
GANHO_MIN_SUGESTAO = 0.15  # diferença mínima de peso para sugerir troca
VISOES = ("top10", "top_perfil")
# valores que significam "não tem": nunca podem somar crédito
AUSENCIAS = {"tipo_hook=sem_gancho", "tema_principal=outro", "pilar_impulso=nenhum", "tipo_cta=nenhum",
             "formato_video=outro", "forca_hook_0a10=baixa", "clareza_mensagem_0a10=baixa", "legenda_tamanho=vazia"}
MIN_CONTEUDO = 2          # clareza e força do gancho até 2 = post sem mensagem, nota 0


def marcar_top_perfil(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    r = df["rankeavel"]
    grp = df[r].groupby(["handle", "plataforma"])["conversa"]
    df.loc[r, "pct_perfil"] = grp.rank(pct=True)
    df.loc[r, "n_perfil"] = grp.transform("size")
    df["top_perfil"] = r & (df["pct_perfil"] > PCT_PERFIL) & (df["n_perfil"] >= MIN_PERFIL)
    return df


def pesos(df: pd.DataFrame, alvo: str) -> pd.DataFrame:
    """Lift de cada atributo e o peso encolhido usado na nota."""
    lift = calcular_lift(df, alvo)
    if lift.empty:
        return lift
    n = lift["posts_top"] + lift["posts_resto"]
    bruto = np.log(lift["lift"].clip(0.05, 20))
    lift["peso"] = (bruto * lift["posts_top"] / (lift["posts_top"] + ENCOLHIMENTO)).round(3)
    # ausência de um traço nunca vira crédito: "sem gancho" mais comum no top é efeito de outra coisa
    # (vlogs de canais que conversam muito), não receita. Esses valores só podem pesar contra.
    ausencia = lift["atributo"].isin(AUSENCIAS)
    lift.loc[ausencia, "peso"] = lift.loc[ausencia, "peso"].clip(upper=0)
    lift["n"] = n
    return lift.set_index("atributo")


def sem_conteudo(rub: dict) -> bool:
    """Post sem mensagem: a rubrica deu clareza e força do gancho quase nulas (4 de 3.548 posts na base)."""
    def nota(c):
        v = rub.get(c)
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    clareza, forca = nota("clareza_mensagem_0a10"), nota("forca_hook_0a10")
    return clareza is not None and forca is not None and clareza <= MIN_CONTEUDO and forca <= MIN_CONTEUDO


@dataclass
class Modelo:
    """Pesos das duas visões + distribuição de pontos da base (para virar percentil)."""
    pesos: dict[str, pd.DataFrame]
    pontos_base: np.ndarray
    base: pd.DataFrame = field(repr=False)

    def pontos(self, attrs: set[str]) -> float:
        return float(sum(self.pesos[v]["peso"].reindex(list(attrs)).fillna(0).sum() for v in VISOES))

    def nota(self, attrs: set[str]) -> int:
        return int(round(100 * (self.pontos_base < self.pontos(attrs)).mean()))


def treinar(df: pd.DataFrame) -> Modelo:
    df = df[df["rankeavel"]]
    w = {v: pesos(df, v) for v in VISOES}
    tmp = Modelo(w, np.array([0.0]), df)
    pts = np.array([tmp.pontos(a) for a in df["atributos"]])
    return Modelo(w, np.sort(pts), df)


def _rub_de_attrs(attrs: set[str]) -> dict:
    d = {}
    for a in attrs:
        k, _, v = a.partition("=")
        d[k] = v if v else True
    return d


def avaliar(modelo: Modelo, rub: dict, n_ref: int = 3) -> dict:
    """Avalia uma rubrica (dict com os campos da RubricaVLM + tipo_post/duracao_faixa/legenda_tamanho)."""
    attrs = atributos(rub)
    if sem_conteudo(rub):
        return {"nota": 0, "pontos": 0.0, "sem_conteudo": True, "padroes_cumpridos": [], "antipadroes": [],
                "sugestoes": [], "referencias": referencias(modelo, attrs, n_ref),
                "motivo": "O post não tem mensagem para avaliar: sem assunto claro e sem gancho. "
                          "Diga o que você vende ou resolve e faça uma pergunta ou um pedido ao público.",
                "aviso": "A nota mede semelhança com posts que geraram conversa na base; não prevê resultado."}
    tem = _rub_de_attrs(attrs)
    w = modelo.pesos
    peso_total = lambda a: sum(float(w[v]["peso"].get(a, 0.0)) for v in VISOES)  # noqa: E731

    fortes, anti = [], []
    for a in attrs:
        for v in VISOES:
            if a in w[v].index and w[v].loc[a, "tipo"] in ("padrao", "antipadrao"):
                item = {"atributo": a, "visao": v, "lift": float(w[v].loc[a, "lift"]),
                        "posts_top": int(w[v].loc[a, "posts_top"])}
                (fortes if w[v].loc[a, "tipo"] == "padrao" else anti).append(item)

    sugestoes = []
    for campo in CATEGORICOS + list(NOTAS):
        atual = f"{campo}={tem[campo]}" if campo in tem else None
        if atual is None:
            continue
        opcoes = {a for v in VISOES for a in w[v].index if a.startswith(campo + "=")}
        melhor = max(opcoes, key=peso_total, default=None)
        if melhor and melhor != atual and peso_total(melhor) - peso_total(atual) >= GANHO_MIN_SUGESTAO:
            sugestoes.append({"campo": campo, "de": atual.split("=")[1], "para": melhor.split("=")[1],
                              "ganho": round(peso_total(melhor) - peso_total(atual), 2),
                              "exemplos": _exemplos(modelo, melhor)})
    for campo in BOOLEANOS:
        if campo not in tem and peso_total(campo) >= GANHO_MIN_SUGESTAO:
            sugestoes.append({"campo": campo, "de": False, "para": True,
                              "ganho": round(peso_total(campo), 2), "exemplos": _exemplos(modelo, campo)})
    sugestoes.sort(key=lambda s: -s["ganho"])

    return {"nota": modelo.nota(attrs), "pontos": round(modelo.pontos(attrs), 3),
            "padroes_cumpridos": fortes, "antipadroes": anti, "sugestoes": sugestoes[:5],
            "referencias": referencias(modelo, attrs, n_ref),
            "aviso": "A nota mede semelhança com posts que geraram conversa na base; não prevê resultado."}


def _exemplos(modelo: Modelo, attr: str, n: int = 2) -> list[dict]:
    b = modelo.base
    m = b[b["top10"] & b["atributos"].map(lambda s: attr in s)].sort_values("conversa", ascending=False)
    return [{"titulo": t, "url": u} for t, u in zip(m["titulo"].head(n), m["url"].head(n))]


def referencias(modelo: Modelo, attrs: set[str], n: int = 3) -> list[dict]:
    """Posts do top 10% mais parecidos (Jaccard dos atributos), um por perfil."""
    b = modelo.base[modelo.base["top10"]]
    sim = b["atributos"].map(lambda s: len(s & attrs) / len(s | attrs) if (s | attrs) else 0)
    b = b.assign(sim=sim).sort_values(["sim", "conversa"], ascending=False).drop_duplicates("handle")
    return [{"post_id": r.post_id, "titulo": r.titulo, "url": r.url, "perfil": r.nome,
             "conversa": round(float(r.conversa), 2), "similaridade": round(float(r.sim), 2)}
            for r in b.head(n).itertuples()]


# ---------- validação ----------

def _auc(y: np.ndarray, s: np.ndarray) -> float:
    """AUC pelo ranking (Mann-Whitney), sem depender do sklearn."""
    y = np.asarray(y, bool)
    r = pd.Series(s).rank().to_numpy()
    n1, n0 = y.sum(), (~y).sum()
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)) if n1 and n0 else float("nan")


def validar(df: pd.DataFrame, k: int = 5, seed: int = 7) -> pd.DataFrame:
    """Validação cruzada agrupada por perfil: os pesos saem de uns perfis e a nota é testada em outros.

    Agrupar por perfil evita vazamento (o mesmo canal no treino e no teste).
    """
    df = df[df["rankeavel"]].reset_index(drop=True)
    perfis = df["handle"].drop_duplicates().sample(frac=1, random_state=seed).to_list()
    dobra = {h: i % k for i, h in enumerate(perfis)}
    df["dobra"] = df["handle"].map(dobra)
    pts = np.zeros(len(df))
    for f in range(k):
        treino, teste = df[df["dobra"] != f], df["dobra"] == f
        m = treinar(treino)
        pts[teste.to_numpy()] = [m.pontos(a) for a in df.loc[teste, "atributos"]]
    df["pontos_cv"] = pts
    linhas = []
    for v in VISOES:
        linhas.append({"visao": v, "auc_cv": round(_auc(df[v], pts), 3), "posts_top": int(df[v].sum()),
                       "posts": len(df)})
    # lift de conversa por quintil da nota: o 5º quintil conversa mais que o 1º?
    df["quintil"] = pd.qcut(df["pontos_cv"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5])
    q = df.groupby("quintil", observed=True).agg(conversa_mediana=("conversa", "median"),
                                                  pct_top10=("top10", "mean"), pct_top_perfil=("top_perfil", "mean"))
    q[["pct_top10", "pct_top_perfil"]] = (100 * q[["pct_top10", "pct_top_perfil"]]).round(1)
    q["conversa_mediana"] = q["conversa_mediana"].round(2)
    return pd.DataFrame(linhas), q.reset_index()


# ---------- checagem externa: criativos do Impulso ----------

def rubricar_texto(titulo: str, legenda: str, plataforma: str = "instagram", imagem=None) -> dict:
    """Aplica a rubrica a um rascunho (texto e, se houver, a imagem do criativo), com o mesmo VLM da base."""
    from .llm import gerar_json
    from .categorizar import corrigir_hook
    from .rubric import PROMPT_VERSAO, SISTEMA, RubricaVLM, legenda_tamanho, montar_prompt, normalizar_hook
    rub, _ = gerar_json(RubricaVLM, SISTEMA, montar_prompt(titulo, legenda, plataforma, None),
                        [imagem] if imagem else [], versao=PROMPT_VERSAO + ("-imagem" if imagem else "-texto"))
    # mesmos ajustes da base: rótulo no lugar da frase de abertura vira a capa ou o título; pergunta é pergunta
    d = normalizar_hook(corrigir_hook(rub, titulo).model_dump(mode="json"))
    d["legenda_tamanho"] = legenda_tamanho(f"{titulo} {legenda}")
    return d


def checar_impulso(modelo: Modelo) -> pd.DataFrame:
    cri = pd.read_csv(DATA / "impulso" / "meta_ads_criativos.csv")
    linhas = []
    for r in cri.itertuples():
        # a coluna leitura_relatorio comenta o desempenho (vazaria o resultado), então não entra.
        # Sem as imagens dos criativos, só o nome vai para a rubrica; com elas, usar categorizar_post.
        img = DATA / "impulso" / str(r.imagem) if isinstance(getattr(r, "imagem", None), str) else None
        rub = rubricar_texto(str(r.criativo), "", imagem=img if img and img.exists() else None)
        rub["tipo_post"] = "imagem" if r.formato in ("estatico", "anuncio", "story") else "carrossel"
        av = avaliar(modelo, rub, n_ref=0)
        linhas.append({"criativo": r.criativo, "grupo": r.grupo, "ctr_pct": r.ctr_pct, "nota": av["nota"],
                       "padroes": len(av["padroes_cumpridos"]), "antipadroes": len(av["antipadroes"])})
    return pd.DataFrame(linhas)


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    cmd = argv[0] if argv else "validar"
    df = marcar_top_perfil(montar_base())
    if cmd == "validar":
        aucs, quintis = validar(df)
        md = ["# Validação do avaliador", "",
              "Validação cruzada em 5 dobras agrupadas por perfil (pesos de uns canais, teste em outros).", "",
              "AUC: chance de um post do top ter nota maior que um post do resto (0,5 = acaso).", "",
              aucs.to_markdown(index=False), "", "## Conversa por quintil da nota", "",
              quintis.to_markdown(index=False), ""]
        (DATA / "avaliador_validacao.md").write_text("\n".join(md), encoding="utf-8")
        print("\n".join(md))
    elif cmd == "impulso":
        res = checar_impulso(treinar(df))
        res.to_csv(DATA / "impulso" / "checagem_avaliador.csv", index=False, encoding="utf-8")
        print(res.to_markdown(index=False))
        print(res.assign(melhor=res["grupo"] != "pior").groupby("melhor")["nota"].describe())
        print("AUC melhores vs piores:", round(_auc(res["grupo"] != "pior", res["nota"].to_numpy()), 3))
    elif cmd == "post":
        m = treinar(df)
        linha = df[df["post_id"] == argv[1]].iloc[0]
        print(json.dumps(avaliar(m, linha.to_dict()), ensure_ascii=False, indent=2, default=str))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
