# CLAUDE.md — f1-realtime-strategy

Guia de contexto para o Claude Code trabalhar neste repositório.

---

## Visão Geral

Projeto irmão do `f1-data-pipeline`. Consome os marts maduros de degradação Pirelli
(leitura SQL pura, sem importar código Python do pipeline) e adiciona:

1. **Predição pré-evento** — curvas de laptime esperado por composto dado clima + perfil circuito.
2. **Ingestão live** — `fastf1.livetiming` → Redis pub/sub → WebSocket no browser.
3. **Comparação live × predito** — delta e score de calibração por stint.
4. **Simulador Monte Carlo** — ranking de estratégias com distribuição de race time (FIA Art. 30.5).

---

## Stack

| Camada           | Tecnologia                            | Porta  |
|------------------|---------------------------------------|--------|
| API + Web        | FastAPI + Jinja2 + HTMX               | 8081   |
| Charts           | Plotly (server-rendered HTML divs)    | —      |
| Pub/sub          | Redis 7                               | 6379   |
| Banco            | PostgreSQL 15 (externo — f1-data-pipeline) | 5432 |
| Ingestão         | FastF1 (Python)                       | —      |
| Forecast clima   | Open-Meteo API (sem key, free)        | —      |

Credenciais Postgres (dev): `airflow / airflow`, banco `f1`.
Redis sem senha em dev.

---

## Arquitetura de Dados

```
marts.* (f1-data-pipeline, read-only)
    │
    ├── tyre_degradation          ← deg média circuito × composto × ano
    ├── tyre_weather_profile      ← deg por bucket de track temp (input principal)
    ├── circuit_tyre_profile      ← perfil de agressividade (fallback)
    └── pirelli_compound_allocations (seed) ← mapeamento C1-C5 por GP
            │
            ▼
predictions.race_forecast         ← predição gerada antes do evento
predictions.compound_curve        ← curva laptime(tyre_life) por composto

live.session / live.lap           ← laps capturados pelo livetiming_worker

comparisons.lap_residual          ← delta actual vs predicted (calibração futura)
```

---

## Estrutura de Diretórios

```
f1-realtime-strategy/
├── CLAUDE.md
├── README.md
├── docker-compose.yml          # API + Redis (Postgres é externo)
├── Dockerfile                  # python:3.11-slim + uv
├── pyproject.toml              # uv — dependências e metadados
├── .env.example                # variáveis necessárias (nunca commitar .env real)
│
├── realtime/                   # Package principal
│   ├── config.py               # Env vars via pydantic-settings ou os.getenv
│   ├── db.py                   # SQLAlchemy engine + helpers de leitura dos marts
│   ├── ingest/
│   │   ├── fastf1_session.py   # Carrega sessão fechada (adaptado de load_fastf1.py)
│   │   ├── livetiming_worker.py# fastf1.livetiming + parser → Redis pub
│   │   └── schedule.py         # Próximo evento via fastf1.get_event_schedule()
│   ├── predict/
│   │   ├── degradation.py      # Query tyre_weather_profile / circuit_tyre_profile
│   │   ├── allocation.py       # Query pirelli_compound_allocations
│   │   ├── weather.py          # Open-Meteo + heurística track temp
│   │   └── model.py            # Combina os 3 → compound_curve + grava predictions.*
│   ├── simulate/
│   │   ├── strategy.py         # Estratégias canônicas; is_dry_legal() (FIA Art. 30.5)
│   │   ├── montecarlo.py       # N simulações → distribuição race time por estratégia
│   │   └── pitloss.py          # Pit loss por circuito (calibrado de dados históricos)
│   ├── compare/
│   │   └── residuals.py        # Live laps vs predicted → delta + grava comparisons.*
│   └── api/
│       ├── main.py             # FastAPI app, routers, lifespan
│       ├── routes/
│       │   ├── next_event.py   # GET /next-event
│       │   ├── live.py         # WebSocket /ws/live
│       │   ├── strategy.py     # POST /strategy/simulate
│       │   └── compare.py      # GET /compare/{session_id}
│       ├── templates/          # Jinja2
│       └── static/             # HTMX, Alpine.js, Plotly bundle, CSS
│
├── migrations/
│   ├── 001_predictions_schema.sql
│   ├── 002_live_schema.sql
│   └── 003_comparisons_schema.sql
│
├── tests/
│   ├── test_degradation_predictor.py
│   ├── test_montecarlo.py
│   └── fixtures/               # Dumps SQL pequenos dos marts para testes offline
│
└── notebooks/
    ├── 01_baseline_degradation.ipynb
    └── 02_montecarlo_validation.ipynb
```

---

## Convenções Importantes

### Banco e Schemas
- Este projeto **nunca escreve** em `raw.*`, `staging.*`, `marts.*` — apenas lê.
- Schemas próprios: `predictions`, `live`, `comparisons`.
- Rodar `migrations/` manualmente antes do primeiro uso: `psql -U airflow -d f1 -f migrations/001_predictions_schema.sql` (idem 002, 003).
- Colunas de composto sempre **UPPER**: `SOFT`, `MEDIUM`, `HARD`, `INTERMEDIATE`, `WET`.
- Compound name físico: `C1`–`C5` (igual ao pipeline). Disponível apenas a partir de 2018.
- `circuit_key` deve ser idêntico ao gerado pelo `f1-data-pipeline` (derivado de `event_name`).

### Python / FastAPI
- Python **3.11** (`.python-version` lockado).
- Gerenciador de pacotes: **uv** (`uv sync`, `uv run`). Nunca `pip install` direto.
- Variáveis de ambiente em `realtime/config.py` via `os.getenv` com defaults de dev.
- `realtime/db.py` expõe `engine` (SQLAlchemy) e `get_db()` para FastAPI Depends.
- Routes **não** acessam o banco diretamente — delegam para `predict/`, `simulate/`, `compare/`.
- Templates Jinja2 em `realtime/api/templates/` — base.html inclui HTMX e Plotly CDN.
- Charts são Plotly `fig.to_html(full_html=False, include_plotlyjs=False)` injetados no template.

### Redis
- Workers publicam em channels `lap:<session_id>` (JSON por mensagem).
- WebSocket route (`/ws/live`) faz subscribe e faz push pro browser via `asyncio`.
- Sem filas complexas na Fase 0–2 — Redis pub/sub simples é suficiente.

### Regra FIA Art. 30.5
- `simulate/strategy.py` expõe `is_dry_legal(compounds: list[str]) -> bool`.
- Regra: em corrida seca, a estratégia precisa usar ≥2 compostos slick distintos.
- Qualquer endpoint que retorne estratégias secas **deve** filtrar com `is_dry_legal`.
- Não remover essa validação.

### Testes
- Fixtures em `tests/fixtures/` são dumps SQL mínimos que populam `marts.*` localmente.
- Testes de modelo (`test_degradation_predictor.py`) rodam offline usando as fixtures.
- Testes de Monte Carlo validam distribuição estatística, não valor exato.

---

## Conexão com f1-data-pipeline

A rede Docker `f1-data-pipeline_default` é declarada como `external: true` no
`docker-compose.yml` deste projeto. Isso permite que o container `api` alcance o
container `postgres` pelo hostname `postgres` (mesmo nome de serviço).

**Pré-requisito**: `docker compose up` do `f1-data-pipeline` deve estar rodando antes
de subir este projeto.

Para desenvolvimento local sem Docker, use `DATABASE_URL=postgresql://airflow:airflow@localhost:5432/f1`.

---

## Comandos Frequentes

```bash
# Subir API + Redis (Postgres externo precisa estar up)
docker compose up --build

# Rodar migrações (uma vez por ambiente limpo)
psql -U airflow -d f1 -h localhost -f migrations/001_predictions_schema.sql
psql -U airflow -d f1 -h localhost -f migrations/002_live_schema.sql
psql -U airflow -d f1 -h localhost -f migrations/003_comparisons_schema.sql

# Instalar deps localmente
uv sync

# Rodar API localmente (sem Docker)
uv run uvicorn realtime.api.main:app --reload --port 8081

# Rodar testes
uv run pytest

# Verificar conexão com Postgres (Fase 0)
uv run python -c "from realtime.db import engine; print(engine.execute('select count(*) from marts.tyre_degradation').scalar())"
```

---

## Status de Implementação

### Fase 0 — Setup ✅ Concluída
Todos os arquivos criados. Nada foi executado ainda — nenhuma dependência instalada, nenhum container rodando.

### Fase 1 — Preditor pré-evento ✅ Código pronto, aguardando primeira execução
Módulos implementados (todos em `realtime/`):
- `config.py` — env vars com defaults de dev
- `db.py` — SQLAlchemy engine + `read_df()`
- `ingest/schedule.py` — `next_event()` via fastf1
- `predict/allocation.py` — query `staging.pirelli_compound_allocations`
- `predict/degradation.py` — `get_weather_profile()`, `get_circuit_profile()`, `get_baseline_pace()`
- `predict/weather.py` — Open-Meteo + heurística track temp por circuito
- `predict/model.py` — `generate_forecast()` + `get_latest_forecast()`
- `api/main.py` — aplica migrations automaticamente no startup (idempotente)
- `api/routes/next_event.py` — GET `/next-event` com Plotly chart ±1σ
- `api/templates/next_event.html` + `api/static/style.css` — dark theme

**Primeira execução (fazer na ordem):**
```bash
# 1. Postgres do pipeline precisa estar up (banco compartilhado)
cd C:\Claude\f1-data-pipeline
docker compose up -d postgres

# 2. Instalar dependências do realtime
cd C:\Claude\f1-realtime-strategy
uv sync

# 3. Rodar a API (migrations criam schemas automaticamente no startup)
uv run uvicorn realtime.api.main:app --reload --port 8081

# 4. Abrir no browser
# http://localhost:8081/next-event
```

**Dependência crítica:** `staging.pirelli_compound_allocations` precisa existir (criada por `dbt seed` no pipeline). Se não existir, `predict/allocation.py` retorna `{}` mas a previsão ainda roda com `compound_name = NULL`.

### Fase 2 — Ingestão live 🔲 Não iniciada
Stub criado em `ingest/livetiming_worker.py` e `ingest/undercut_connector.py`.
Requer: implementar worker FastF1 livetiming → Redis pub/sub + rota WebSocket `/ws/live`.

### Fase 3 — Comparação live × predito 🔲 Não iniciada
Stub em `compare/residuals.py`. Depende da Fase 2.

### Fase 4 — Monte Carlo strategy lab 🔲 Não iniciada
`simulate/strategy.py` e `simulate/pitloss.py` implementados (valores hardcoded).
`simulate/montecarlo.py` é stub — depende de Fase 1 estável.

---

## O que NÃO Alterar Sem Discussão

- `is_dry_legal()` em `simulate/strategy.py` — regra FIA Art. 30.5, replicada do pipeline.
- Schemas `predictions`, `live`, `comparisons` — contratos com as migrations; alterar exige nova migration.
- `circuit_key` — deve ser idêntico ao gerado pelo `f1-data-pipeline` para JOINs funcionarem.
- Filtro `year >= 2018` em qualquer lógica de `compound_name` — antes disso não há dados C1-C5.
- Credenciais nunca no código — sempre via `.env` / variáveis de ambiente.
