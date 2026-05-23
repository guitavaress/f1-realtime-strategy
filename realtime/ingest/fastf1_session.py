"""Load a completed FastF1 session and return per-lap data.

Adapted from f1-data-pipeline/dags/load_fastf1.py — read-only usage here,
no writes to raw.fastf1_laps.
"""
from __future__ import annotations

import fastf1
import pandas as pd
from realtime.config import FASTF1_CACHE_DIR

fastf1.Cache.enable_cache(FASTF1_CACHE_DIR)

LAP_COLUMNS = [
    "Driver", "LapNumber", "LapTime", "Compound", "TyreLife",
    "Stint", "FreshTyre", "TrackStatus", "AirTemp", "TrackTemp",
    "Humidity", "Rainfall",
]


def load_session(year: int, round_number: int, session_type: str = "R") -> pd.DataFrame:
    """Return a DataFrame of laps for the given session.

    Args:
        year: Season year.
        round_number: Round number within the season.
        session_type: 'R' (Race), 'Q' (Qualifying), 'S' (Sprint).

    Returns:
        DataFrame with columns from LAP_COLUMNS, laptime in seconds (float).
    """
    raise NotImplementedError
