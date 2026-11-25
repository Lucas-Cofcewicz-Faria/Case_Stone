# Relatório de qualidade da base

Gerado em 2026-11-18 15:14 UTC.

| Item | Valor |
|---|---|
| posts coletados | 4050 |
| perfis coletados | 52 |
| perfis inativos | ['marcelopedrosa (youtube)', 'marketingpequenosnegocios (youtube)', 'meilucrativo (youtube)', 'pamelacavalcanteadm (youtube)', 'rendaextraenegocios (youtube)', 'sebraeminas (youtube)', 'seviramei (youtube)'] |
| posts descartados menos 14 dias | 387 |
| posts na base | 3548 |
| posts rankeaveis | 2618 |
| posts abaixo do minimo de views | 907 |
| curtidas ocultas | 92 |
| posts com intencao estimada | 1723 |
| comentarios lidos | 11093 |
| perfis na base | 44 |
| por plataforma | {'youtube': 3548} |
| perfis por faixa | {'medio': 15, 'grande': 15, 'micro': 14} |
| periodo | ('2021-02-19', '2026-11-04') |
| posts no top10 | 263 |
| perfis no top10 | 35 |
| top10 por faixa | {'grande': 125, 'medio': 85, 'micro': 53} |
| sobreposicao top10 conversa vs er | 0.074 |
| spearman conversa vs er | 0.277 |

## Sensibilidade do peso de intenção

Quanto o top 10% de conversa muda com outro peso para comentários com intenção (Jaccard contra o primeiro cenário).

|   peso_intencao |   n_top |   jaccard_vs_primeiro |
|----------------:|--------:|----------------------:|
|               2 |     263 |                 1     |
|               1 |     263 |                 0.865 |
|               4 |     263 |                 0.777 |

## Critérios aplicados

- Métrica principal: conversa = (comentários + 2·comentários com intenção) ÷ views × 1000. Curtidas não entram.
- Ranking só com 300+ views; no máximo 15 posts por perfil no top 10%.
- ER (curtidas + comentários) ÷ seguidores, recomendada no TAPI, é calculada e comparada lado a lado.
- Só posts com 14+ dias de publicação.
- Só perfis com pelo menos um post nos últimos 12 meses.
- Posts com curtidas ocultas ou perfil sem seguidores ficam fora do ranking de ER (a conversa não usa curtidas).
- Comentários com intenção = taxa de intenção na amostra lida × total de comentários do post.
- Seguidores e inscritos são os da data da coleta, não os da data do post.
