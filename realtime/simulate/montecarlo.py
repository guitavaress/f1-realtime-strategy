"""Monte Carlo race simulator.

Runs N scenarios per strategy candidate, sampling degradation variance,
track temp drift, pit loss variance, and safety car probability.
"""
from __future__ import annotations

import numpy as np


# Default SC probability priors by circuit_key (calibrated from historical data)
SC_PRIORS: dict[str, float] = {
    "Monaco Grand Prix": 0.80,
    "Singapore Grand Prix": 0.75,
    "Azerbaijan Grand Prix": 0.70,
    "Saudi Arabian Grand Prix": 0.65,
    "Las Vegas Grand Prix": 0.60,
    "Australian Grand Prix": 0.55,
    "Bahrain Grand Prix": 0.30,
    "British Grand Prix": 0.35,
    "Italian Grand Prix": 0.30,
    "Spanish Grand Prix": 0.25,
}
DEFAULT_SC_PRIOR = 0.40


def simulate(
    strategy: dict,
    forecast_id: str,
    circuit_key: str,
    n_laps: int = 57,
    n_simulations: int = 10_000,
) -> dict:
    """Run Monte Carlo simulation for a single strategy.

    Args:
        strategy: Dict with 'name' and 'stints' (list of compound names).
        forecast_id: UUID of the predictions.race_forecast to pull curves from.
        circuit_key: Used for pit loss and SC prior lookup.
        n_laps: Total race laps.
        n_simulations: Number of Monte Carlo samples.

    Returns:
        Dict with keys: strategy_name, p10, p50, p90 (race time in seconds),
        sc_probability, simulations (array of N total race times).
    """
    raise NotImplementedError
