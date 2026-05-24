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

# Subir só o Redis (porta 6379 exposta no host para rodar worker/API fora do compose)
docker compose up -d redis

# Migrations rodam idempotentemente no startup da API (api/main.py::_run_migrations).
# Aplicação manual (opcional, exige psql no PATH):
psql -U airflow -d f1 -h localhost -f migrations/001_predictions_schema.sql
psql -U airflow -d f1 -h localhost -f migrations/002_live_schema.sql
psql -U airflow -d f1 -h localhost -f migrations/003_comparisons_schema.sql
psql -U airflow -d f1 -h localhost -f migrations/004_lap_residual_stddev.sql
psql -U airflow -d f1 -h localhost -f migrations/005_lap_residual_pk_forecast.sql

# Instalar deps localmente
uv sync

# Rodar API localmente (sem Docker)
uv run uvicorn realtime.api.main:app --reload --port 8081

# Rodar livetiming worker (modo replay; reaproveita cache do pipeline)
$env:FASTF1_CACHE_DIR='C:\Claude\f1-data-pipeline\cache'
uv run python -m realtime.ingest.livetiming_worker --year 2024 --round 1 --session R --speed 30

# Rodar testes
uv run pytest

# Verificar conexão com Postgres
uv run python -c "from realtime.db import engine; from sqlalchemy import text; print(engine.connect().execute(text('select count(*) from marts.tyre_degradation')).scalar())"
```

---

## Status de Implementação

### Fase 0 — Setup ✅ Concluída
Estrutura inicial, docker-compose, pyproject (uv), migrations em disco.

### Fase 1 — Preditor pré-evento ✅ Concluída
`GET /next-event` retornando 200 com chart Plotly de degradação ±1σ por composto.
Módulos:
- `config.py`, `db.py`, `ingest/schedule.py`
- `predict/allocation.py`, `predict/degradation.py`, `predict/weather.py`, `predict/model.py`
- `api/main.py` (lifespan aplica migrations idempotente), `api/routes/next_event.py`
- Template `next_event.html` + `static/style.css` (dark theme)

**Dependência crítica:** `staging.pirelli_compound_allocations` precisa existir (criada por `dbt seed` no pipeline). Se não existir, `predict/allocation.py` retorna `{}` e a previsão roda com `compound_name = NULL` no template (mostra `—`).

### Fase 2 — Ingestão live ✅ MVP em main (PR #1 mergeada)
Worker em modo replay, persistência em `live.lap`, pub/sub Redis e WebSocket prontos. Validado end-to-end com Bahrein 2024 R1 (1127 laps, 20 drivers).

Módulos implementados:
- `ingest/livetiming_worker.py` — `run_replay()` carrega sessão FastF1, itera laps cronologicamente (com sleep proporcional ao gap real ÷ `speed`), faz INSERT idempotente em `live.lap` e publica JSON em `lap:<session_id>` no Redis. CLI via `python -m realtime.ingest.livetiming_worker`.
- `api/routes/live.py` — `GET /live/{session_id}` renderiza template; `WS /ws/live?session_id=...` faz subscribe no canal Redis e push pro browser.
- `api/templates/live.html` — JS conecta no WS e prepende cada lap ao feed.
- `docker-compose.yml` — porta 6379 do Redis exposta no host pra worker/API rodarem fora do compose em dev.

**Limitações deliberadas (NÃO são bugs):**
1. `live.lap.received_at = now()` no replay, não o wall-clock original da sessão histórica.
2. WS detecta disconnect só na próxima `send_text` (cliente uni-direcional, sem heartbeat).

Documentadas no docstring dos respectivos módulos.

### Fase 2.1 — Live real via undercut-f1 sidecar 🔲 Não iniciada
`ingest/undercut_connector.py::is_available()` implementado; `get_laps()` ainda stub. Depende de subir o sidecar .NET no compose e adicionar modo `--live` ao worker. Necessário quando rolar corrida real (FastF1 SignalRClient só grava raw stream, não permite parse em tempo real).

### Fase 3 — Comparação live × predito ✅ MVP em PR (#2)
`GET /compare` (picker) + `GET /compare/{session_id}` (KPIs + scatter por composto com banda ±1σ + tabela agregada). Validado end-to-end com Bahrein 2024 R1 (1127 laps → 1127 residuals).

Módulos implementados:
- `compare/residuals.py` — `compute_and_save(session_id, forecast_id=None, *, force=False)`. JOIN único `live.lap × predictions.compound_curve`, persiste em `comparisons.lap_residual` via `INSERT … SELECT … ON CONFLICT DO NOTHING`. Idempotente pela PK (4 colunas incluindo `forecast_id`); suporta growing session (worker ainda escrevendo) e `force=True` para limpar e recomputar. `_resolve_forecast_id` busca o forecast mais recente via `get_latest_forecast(year, round_number)`.
- `api/routes/compare.py` — `GET /compare` picker + `GET /compare/{session_id}` em **sync `def`** (Starlette roda em threadpool, não bloqueia o event loop dos WS feeds da Fase 2). Status codes distintos: `ValueError "Session not found"` → 404, `ValueError "No forecast..."` → 424, `SQLAlchemyError` → 503. `?refresh=true` força DELETE+INSERT; `?driver=ABC` filtra só o scatter (KPIs/tabela ficam globais), com aviso explícito quando o filtro casa zero laps.
- `api/templates/compare.html` + `compare_index.html` — dark theme, Pirelli colors (SOFT vermelho / MEDIUM amarelo / HARD branco), banda ±1σ sombreada, linha zero, tooltip com `σ:` em segundos (ou `—` quando NULL na curva).
- `migrations/004_lap_residual_stddev.sql` — adiciona `stddev_s NUMERIC` ao lado de cada residual, evitando re-join com `compound_curve` em runtime.
- `migrations/005_lap_residual_pk_forecast.sql` — PK passa a incluir `forecast_id`. **Crítico**: sem isso, `ON CONFLICT DO NOTHING` dropava silenciosamente as linhas do segundo forecast quando `/next-event` rodava de novo (ex: clima mudou).

Tests: 9 unit/integration em `tests/test_compare_residuals.py` cobrindo filters de laps inválidas, idempotência, força recompute com delete externo, growing session com worker mid-flight, resolve forecast por (year,round), `ValueError` para session/forecast ausente.

**A polir junto com Claude Design:** o visual atual segue o `style.css` do dark theme da Fase 1; uma passada com o `DESIGN.md` do `f1-data-pipeline` está prevista pós-merge.

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
