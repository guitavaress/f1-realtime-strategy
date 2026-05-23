"""Live timing worker: streams laps from a session into Redis + Postgres.

Two modes:

- ``replay``: load a historical session via FastF1, iterate laps in chronological
  order, sleep proportionally to the real gap between them divided by ``speed``.
  This is the default during development since FastF1's SignalR client only
  records raw stream to a file (parsing is post-session) — see the docstring of
  ``fastf1.livetiming.client.SignalRClient``.

- ``live`` (Fase 2.1): consume from the ``undercut-f1`` .NET sidecar when a real
  session is running. Currently delegates to ``undercut_connector.get_laps``
  which is still a stub.

Each completed lap is:
  1) inserted into ``live.lap``
  2) published as JSON to Redis channel ``lap:<session_id>``

CLI usage:
    uv run python -m realtime.ingest.livetiming_worker --year 2024 --round 22 --session R --speed 60
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Iterator

import fastf1
import pandas as pd
import redis
from sqlalchemy import text

from realtime.config import REDIS_URL
from realtime.db import engine
from realtime.ingest.schedule import FASTF1_CACHE_DIR  # noqa: F401 -- ensures fastf1 cache is configured


def _create_session_row(year: int, round_number: int, session_type: str) -> str:
    """Insert a row in ``live.session`` and return the new UUID as string."""
    session_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO live.session (session_id, year, round_number, session_type, started_at)
                VALUES (:sid, :y, :r, :st, :ts)
                """
            ),
            {
                "sid": session_id,
                "y": year,
                "r": round_number,
                "st": session_type,
                "ts": datetime.now(tz=timezone.utc),
            },
        )
    return session_id


def _persist_and_publish(
    redis_client: "redis.Redis",
    session_id: str,
    lap: dict,
) -> None:
    """Insert lap into ``live.lap`` (idempotent) and publish to Redis."""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO live.lap
                    (session_id, driver, lap_number, laptime_s, compound, tyre_life, stint)
                VALUES
                    (:sid, :driver, :lapn, :lt, :comp, :life, :stint)
                ON CONFLICT (session_id, driver, lap_number) DO NOTHING
                """
            ),
            {
                "sid":   session_id,
                "driver": lap["driver"],
                "lapn":  lap["lap_number"],
                "lt":    lap["laptime_s"],
                "comp":  lap["compound"],
                "life":  lap["tyre_life"],
                "stint": lap["stint"],
            },
        )

    payload = json.dumps({"session_id": session_id, **lap})
    redis_client.publish(f"lap:{session_id}", payload)


def _laps_chronological(session) -> Iterator[tuple[float, dict]]:
    """Yield (race_seconds_since_start, lap_dict) for each completed lap.

    ``race_seconds_since_start`` is taken from ``Time`` (the lap finish time
    measured from the session start). Laps with missing ``LapTime`` are skipped
    because they correspond to in/out laps the pipeline filters anyway.
    """
    laps: pd.DataFrame = session.laps.copy()
    laps = laps[laps["LapTime"].notna()]
    laps = laps.sort_values("Time")

    for _, row in laps.iterrows():
        finish_s = row["Time"].total_seconds() if pd.notna(row["Time"]) else None
        if finish_s is None:
            continue

        compound = row.get("Compound")
        if isinstance(compound, str):
            compound = compound.upper()
        else:
            compound = None

        yield finish_s, {
            "driver":      str(row["Driver"]),
            "lap_number":  int(row["LapNumber"]),
            "laptime_s":   round(row["LapTime"].total_seconds(), 3),
            "compound":    compound,
            "tyre_life":   int(row["TyreLife"]) if pd.notna(row.get("TyreLife")) else None,
            "stint":       int(row["Stint"]) if pd.notna(row.get("Stint")) else None,
        }


def run_replay(
    year: int,
    round_number: int,
    session_type: str = "R",
    speed: float = 60.0,
) -> str:
    """Replay a historical session as if it were live.

    Args:
        year: F1 season year.
        round_number: Event round number.
        session_type: 'R' (race), 'Q' (qualifying), 'S' (sprint), etc.
        speed: Real-time speed multiplier. 1.0 = real time, 60.0 = a 1.5h race
            collapses to ~1.5 min. Set to 0 to skip sleeping (burst replay).

    Returns:
        The session_id (UUID) of the created ``live.session`` row.
    """
    print(f"[worker] Loading session {year} R{round_number} {session_type}...", flush=True)
    session = fastf1.get_session(year, round_number, session_type)
    session.load(laps=True, telemetry=False, weather=False, messages=False)

    session_id = _create_session_row(year, round_number, session_type)
    print(f"[worker] Created live.session {session_id}", flush=True)

    redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

    laps = list(_laps_chronological(session))
    if not laps:
        print("[worker] No laps with LapTime found — nothing to replay.", flush=True)
        return session_id

    print(
        f"[worker] Replaying {len(laps)} laps at speed={speed}x "
        f"(session length ~{laps[-1][0] / 60:.1f} min real time)",
        flush=True,
    )

    prev_finish_s = laps[0][0]
    published = 0
    for finish_s, lap in laps:
        if speed > 0:
            sleep_s = max(0.0, (finish_s - prev_finish_s) / speed)
            if sleep_s > 0:
                time.sleep(sleep_s)
        prev_finish_s = finish_s

        _persist_and_publish(redis_client, session_id, lap)
        published += 1
        if published % 50 == 0:
            print(f"[worker] published {published}/{len(laps)} laps", flush=True)

    print(f"[worker] Done — {published} laps published to lap:{session_id}", flush=True)
    return session_id


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="F1 live timing worker (replay mode)")
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--round", dest="round_number", type=int, required=True)
    p.add_argument("--session", default="R", help="Session type: R, Q, S, FP1, FP2, FP3")
    p.add_argument("--speed", type=float, default=60.0, help="Replay speed multiplier (0 = burst)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    run_replay(args.year, args.round_number, args.session, args.speed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
