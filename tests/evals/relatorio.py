"""Resumo de uma rodada de evals: notas do juiz por métrica, nota interna de aderência e as duas comparadas.

Rodar da raiz logo depois do `deepeval test run`:
  .venv\\Scripts\\python tests/evals/relatorio.py rodada-1
Copia o resultado do deepeval e o saidas.jsonl para tests/evals/resultados/<rodada>/ e escreve resumo.md lá.
"""
import json
import shutil
import sys
from pathlib import Path

import pandas as pd

AQUI = Path(__file__).parent
RAIZ = AQUI.parents[1]


def carregar(rodada: str) -> pd.DataFrame:
    pasta = AQUI / "resultados" / rodada
    pasta.mkdir(parents=True, exist_ok=True)
    if (RAIZ / ".deepeval" / ".latest_test_run.json").exists() and not (pasta / "deepeval.json").exists():
        shutil.copy(RAIZ / ".deepeval" / ".latest_test_run.json", pasta / "deepeval.json")
        shutil.copy(AQUI / "saidas.jsonl", pasta / "saidas.jsonl")
    run = json.loads((pasta / "deepeval.json").read_text(encoding="utf-8"))["testRunData"]
    saidas = {}
    for linha in (pasta / "saidas.jsonl").read_text(encoding="utf-8").splitlines():
        d = json.loads(linha)
        saidas[d["pedido"]] = d
    linhas = []
    for tc in run["testCases"]:
        s = saidas.get(tc["input"], {})
        r = {"pedido": tc["input"], "nota_interna": s.get("nota_aderencia"), "segmento": s.get("segmento"),
             "versoes": s.get("versoes"), "titulo": s.get("criativo", {}).get("titulo")}
        for m in tc.get("metricsData") or []:
            nome = m["name"].replace(" [GEval]", "")
            r[nome] = m.get("score")
            r[f"{nome}·motivo"] = m.get("reason")
        linhas.append(r)
    return pd.DataFrame(linhas)


def resumo(df: pd.DataFrame, rodada: str) -> str:
    metricas = [c for c in df.columns if "·" not in c and c not in
                ("pedido", "nota_interna", "segmento", "versoes", "titulo")]
    limites = {"Fidelidade ao pedido": .7, "Correção factual": .7, "Engajamento qualificado": .6,
               "Execução do roteiro": .6}
    df["juiz_media"] = df[metricas].mean(axis=1)
    md = [f"# Evals do agente · {rodada}", "", f"{len(df)} pedidos. Juiz: Claude Sonnet 5.5 (Claude Code).", "",
          "| Métrica | Média | Passou |", "|---|---:|---:|"]
    for m in metricas:
        md.append(f"| {m} | {df[m].mean():.2f} | {(df[m] >= limites.get(m, .5)).sum()}/{df[m].notna().sum()} |")
    tudo = df[metricas].ge(pd.Series(limites)).all(axis=1).sum()
    md += ["", f"Passou em tudo: **{tudo}/{len(df)}**.", ""]
    ok = df.dropna(subset=["nota_interna"])
    if len(ok) >= 5:
        rho = ok["nota_interna"].rank().corr(ok["juiz_media"].rank())
        md += [f"Spearman nota interna × média do juiz: **{rho:.2f}** (n={len(ok)}).", ""]
    md += ["| Pedido | Interna | " + " | ".join(m.split()[0] for m in metricas) + " |",
           "|---|---:|" + "---:|" * len(metricas)]
    for r in df.sort_values("juiz_media").itertuples():
        md.append(f"| {r.pedido[:70]} | {r.nota_interna} | "
                  + " | ".join(f"{df.loc[r.Index, m]:.2f}" if pd.notna(df.loc[r.Index, m]) else "—"
                               for m in metricas) + " |")
    return "\n".join(md) + "\n"


if __name__ == "__main__":
    rodada = sys.argv[1] if len(sys.argv) > 1 else "rodada"
    df = carregar(rodada)
    texto = resumo(df, rodada)
    (AQUI / "resultados" / rodada / "resumo.md").write_text(texto, encoding="utf-8")
    df.to_csv(AQUI / "resultados" / rodada / "notas.csv", index=False, encoding="utf-8")
    print(texto)
