# Evals do agente de criativos

Mede se o agente (`stone.agente.grafo`) entrega bons criativos, com um juiz **independente** do modelo que escreve.
A nota de aderência interna (0–100) não entra no julgamento: ela é comparada com ele.

## Como funciona

- **Pedidos:** `.dataset.json` tem 18 pedidos. São os 6 reais (`.sementes.json`: os 5 do playbook + o preset do ar-condicionado da demo) e 12 variações geradas pelo deepeval (`gerar_dataset.py`, `Synthesizer.generate_goldens_from_goldens`), com casos difíceis: duração máxima, dois problemas no mesmo pedido, NFS-e com retenção de ISS.
- **Agente rastreado:** `test_agente.py` roda o grafo LangGraph com o `CallbackHandler` do deepeval. Com `STONE_TRACE=1`, ligado no `conftest.py`, cada chamada ao Qwen vira um span `llm`. O juiz lê só o criativo, sem a nota interna nem as referências.
- **Juiz:** `juiz_claude.py` roda o Claude Sonnet 5.5 pelo Claude Code (`claude -p`), na assinatura, sem chave de API. Cada chamada sai isolada: sem ferramentas, sem MCP, sem settings, plugins ou hooks do usuário e sem salvar sessão. O uso de cada chamada fica em `juiz_uso.jsonl`.
- **Métricas** (`metrics.py`, GEval):

| Métrica | Limite | O que mede |
|---|---:|---|
| Fidelidade ao pedido | 0,7 | O assunto central é o problema específico do pedido. Trocar por um tema genérico (nota do MEI, preço) é penalizado. |
| Correção factual | 0,7 | Contas, taxas e regras do MEI estão certas, e o Impulso não aparece como app. Usa 4 fatos de referência como `context`. |
| Engajamento qualificado | 0,6 | O CTA é concreto e fácil de comentar, o gancho cabe em 3 s e o post não tem tom inspiracional nem promessa. |
| Execução do roteiro | 0,6 | Cenas com imagem e fala, sem repetição. O roteiro entrega o que promete, e a capa, a legenda e a duração são coerentes. |

O `TaskCompletionMetric` ficou de fora: ele lê o trace inteiro do LangGraph (~115 mil tokens por pedido), o que dava 85% do custo, e mede o mesmo que a fidelidade.

## Rodar

Da raiz do repo, com o Ollama ligado e o Claude Code logado:

```powershell
.venv\Scripts\python tests/evals/gerar_dataset.py          # só para refazer os pedidos
.venv\Scripts\deepeval test run tests/evals/test_agente.py --identifier minha-rodada -i
.venv\Scripts\python tests/evals/relatorio.py minha-rodada  # resumo.md + notas.csv em resultados/minha-rodada/
```

Uma rodada leva ~25–30 min (GPU) e ~70 chamadas do juiz (~270 mil tokens de entrada). O `pytest` normal não entra aqui (`norecursedirs` no `pyproject.toml`).

## Resultados

Cada rodada tem `resultados/<rodada>/resumo.md` (tabela por pedido) e `notas.csv` (notas e motivos do juiz). O histórico e a leitura estão no README da raiz, seção 6.
