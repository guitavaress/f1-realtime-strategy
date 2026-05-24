"""Tests for realtime.compare.residuals.

Integration tests against a real Postgres (live + predictions + comparisons schemas).
Uses tiny in-memory fixtures with a unique (year, round_number, session_id, forecast_id)
per test to avoid cross-test contamination.
"""
import uuid

import pytest
from sqlalchemy import text

from realtime.compare.residuals import _resolve_forecast_id, compute_and_save
from realtime.db import engine


@pytest.fixture
def seeded():
    """Seed a session+laps+forecast+curve; yield ids; cleanup at teardown."""
    session_id = str(uuid.uuid4())
    forecast_id = str(uuid.uuid4())
    year = 1999
    round_number = 99

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO live.session (session_id, year, round_number, session_type) "
                "VALUES (:sid, :y, :r, 'R')"
            ),
            {"sid": session_id, "y": year, "r": round_number},
        )

        # 5 laps:
        #   L1 SOFT  /life=1   → COMPARABLE
        #   L2 SOFT  /life=99  → DROP (out of 1..50)
        #   L3 MEDIUM/life=2   → COMPARABLE
        #   L4 NULL  /life=1   → DROP (compound NULL)
        #   L5 WET   /life=1   → DROP (no curve for WET)
        for d, n, t, c, life, stint in [
            ("VER", 1, 95.5, "SOFT",   1,  1),
            ("VER", 2, 95.8, "SOFT",   99, 1),
            ("VER", 3, 96.3, "MEDIUM", 2,  2),
            ("VER", 4, 96.4, None,     1,  3),
            ("VER", 5, 97.0, "WET",    1,  4),
        ]:
            conn.execute(
                text(
                    "INSERT INTO live.lap "
                    "(session_id, driver, lap_number, laptime_s, compound, tyre_life, stint) "
                    "VALUES (:sid, :d, :n, :t, :c, :life, :stint)"
                ),
                {"sid": session_id, "d": d, "n": n, "t": t, "c": c, "life": life, "stint": stint},
            )

        conn.execute(
            text(
                "INSERT INTO predictions.race_forecast "
                "(forecast_id, year, round_number, event_name, "
                " forecast_track_temp_c, forecast_rainfall_prob) "
                "VALUES (:fid, :y, :r, :name, 30, 0.05)"
            ),
            {"fid": forecast_id, "y": year, "r": round_number, "name": "Test GP"},
        )

        for compound, base in [("SOFT", 90.0), ("MEDIUM", 92.0), ("HARD", 94.0)]:
            for n in range(1, 6):
                conn.execute(
                    text(
                        "INSERT INTO predictions.compound_curve "
                        "(forecast_id, compound, tyre_life, predicted_laptime_s, "
                        " predicted_deg_per_lap_s, stddev_s) "
                        "VALUES (:fid, :c, :n, :lt, 0.05, 0.5)"
                    ),
                    {"fid": forecast_id, "c": compound, "n": n, "lt": base + (n - 1) * 0.05},
                )

    yield {
        "session_id":   session_id,
        "forecast_id":  forecast_id,
        "year":         year,
        "round_number": round_number,
    }

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM comparisons.lap_residual WHERE session_id = :sid"), {"sid": session_id})
        conn.execute(text("DELETE FROM predictions.compound_curve WHERE forecast_id = :fid"), {"fid": forecast_id})
        conn.execute(text("DELETE FROM predictions.race_forecast WHERE forecast_id = :fid"), {"fid": forecast_id})
        conn.execute(text("DELETE FROM live.lap WHERE session_id = :sid"), {"sid": session_id})
        conn.execute(text("DELETE FROM live.session WHERE session_id = :sid"), {"sid": session_id})


def test_compute_and_save_filters_invalid_laps(seeded):
    df = compute_and_save(seeded["session_id"], seeded["forecast_id"])
    assert len(df) == 2, "Only the 2 valid laps (SOFT/1 + MEDIUM/2) should remain"
    assert set(df["compound"]) == {"SOFT", "MEDIUM"}
    assert set(df["lap_number"]) == {1, 3}


def test_compute_and_save_idempotent(seeded):
    df1 = compute_and_save(seeded["session_id"], seeded["forecast_id"])
    df2 = compute_and_save(seeded["session_id"], seeded["forecast_id"])
    assert len(df1) == len(df2) == 2


def test_compute_and_save_force_recomputes(seeded):
    """force=True must DELETE existing rows before re-inserting.

    We delete one row externally between the two calls; only force=True can
    restore it, because the default branch relies on ON CONFLICT DO NOTHING
    and would NOT re-insert the missing row if a stale predicted value were
    present — here we test the stronger guarantee that DELETE actually fires.
    """
    sid = seeded["session_id"]
    fid = seeded["forecast_id"]

    compute_and_save(sid, fid)

    # Drop one residual row to simulate stale data the user wants recomputed
    with engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM comparisons.lap_residual "
                "WHERE session_id = :sid AND lap_number = 1"
            ),
            {"sid": sid},
        )
        remaining = conn.execute(
            text(
                "SELECT COUNT(*) FROM comparisons.lap_residual WHERE session_id = :sid"
            ),
            {"sid": sid},
        ).scalar()
    assert remaining == 1, "DELETE setup must have left exactly 1 row"

    df_force = compute_and_save(sid, fid, force=True)
    assert len(df_force) == 2, "force=True should DELETE+re-INSERT both valid laps"


def test_compute_and_save_growing_session_picks_up_new_laps(seeded):
    """Without force=True, a second call must pick up newly-arrived live.lap rows.

    Reproduces the live-worker scenario: the user opens /compare before the
    worker finishes replaying. The page must reflect new laps on reload, not
    cache the first snapshot.
    """
    sid = seeded["session_id"]
    fid = seeded["forecast_id"]

    df1 = compute_and_save(sid, fid)
    assert len(df1) == 2

    # Worker writes a brand-new comparable lap (HARD/life=3) after the first GET.
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO live.lap "
                "(session_id, driver, lap_number, laptime_s, compound, tyre_life, stint) "
                "VALUES (:sid, 'VER', 6, 98.1, 'HARD', 3, 5)"
            ),
            {"sid": sid},
        )

    df2 = compute_and_save(sid, fid)
    assert len(df2) == 3, "Second call must INSERT the newly-arrived lap"
    assert (df2["lap_number"] == 6).any()


def test_residual_value_matches_actual_minus_predicted(seeded):
    df = compute_and_save(seeded["session_id"], seeded["forecast_id"])
    # SOFT/L1: actual=95.5, predicted=90.0 → residual=+5.5
    soft = df[df["compound"] == "SOFT"].iloc[0]
    assert abs(float(soft["actual_laptime_s"]) - 95.5) < 1e-6
    assert abs(float(soft["predicted_laptime_s"]) - 90.0) < 1e-6
    assert abs(float(soft["residual_s"]) - 5.5) < 1e-6
    assert abs(float(soft["stddev_s"]) - 0.5) < 1e-6


def test_resolve_forecast_id_uses_session_lookup(seeded):
    fid = _resolve_forecast_id(seeded["session_id"])
    assert fid == seeded["forecast_id"]


def test_resolve_forecast_id_raises_for_unknown_session():
    with pytest.raises(ValueError, match="Session not found"):
        _resolve_forecast_id(str(uuid.uuid4()))


def test_compute_and_save_resolves_forecast_when_none(seeded):
    df = compute_and_save(seeded["session_id"], forecast_id=None)
    assert len(df) == 2


def test_resolve_forecast_id_raises_when_no_forecast():
    """Session exists but no forecast for its (year, round_number)."""
    session_id = str(uuid.uuid4())
    year = 1998
    round_number = 88
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO live.session (session_id, year, round_number, session_type) "
                "VALUES (:sid, :y, :r, 'R')"
            ),
            {"sid": session_id, "y": year, "r": round_number},
        )
    try:
        with pytest.raises(ValueError, match="No forecast"):
            _resolve_forecast_id(session_id)
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM live.session WHERE session_id = :sid"), {"sid": session_id})
