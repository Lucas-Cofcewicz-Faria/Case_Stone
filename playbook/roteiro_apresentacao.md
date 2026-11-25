# Roteiro da apresentação · 25/11 na Stone

Uns 8 minutos de fala + demo ao vivo. Cada bloco tem a frase que precisa ficar na cabeça de quem assiste.

## Antes de entrar na sala (15 min antes)

- [ ] Notebook **na tomada**, modo de energia **turbo**, suspensão desligada (se dormir, a API e o site caem).
- [ ] Feche jogos, Chrome pesado e qualquer coisa que use a GPU (o Qwen precisa de ~8 GB de VRAM).
- [ ] Suba a API: na raiz do repo, `$env:PYTHONPATH="src"; .venv\Scripts\python -m stone.api`
- [ ] Suba o site: em `web/`, `npx next dev -p 3100` → abra `http://localhost:3100/?semintro`
- [ ] Aqueça o modelo: avalie um post real (tecla 7) e um rascunho, para o Ollama já carregar o Qwen na GPU.
- [ ] Confira o selo no topo da máquina: **"ao vivo"** = API ligada; **"demo"** = caiu no modo gravado (ainda funciona, ver plano B).
- [ ] Deixe aberto numa aba: `playbook/playbook.md` e o README (gráficos).

## 1. O problema (1 min)

> **"Reação não é ação."**

- Mostre a tabela do PowerPoint: o depoimento da Cristina teve 3.255 de engajamento e 0,82% de CTR. O "Empreendedor(a), queremos..." teve 8,82%.
- Ranking por curtidas premiaria o post errado. O projeto mede **conversa**: quem comenta, pergunta ou pede algo.

## 2. A métrica e a base (1 min)

> **"De cada mil pessoas que viram, quantas comentaram ou pediram algo."**

- `conversa = (comentários + 2 · intenção) ÷ views × 1000`. Curtida não entra.
- 3.548 Shorts de 44 canais do nicho MPE, pela API oficial do YouTube. 11 mil comentários lidos para achar intenção ("quero", "qual o link", "funciona pra MEI?").
- Só 7,4% do top por conversa também está no top por ER: as métricas escolhem posts diferentes.

## 3. O que gera conversa (1 min)

> **"Pergunta, dor concreta, tom de conversa. Promessa e frase inspiracional somem do topo."**

- Gráfico de lift (`playbook/graficos/padroes.svg`).
- Deixe claro: são associações, não receita.

## 4. Demo ao vivo (3 min)

1. **Rascunho fraco:** digite algo genérico no campo de título ("Acredite no seu sonho de empreender"), ENTRA. Nota baixa, extrato com as sugestões "de → para".
2. **Post real do top:** tecla 7, 8 ou 9. Nota alta, QR code do post original.
3. **Agente:** escolha o preset (salão ou confeitaria) e aperte ENTRA. Enquanto ele roda (~1 min), explique o ciclo: entende o pedido → busca padrões → busca posts reais → escreve → **o avaliador dá nota** → reescreve se ficar abaixo de 60.
4. Abra o extrato e mostre: roteiro, CTA, nota e as referências reais.

## 5. Funciona no público do Impulso? (1 min)

> **"Separa o melhor do pior, mas não escolhe o vencedor."**

- Os 16 criativos do PowerPoint, avaliados pela imagem, com pesos aprendidos só no YouTube.
- Melhores: média 52. Piores: média 31. AUC 0,75.
- Acertou a Cristina (11) e o POV (9). Errou o "Empreendedor(a), queremos..." (25).

## 6. Como sabemos se o agente é bom? (40 s)

> **"Um juiz mais forte corrige a prova, e a nota do próprio sistema não basta."**

- 18 pedidos (6 reais + 12 gerados) passam pelo agente, e o Claude julga cada criativo em 4 critérios: fidelidade ao pedido, fatos, engajamento e execução (README, seção 6).
- O achado: o agente fugia do pedido para o tema que mais pontua (a lavanderia virava "nota do MEI"). Corrigido, a fidelidade subiu de 0,40 para 0,60 e os fatos, de 0,46 para 0,55.
- A nota de aderência não acompanha o juiz (Spearman ≈ 0): ela compara com o nicho, não diz se o texto é bom. Por isso existe a revisão humana.

## 7. Limites e próximos passos (1 min)

> **"A nota é para revisar um rascunho, não para prometer resultado."**

- AUC 0,55 na validação por perfil: o sinal existe, mas é fraco. Base só do YouTube; a rubrica vê a capa e o texto, não o vídeo.
- Próximo: rodar no Instagram do Impulso com a conta profissional, usar os Insights da Stone (salvamentos, cliques) como alvo e testar os criativos do agente em A/B.

## Plano B

| Se... | Faça |
|---|---|
| A API não sobe ou o selo mostra "demo" | Siga a demo: posts reais (7/8/9) e o agente gravado (salão, 73/100) funcionam sem a API. Diga que é a execução gravada. |
| O agente demora mais de 2 min | Fale do playbook enquanto espera; se travar, ANULA e use o modo gravado. |
| O site não abre | Abra `playbook/playbook.md` e os criativos em `playbook/criativos/`. |
| Perguntarem "isso prevê resultado?" | Não. O TAPI (4.3) deixa modelo preditivo fora do escopo; a nota mede aderência ao que já gerou conversa (4.2). |
| Perguntarem "como vocês sabem que o criativo é bom?" | Evals com juiz independente (README, seção 6). A nota interna mede aderência ao nicho; qualidade e fatos quem mede é o juiz, e no fim a revisão humana. |
| Perguntarem "por que não Instagram?" | A Graph API exige conta profissional + Página. O coletor está pronto; o método foi provado no YouTube. |
