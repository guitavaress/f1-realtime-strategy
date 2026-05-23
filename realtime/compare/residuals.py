"""Compute residuals between live laps and the pre-event prediction curve.

Writes results to comparisons.lap_residual for calibration tracking.
"""
from __future__ import annotations

import pandas as pd


def compute_and_save(session_id: str, forecast_id: str) -> pd.DataFrame:
    """Match live.lap rows against predictions.compound_curve and persist deltas.

    Args:
        session_id: UUID of the live.session row.
        forecast_id: UUID of the predictions.race_forecast to compare against.

    Returns:
        DataFrame of residuals (also written to comparisons.lap_residual).
    """
    raise NotImplementedError
