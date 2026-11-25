# Validação do avaliador

Validação cruzada em 5 dobras agrupadas por perfil (pesos de uns canais, teste em outros).

AUC: chance de um post do top ter nota maior que um post do resto (0,5 = acaso).

| visao      |   auc_cv |   posts_top |   posts |
|:-----------|---------:|------------:|--------:|
| top10      |    0.55  |         263 |    2618 |
| top_perfil |    0.534 |         523 |    2618 |

## Conversa por quintil da nota

|   quintil |   conversa_mediana |   pct_top10 |   pct_top_perfil |
|----------:|-------------------:|------------:|-----------------:|
|         1 |               0.21 |         7.1 |             17.6 |
|         2 |               0.39 |         9.6 |             17.4 |
|         3 |               0.63 |         9.4 |             20.4 |
|         4 |               1.4  |        12   |             21   |
|         5 |               1.35 |        12.2 |             23.5 |
