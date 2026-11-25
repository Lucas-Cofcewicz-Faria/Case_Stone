"""Métricas das evals do agente de criativos. O juiz é o Claude Sonnet 5.5 pelo Claude Code (juiz_claude.py,
na assinatura, sem chave de API), mais forte que o Qwen 8B que escreve: assim o modelo não corrige a própria prova.

A nota de aderência interna (0–100) NÃO entra aqui: ela mede semelhança com a base e é justamente o que
queremos checar contra um julgamento independente (ver relatorio.py).
"""
from deepeval.metrics import GEval
from deepeval.test_case import SingleTurnParams as P

from juiz_claude import JuizClaudeCode

JUIZ = JuizClaudeCode("sonnet")

# fatos de referência que o juiz recebe como `context` (só o que é estável e verificável)
FATOS = [
    "O Impulso Stone é um programa de conteúdo e capacitação da Stone para micro e pequenos empreendedores. "
    "Não é um aplicativo: não emite nota fiscal, não cobra taxas e não tem funções de software.",
    "O DAS do MEI é um valor fixo mensal, pago todo mês mesmo sem vendas; não é cobrado por venda.",
    "O MEI emite nota fiscal de serviço (NFS-e) pelo Emissor Nacional do governo, sem custo. "
    "Emitir a nota não tem taxa; a nota é obrigatória quando o cliente é empresa (CNPJ).",
    "Os posts são do Impulso Stone falando com EMPREENDEDORES de um segmento (o público), "
    "não um post do próprio negócio para os clientes dele.",
]

FIDELIDADE = GEval(
    name="Fidelidade ao pedido",
    evaluation_steps=[
        "No pedido (input), identifique o tipo de negócio e o problema ou objetivo ESPECÍFICO citado "
        "(ex.: 'atender os prédios da região', 'agenda vazia na terça', 'vender pelo Instagram').",
        "Verifique se o assunto central do criativo (título, gancho, roteiro e CTA) trata desse problema "
        "específico e dá algo útil sobre ele.",
        "Penalize forte se o criativo troca o problema do pedido por outro assunto genérico "
        "(ex.: nota fiscal do MEI, precificação ou DAS quando o pedido não fala disso). "
        "Citar outro assunto de passagem é aceitável; virar o tema principal não é.",
        "Verifique se o post fala com os empreendedores desse segmento (publicado pelo Impulso), "
        "e não com os clientes finais do negócio.",
    ],
    evaluation_params=[P.INPUT, P.ACTUAL_OUTPUT],
    threshold=0.7, model=JUIZ,
)

CORRECAO = GEval(
    name="Correção factual",
    evaluation_steps=[
        "Liste toda afirmação de fato do criativo: números, contas, preços, taxas, regras do MEI, "
        "funções de produtos ou do Impulso.",
        "Confira cada uma contra o contexto e contra o conhecimento geral sobre MEI e pequenos negócios no Brasil.",
        "Penalize forte: conta aritmética errada, taxa ou regra inventada, o Impulso descrito como app, "
        "o DAS descrito como cobrança por venda, promessa de função que não existe.",
        "Um criativo sem afirmações de fato duvidosas tira nota alta; não penalize por ser genérico.",
    ],
    evaluation_params=[P.INPUT, P.ACTUAL_OUTPUT, P.CONTEXT],
    threshold=0.7, model=JUIZ,
)

ENGAJAMENTO = GEval(
    name="Engajamento qualificado",
    evaluation_steps=[
        "O objetivo do post é fazer o empreendedor COMENTAR, PERGUNTAR ou PEDIR algo, não curtir nem viralizar.",
        "Verifique se o CTA pede uma ação concreta, fácil de comentar e ligada ao tema "
        "(contar a própria situação, tirar uma dúvida, pedir um material), e não um 'curte e compartilha'.",
        "Verifique se o gancho dos 3 primeiros segundos é curto o bastante para ser dito em ~3 s (até ~15 palavras) "
        "e abre com uma pergunta ou uma dor concreta do segmento.",
        "Penalize tom inspiracional genérico, promessa de resultado ('fature o dobro') e frases com que "
        "todo mundo concorda e ninguém precisa responder.",
    ],
    evaluation_params=[P.INPUT, P.ACTUAL_OUTPUT],
    threshold=0.6, model=JUIZ,
)

EXECUCAO = GEval(
    name="Execução do roteiro",
    evaluation_steps=[
        "Verifique se cada cena do roteiro mostra algo novo e avança a mensagem (sem cenas repetidas) "
        "e diz o que aparece na imagem e o que a pessoa fala.",
        "Verifique se o roteiro ENTREGA o que promete: se diz 'vou te mostrar a fórmula', a fórmula aparece.",
        "Verifique se título, texto na tela e legenda são frases diferentes, a capa tem até 8 palavras "
        "e a legenda tem 2 a 4 frases terminando no pedido.",
        "Verifique se a duração declarada combina com o tamanho do roteiro e se o texto está em português do "
        "Brasil natural, sem frases sem sentido.",
    ],
    evaluation_params=[P.INPUT, P.ACTUAL_OUTPUT],
    threshold=0.6, model=JUIZ,
)

# TaskCompletionMetric ficou de fora: ele lê o trace inteiro do LangGraph (padrões, referências e prompts no
# estado), ~115 mil tokens por pedido, 85% do custo do juiz, e mede o mesmo que a Fidelidade ao pedido.
AGENTE_TRACE_METRICS = [
    FIDELIDADE,
    CORRECAO,
    ENGAJAMENTO,
    EXECUCAO,
]
