"""Compute residuals between live laps and the pre-event prediction.

Joins ``live.lap`` × ``predictions.compound_curve`` and persists deltas in
``comparisons.lap_residual``. Idempotent via the 4-column PK on
(session_id, forecast_id, driver, lap_number) + ON CONFLICT DO NOTHING — each
call picks up newly-arrived laps without duplicating already-persisted ones,
which matters for growing sessions (worker still writing while UI refreshes).
``force=True`` additionally wipes existing rows for the pair before reinserting.

The JOIN naturally drops laps that cannot be compared:
  - ``laptime_s`` NULL (in/out laps already filtered by the worker, defensive)
  - ``compound`` NULL or ∉ {SOFT, MEDIUM, HARD} (no curve for INTERMEDIATE/WET)
  - ``tyre_life`` NULL or outside 1..MAX_TYRE_LIFE (50)
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from realtime.db import engine, read_df
from realtime.predict.model import get_latest_forecast


_SELECT_RESIDUALS = """
SELECT driver, lap_number, compound, tyre_life,
       actual_laptime_s, predicted_laptime_s, residual_s, stddev_s
FROM comparisons.lap_residual
WHERE session_id = :sid AND forecast_id = :fid
ORDER BY driver, lap_number
"""

_INSERT_RESIDUALS = """
INSERT INTO comparisons.lap_residual
    (session_id, forecast_id, driver, lap_number, compound, tyre_life,
     actual_laptime_s, predicted_laptime_s, stddev_s)
SELECT
    l.session_id, :fid, l.driver, l.lap_number, l.compound, l.tyre_life,
    l.laptime_s, c.predicted_laptime_s, c.stddev_s
FROM live.lap l
JOIN predictions.compound_curve c
  ON c.forecast_id = :fid
 AND c.compound    = l.compound
 AND c.tyre_life   = l.tyre_life
WHERE l.session_id   = :sid
  AND l.laptime_s    IS NOT NULL
  AND l.compound     IN ('SOFT','MEDIUM','HARD')
  AND l.tyre_life    BETWEEN 1 AND 50
ON CONFLICT (session_id, forecast_id, driver, lap_number) DO NOTHING
"""


def _resolve_forecast_id(session_id: str) -> str:
    """Find the latest forecast_id for the (year, round_number) of a session.

    Raises:
        ValueError: if the session is unknown or no forecast exists for its event.
    """
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT year, round_number FROM live.session WHERE session_id = :sid"),
            {"sid": session_id},
        ).first()
    if row is None:
        raise ValueError(f"Session not found: {session_id}")

    year, round_number = int(row[0]), int(row[1])
    forecast = get_latest_forecast(year, round_number)
    if forecast is None:
        raise ValueError(
            f"No forecast for year={year}, round={round_number}. "
            "Run /next-event for the matching event first."
        )
    return str(forecast["forecast_id"])


def compute_and_save(
    session_id: str,
    forecast_id: str | None = None,
    *,
    force: bool = False,
) -> pd.DataFrame:
    """Match live.lap rows against predictions.compound_curve and persist deltas.

    Always issues the INSERT — ON CONFLICT DO NOTHING (on the 4-column PK
    including ``forecast_id``, see migration 005) keeps it idempotent and lets
    growing sessions pick up new laps without an explicit refresh. ``force=True``
    additionally wipes existing rows for the pair before re-inserting, used by
    ``?refresh=true`` when the forecast was regenerated.

    Args:
        session_id: UUID of the ``live.session`` row to compare.
        forecast_id: UUID of the ``predictions.race_forecast`` to compare against.
            If None, resolved via the session's (year, round_number) using
            ``get_latest_forecast``.
        force: If True, DELETE existing rows for (session_id, forecast_id) before
            re-inserting.

    Returns:
        DataFrame ordered by (driver, lap_number) with columns:
        driver, lap_number, compound, tyre_life,
        actual_laptime_s, predicted_laptime_s, residual_s, stddev_s.

    Raises:
        ValueError: if session is unknown or no forecast exists.
    """
    if forecast_id is None:
        forecast_id = _resolve_forecast_id(session_id)

    with engine.begin() as conn:
        if force:
            conn.execute(
                text(
                    "DELETE FROM comparisons.lap_residual "
                    "WHERE session_id = :sid AND forecast_id = :fid"
                ),
                {"sid": session_id, "fid": forecast_id},
            )
        conn.execute(
            text(_INSERT_RESIDUALS),
            {"sid": session_id, "fid": forecast_id},
        )

    return read_df(_SELECT_RESIDUALS, sid=session_id, fid=forecast_id)
