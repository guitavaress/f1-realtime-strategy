"""Pit stop time loss estimates by circuit.

Calibrated from historical data in marts.tyre_degradation (lap delta around pit laps).
Values below are initial estimates — will be refined in Fase 4.
"""
from __future__ import annotations

# Pit loss in seconds (stationary time + delta vs flying lap) by circuit_key
PIT_LOSS: dict[str, float] = {
    "Monaco Grand Prix": 24.0,
    "Singapore Grand Prix": 22.5,
    "Hungarian Grand Prix": 21.0,
    "Spanish Grand Prix": 20.0,
    "British Grand Prix": 20.5,
    "Italian Grand Prix": 19.0,
    "Belgian Grand Prix": 19.5,
    "Australian Grand Prix": 21.5,
    "Bahrain Grand Prix": 20.0,
    "Japanese Grand Prix": 20.5,
}
DEFAULT_PIT_LOSS = 20.5


def get_pit_loss(circuit_key: str) -> float:
    return PIT_LOSS.get(circuit_key, DEFAULT_PIT_LOSS)
