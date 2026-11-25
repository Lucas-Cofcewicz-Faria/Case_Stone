"""Gera os criativos de exemplo do playbook: um pedido por segmento, rodado pelo agente completo.

Cada criativo sai com referências reais, a nota de aderência, as versões testadas e o aviso de
confiança do segmento. Os arquivos vão para playbook/criativos/ (um .md por pedido + um índice .json).

Uso (precisa do Ollama; ~1 min por versão, até 3 versões por pedido):
  python -m stone.playbook
  python -m stone.playbook 2 4      # só os pedidos 2 e 4
"""
from __future__ import annotations

import json
import sys
import time

from .config import DATA
from .agente.grafo import rodar

SAIDA = DATA.parent / "playbook" / "criativos"

# cada pedido é um post do Impulso Stone falando com empreendedores de um segmento
PEDIDOS = [
    ("alimentacao", "Post do Impulso para confeiteiras que vendem bolo por encomenda pelo WhatsApp "
                    "e não sabem quanto cobrar"),
    ("beleza", "Post do Impulso para donas de salão de beleza pequeno com a agenda vazia "
               "na terça e na quarta"),
    ("varejo", "Post do Impulso para donas de loja de roupas de bairro que também querem vender "
               "pelo Instagram"),
    ("servicos", "Post do Impulso para donos de lavanderia de bairro que querem atender os prédios "
                 "da região"),
    ("autonomos", "Post do Impulso para artesãs autônomas, MEI, que fazem lembrancinhas personalizadas "
                  "e se perdem com a nota fiscal e o DAS"),
]


def main(indices: list[int]) -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    indice_path = SAIDA / "indice.json"
    indice = json.loads(indice_path.read_text(encoding="utf-8")) if indice_path.exists() else {}
    for i in indices:
        rotulo, pedido = PEDIDOS[i - 1]
        t0 = time.time()
        s = rodar(pedido)
        seg, conf = s["plano"]["segmento"], s["padroes"]["confianca"]
        nota = s["melhor"]["avaliacao"]["nota"]
        nome = f"{i:02d}_{rotulo}.md"
        cab = (f"> **Pedido:** {pedido}  \n> **Segmento classificado pelo agente:** `{seg}` · "
               f"confiança dos padrões: {conf} · gerado em {time.strftime('%d/%m/%Y')} "
               f"com qwen3-vl:8b local em {time.time() - t0:.0f} s\n\n")
        (SAIDA / nome).write_text(cab + s["resposta"] + "\n", encoding="utf-8")
        indice[str(i)] = {"arquivo": nome, "rotulo": rotulo, "pedido": pedido, "segmento": seg,
                          "confianca": conf, "nota": nota, "titulo": s["melhor"]["criativo"]["titulo"],
                          "versoes": [h["nota"] for h in s["historico"]]}
        indice_path.write_text(json.dumps(indice, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{nome}: {seg} · nota {nota} · versões {indice[str(i)]['versoes']} · {time.time() - t0:.0f}s",
              flush=True)


if __name__ == "__main__":
    main([int(x) for x in sys.argv[1:]] or list(range(1, len(PEDIDOS) + 1)))
