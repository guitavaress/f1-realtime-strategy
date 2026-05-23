# F1 Realtime Strategy

Aplicação de predição e estratégia ao vivo para corridas de F1.
Projeto irmão do [`f1-data-pipeline`](https://github.com/guitavaress/f1-data-pipeline) —
consome os marts de degradação Pirelli (read-only via SQL) e adiciona predição
pré-evento, ingestão live, comparação live × predito e simulação Monte Carlo de
estratégias (FIA Art. 30.5).

## Stack

| Camada           | Tecnologia                              | Porta  |
|------------------|-----------------------------------------|--------|
| API + Web        | FastAPI + Jinja2 + HTMX                 | 8081   |
| Charts           | Plotly (server-rendered HTML)           | —      |
| Pub/sub          | Redis 7                                 | 6379   |
| Banco            | PostgreSQL 15 (externo — pipeline)      | 5432   |
| Ingestão         | FastF1 + undercut-f1 (sidecar .NET)     | —      |
| Forecast clima   | Open-Meteo API                          | —      |

## Como Rodar

Pré-requisito: o Postgres do `f1-data-pipeline` precisa estar de pé
(este projeto não escreve em `raw.*`, `staging.*` ou `marts.*` — apenas lê).

```bash
# 1. Sobe o Postgres do pipeline
cd ../f1-data-pipeline
docker compose up -d postgres

# 2. Instala dependências e roda a API (migrations aplicam no startup)
cd ../f1-realtime-strategy
uv sync
uv run uvicorn realtime.api.main:app --reload --port 8081
```

Abrir: <http://localhost:8081/next-event>

## Schemas Próprios

Este projeto cria e escreve apenas em:

- `predictions.*` — previsões pré-evento (curva laptime × composto × tyre life)
- `live.*` — laps capturados ao vivo pelo livetiming worker
- `comparisons.*` — delta entre actual e predicted (calibração)

Migrations em `migrations/*.sql` rodam idempotentemente no startup da API.

## Relação com `f1-data-pipeline`

| Aspecto                  | Pipeline                       | Realtime                          |
|--------------------------|--------------------------------|-----------------------------------|
| Responsabilidade         | Ingestão histórica + marts     | Predição + live + simulação       |
| Escreve em               | `raw`, `staging`, `marts`      | `predictions`, `live`, `comparisons` |
| Lê de                    | FastF1 (sessões fechadas)      | FastF1 livetiming + marts (SQL)   |
| Orquestração             | Airflow + dbt (Cosmos)         | FastAPI + Redis pub/sub           |

O acoplamento é **só pelo banco**, não pelo código. Atualizar o pipeline
não exige rebuild deste projeto, desde que `circuit_key` e os schemas dos
marts permaneçam estáveis.

Para detalhes de convenções, fases de implementação e o que **não** alterar
sem discussão, ver [`CLAUDE.md`](./CLAUDE.md).
