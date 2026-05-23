"""Query marts.tyre_weather_profile and marts.circuit_tyre_profile for degradation data.

Primary input for the lap-time predictor.

Temp buckets (defined in tyre_weather_profile.sql):
    '<20', '20-25', '25-30', '30-35', '35-40', '>40'
"""
from __future__ import annotations

import pandas as pd

from realtime.db import read_df


def _temp_bucket(track_temp_c: float) -> str:
    """Convert a float track temperature to the bucket label used in the mart."""
    if track_temp_c < 20:
        return "<20"
    elif track_temp_c < 25:
        return "20-25"
    elif track_temp_c < 30:
        return "25-30"
    elif track_temp_c < 35:
        return "30-35"
    elif track_temp_c < 40:
        return "35-40"
    return ">40"


def get_weather_profile(circuit_key: str, temp_bucket: str) -> pd.DataFrame:
    """Return degradation data from marts.tyre_weather_profile for a circuit + temp bucket.

    Aggregates across all available years so the result uses full historical depth.
    Only returns compounds with enough stints (stints_in_bucket >= 3 across years).

    Returns:
        DataFrame with columns: compound, avg_deg_per_lap_s, stddev_deg_s,
        total_stints, avg_track_temp_c.
        Empty if no data for this circuit / bucket combination.
    """
    return read_df(
        """
        SELECT
            compound,
            SUM(stints_in_bucket)                           AS total_stints,
            AVG(avg_deg_per_lap_s)                          AS avg_deg_per_lap_s,
            STDDEV(avg_deg_per_lap_s)                       AS stddev_deg_s,
            AVG(avg_track_temp_c)                           AS avg_track_temp_c
        FROM marts.tyre_weather_profile
        WHERE circuit_key  = :circuit_key
          AND temp_bucket  = :temp_bucket
          AND compound IN ('SOFT', 'MEDIUM', 'HARD')
        GROUP BY compound
        HAVING SUM(stints_in_bucket) >= 3
        ORDER BY compound
        """,
        circuit_key=circuit_key,
        temp_bucket=temp_bucket,
    )


def get_circuit_profile(circuit_key: str) -> pd.DataFrame:
    """Fallback: degradation from marts.circuit_tyre_profile (no temp conditioning).

    Used when get_weather_profile() returns empty (sparse data for that temp bucket).

    Returns:
        DataFrame with columns: compound, avg_deg_per_lap_s (= avg_deg_s from mart),
        avg_stint_laps.
    """
    df = read_df(
        """
        SELECT
            compound,
            avg_deg_s   AS avg_deg_per_lap_s,
            avg_stint_laps
        FROM marts.circuit_tyre_profile
        WHERE circuit_key = :circuit_key
          AND compound IN ('SOFT', 'MEDIUM', 'HARD')
        ORDER BY compound
        """,
        circuit_key=circuit_key,
    )
    return df


def get_baseline_pace(circuit_key: str, year: int, n_years: int = 3) -> pd.DataFrame:
    """Return baseline lap pace and stint stats from marts.tyre_degradation.

    Looks back n_years from the given year to get a recent-era average.
    The avg_pace_s is the anchor point for constructing the predicted lap time curve.

    Returns:
        DataFrame with columns: compound, avg_pace_s, avg_deg_per_lap_s,
        avg_stint_length, stddev_pace_s (inter-year variation).
    """
    return read_df(
        """
        SELECT
            compound,
            AVG(avg_pace_s)           AS avg_pace_s,
            AVG(avg_deg_per_lap_s)    AS avg_deg_per_lap_s,
            AVG(avg_stint_length)     AS avg_stint_length,
            STDDEV(avg_pace_s)        AS stddev_pace_s
        FROM marts.tyre_degradation
        WHERE circuit_key = :circuit_key
          AND year BETWEEN :start_year AND :end_year
          AND compound IN ('SOFT', 'MEDIUM', 'HARD')
          AND avg_pace_s IS NOT NULL
        GROUP BY compound
        ORDER BY compound
        """,
        circuit_key=circuit_key,
        start_year=year - n_years,
        end_year=year,
    )
