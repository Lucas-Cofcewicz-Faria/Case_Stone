"""Gera tests/evals/.dataset.json: os 6 pedidos reais (.sementes.json) + variações geradas pelo deepeval.

Usa o Synthesizer (generate_goldens_from_goldens) com o juiz do Claude Code, porque o `deepeval generate`
da linha de comando só aceita modelos de API. Rodar da raiz:
  .venv\\Scripts\\python tests/evals/gerar_dataset.py [variacoes_por_semente=2]
"""
import json
import os
import sys
from pathlib import Path

AQUI = Path(__file__).parent
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "1")
sys.path.insert(0, str(AQUI))

from deepeval.dataset import Golden  # noqa: E402
from deepeval.synthesizer import Synthesizer  # noqa: E402
from deepeval.synthesizer.config import FiltrationConfig, StylingConfig  # noqa: E402

from juiz_claude import JuizClaudeCode  # noqa: E402

ESTILO = StylingConfig(
    scenario="A equipe de conteúdo do Impulso Stone (programa da Stone para micro e pequenos empreendedores) "
             "pede a um agente o roteiro de um vídeo curto que fale com empreendedores de um segmento específico.",
    task="Escrever um criativo de vídeo curto (título, gancho, roteiro, capa, legenda, CTA) que faça esses "
         "empreendedores comentarem, perguntarem ou pedirem algo, sobre o problema citado no pedido.",
    input_format="Uma frase em português do Brasil começando com 'Post do Impulso para', dizendo o tipo de pequeno "
                 "negócio (variar: comida, beleza, varejo, serviços locais, artesanato, autônomos, MEI) e um "
                 "problema ou objetivo concreto do dia a dia (clientes, preço, agenda, fiado, fornecedor, "
                 "divulgação, nota, caixa). Às vezes vago ou com dois problemas, como um pedido real.",
)


def main(por_semente: int = 2) -> None:
    sementes = json.loads((AQUI / ".sementes.json").read_text(encoding="utf-8"))
    juiz = JuizClaudeCode("sonnet")
    synth = Synthesizer(model=juiz, styling_config=ESTILO, max_concurrent=4,
                        filtration_config=FiltrationConfig(critic_model=juiz))
    novos = synth.generate_goldens_from_goldens(
        [Golden(input=s["input"]) for s in sementes], max_goldens_per_golden=por_semente,
        include_expected_output=False)
    vistos = {s["input"] for s in sementes}
    saida = [{**s, "additional_metadata": {**s.get("additional_metadata", {})}} for s in sementes]
    for g in novos:
        if g.input not in vistos:
            vistos.add(g.input)
            saida.append({"input": g.input, "additional_metadata": {"origem": "deepeval-goldens"}})
    (AQUI / ".dataset.json").write_text(json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(saida)} pedidos ({len(sementes)} reais + {len(saida) - len(sementes)} gerados)")
    for s in saida:
        print("-", s["input"])


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2)
