"""Main prediction model: combines allocation + weather + degradation into compound curves.

Algorithm for each compound:
    1. Get deg_per_lap_s from tyre_weather_profile (temp-conditioned) or circuit_tyre_profile.
    2. Get avg_pace_s and avg_stint_length from tyre_degradation (last 3 years).
    3. Anchor: pace_at_lap1 = avg_pace_s - deg * (avg_stint_length / 2 - 1)
       so the curve passes through the historical average midpoint.
    4. Curve: laptime(n) = pace_at_lap1 + deg * (n - 1)  for n in 1..MAX_TYRE_LIFE
    5. stddev_s = inter-year stddev of avg_pace_s (captures year-to-year variance).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy import text

from realtime.db import engine, read_df
from realtime.predict.allocation import get_allocation
from realtime.predict.degradation import (
    _temp_bucket,
    get_baseline_pace,
    get_circuit_profile,
    get_weather_profile,
)
from realtime.predict.weather import fetch_forecast

MAX_TYRE_LIFE = 50
_COMPOUNDS = ("SOFT", "MEDIUM", "HARD")


def _build_curve(
    compound: str,
    deg_per_lap_s: float,
    avg_pace_s: float,
    avg_stint_length: float,
    stddev_pace_s: float | None,
) -> list[dict]:
    """Build a list of {compound, tyre_life, predicted_laptime_s, ...} rows."""
    midpoint = max(avg_stint_length / 2, 1.0)
    pace_at_lap1 = avg_pace_s - deg_per_lap_s * (midpoint - 1)
    rows = []
    for n in range(1, MAX_TYRE_LIFE + 1):
        rows.append(
            {
                "compound":               compound,
                "tyre_life":              n,
                "predicted_laptime_s":    round(pace_at_lap1 + deg_per_lap_s * (n - 1), 4),
                "predicted_deg_per_lap_s": round(deg_per_lap_s, 5),
                "stddev_s":               round(stddev_pace_s, 3) if stddev_pace_s else None,
            }
        )
    return rows


def generate_forecast(
    year: int,
    round_number: int,
    event_name: str,
    race_date: str,
) -> str:
    """Run the full prediction pipeline for an upcoming event.

    Args:
        year: Season year.
        round_number: Round number in the season.
        event_name: Event name exactly as in marts (= circuit_key).
        race_date: ISO date string 'YYYY-MM-DD' for the race day.

    Returns:
        forecast_id (UUID string) of the newly inserted forecast.

    Raises:
        RuntimeError: if the DB write fails.
    """
    circuit_key = event_name  # in marts, circuit_key == event_name

    # 1. Pirelli allocation
    allocation = get_allocation(year, round_number)  # may be empty for unmapped rounds

    # 2. Weather forecast
    try:
        weather = fetch_forecast(circuit_key, race_date)
    except Exception:
        weather = {"air_temp_c": 25.0, "rainfall_prob": 0.0, "track_temp_c": 33.0}
    bucket = _temp_bucket(weather["track_temp_c"])

    # 3. Degradation + baseline pace per compound
    weather_profile = get_weather_profile(circuit_key, bucket)
    circuit_profile = get_circuit_profile(circuit_key)
    baseline = get_baseline_pace(circuit_key, year)

    def _deg(compound: str) -> float | None:
        """Best-effort deg_per_lap_s: weather-conditioned → circuit fallback → None."""
        if not weather_profile.empty:
            row = weather_profile[weather_profile["compound"] == compound]
            if not row.empty:
                return float(row.iloc[0]["avg_deg_per_lap_s"])
        if not circuit_profile.empty:
            row = circuit_profile[circuit_profile["compound"] == compound]
            if not row.empty:
                return float(row.iloc[0]["avg_deg_per_lap_s"])
        return None

    def _pace(compound: str) -> tuple[float | None, float, float | None]:
        """Return (avg_pace_s, avg_stint_length, stddev_pace_s) from baseline."""
        if not baseline.empty:
            row = baseline[baseline["compound"] == compound]
            if not row.empty:
                r = row.iloc[0]
                return (
                    float(r["avg_pace_s"]),
                    float(r["avg_stint_length"]),
                    float(r["stddev_pace_s"]) if pd.notna(r["stddev_pace_s"]) else None,
                )
        return None, 20.0, None

    # 4. Build compound curves
    curve_rows: list[dict] = []
    for compound in _COMPOUNDS:
        deg = _deg(compound)
        avg_pace_s, avg_stint_length, stddev = _pace(compound)
        if deg is None or avg_pace_s is None:
            continue  # skip compounds with no historical data
        curve_rows.extend(_build_curve(compound, deg, avg_pace_s, avg_stint_length, stddev))

    # 5. Write to DB
    forecast_id = str(uuid.uuid4())
    now = datetime.now(tz=timezone.utc)

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO predictions.race_forecast
                    (forecast_id, year, round_number, event_name, generated_at,
                     forecast_track_temp_c, forecast_rainfall_prob,
                     pirelli_c_soft, pirelli_c_medium, pirelli_c_hard)
                VALUES
                    (:forecast_id, :year, :round_number, :event_name, :generated_at,
                     :track_temp, :rainfall_prob,
                     :c_soft, :c_medium, :c_hard)
                ON CONFLICT (year, round_number, generated_at) DO NOTHING
            """),
            {
                "forecast_id":   forecast_id,
                "year":          year,
                "round_number":  round_number,
                "event_name":    event_name,
                "generated_at":  now,
                "track_temp":    weather["track_temp_c"],
                "rainfall_prob": weather["rainfall_prob"],
                "c_soft":   allocation.get("SOFT"),
                "c_medium": allocation.get("MEDIUM"),
                "c_hard":   allocation.get("HARD"),
            },
        )
        if curve_rows:
            conn.execute(
                text("""
                    INSERT INTO predictions.compound_curve
                        (forecast_id, compound, tyre_life,
                         predicted_laptime_s, predicted_deg_per_lap_s, stddev_s)
                    VALUES
                        (:forecast_id, :compound, :tyre_life,
                         :predicted_laptime_s, :predicted_deg_per_lap_s, :stddev_s)
                    ON CONFLICT DO NOTHING
                """),
                [{"forecast_id": forecast_id, **row} for row in curve_rows],
            )

    return forecast_id


def get_latest_forecast(year: int, round_number: int) -> dict[str, Any] | None:
    """Return the most recent forecast for a round, or None if none exists.

    Returns:
        Dict with keys: forecast_id, track_temp_c, rainfall_prob,
        allocation (dict), curves (DataFrame).
    """
    df = read_df(
        """
        SELECT forecast_id, forecast_track_temp_c, forecast_rainfall_prob,
               pirelli_c_soft, pirelli_c_medium, pirelli_c_hard, generated_at
        FROM predictions.race_forecast
        WHERE year = :year AND round_number = :round_number
        ORDER BY generated_at DESC
        LIMIT 1
        """,
        year=year,
        round_number=round_number,
    )
    if df.empty:
        return None

    row = df.iloc[0]
    fid = row["forecast_id"]

    curves = read_df(
        """
        SELECT compound, tyre_life, predicted_laptime_s, predicted_deg_per_lap_s, stddev_s
        FROM predictions.compound_curve
        WHERE forecast_id = :fid
        ORDER BY compound, tyre_life
        """,
        fid=fid,
    )
    return {
        "forecast_id":   fid,
        "track_temp_c":  float(row["forecast_track_temp_c"] or 0),
        "rainfall_prob": float(row["forecast_rainfall_prob"] or 0),
        "allocation": {
            "SOFT":   row["pirelli_c_soft"],
            "MEDIUM": row["pirelli_c_medium"],
            "HARD":   row["pirelli_c_hard"],
        },
        "curves": curves,
        "generated_at": row["generated_at"],
    }
