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

# 2. Sobe o Redis local (pub/sub do livetiming)
cd ../f1-realtime-strategy
docker compose up -d redis

# 3. Instala dependências e roda a API (migrations aplicam no startup)
uv sync
uv run uvicorn realtime.api.main:app --reload --port 8081
```

Abrir: <http://localhost:8081/next-event>

### Replay de sessão histórica (livetiming worker)

```bash
# Reaproveita cache do pipeline; --speed 30 colapsa Bahrein 2024 (~2.5h) em ~5 min
$env:FASTF1_CACHE_DIR='C:\Claude\f1-data-pipeline\cache'
uv run python -m realtime.ingest.livetiming_worker --year 2024 --round 1 --session R --speed 30
```

O worker imprime o `session_id` (UUID) no stdout. Abrir <http://localhost:8081/live/{session_id}> para acompanhar o feed, ou <http://localhost:8081/compare/{session_id}> para ver os residuais contra a previsão.

## Rotas

| Rota                          | Descrição                                                       |
|-------------------------------|-----------------------------------------------------------------|
| `GET /next-event`             | Previsão pré-evento: alocação Pirelli + chart de degradação ±1σ |
| `GET /live/{session_id}`      | Feed ao vivo (HTMX) consumindo o WebSocket abaixo                |
| `WS  /ws/live?session_id=...` | Push de cada lap publicado em `lap:{session_id}` no Redis        |
| `GET /compare`                | Picker — lista sessões em `live.session`                         |
| `GET /compare/{session_id}`   | Delta actual × predicted: KPIs + scatter ±1σ + tabela por composto |
| `POST /strategy/simulate`     | Monte Carlo de estratégias (Fase 4, ainda não implementado)      |

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
