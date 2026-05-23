from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from realtime.db import engine
from realtime.api.routes import next_event, live, strategy, compare

templates = Jinja2Templates(directory="realtime/api/templates")

_MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "migrations"


def _run_migrations() -> None:
    """Apply all *.sql migrations idempotently on startup.

    Migrations use CREATE IF NOT EXISTS so they are safe to re-run.
    """
    for sql_file in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        raw = sql_file.read_text(encoding="utf-8")
        # Strip single-line comments before splitting by ';'
        stripped = "\n".join(
            line for line in raw.splitlines() if not line.strip().startswith("--")
        )
        statements = [s.strip() for s in stripped.split(";") if s.strip()]
        with engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Apply migrations (idempotent — safe every restart)
    try:
        _run_migrations()
    except Exception as exc:
        # Log but don't crash: DB may not be ready yet in dev
        import traceback
        traceback.print_exc()
        print(f"[startup] Migration warning: {exc}")

    yield
    # shutdown: nothing to clean up in Phase 1


app = FastAPI(title="F1 Realtime Strategy", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="realtime/api/static"), name="static")

app.include_router(next_event.router)
app.include_router(live.router)
app.include_router(strategy.router)
app.include_router(compare.router)
