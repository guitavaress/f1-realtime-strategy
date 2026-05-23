"""Fetch weather forecast from Open-Meteo and derive track temperature.

Open-Meteo is free and keyless. Track temp is derived from air temp via
a per-circuit heuristic (typical surface delta based on sun exposure and asphalt type).
"""
from __future__ import annotations

import httpx

from realtime.config import OPEN_METEO_URL

# Approximate circuit coordinates keyed by circuit_key (= event_name in marts)
CIRCUIT_COORDS: dict[str, tuple[float, float]] = {
    "Bahrain Grand Prix":           (26.032,   50.511),
    "Saudi Arabian Grand Prix":     (21.632,   39.104),
    "Australian Grand Prix":        (-37.849, 144.968),
    "Japanese Grand Prix":          (34.844,  136.541),
    "Chinese Grand Prix":           (31.338,  121.220),
    "Miami Grand Prix":             (25.958,  -80.239),
    "Emilia Romagna Grand Prix":    (44.341,   11.714),
    "Monaco Grand Prix":            (43.735,    7.421),
    "Canadian Grand Prix":          (45.505,  -73.526),
    "Spanish Grand Prix":           (41.570,    2.261),
    "Austrian Grand Prix":          (47.220,   14.765),
    "British Grand Prix":           (52.073,   -1.017),
    "Hungarian Grand Prix":         (47.583,   19.251),
    "Belgian Grand Prix":           (50.437,    5.971),
    "Dutch Grand Prix":             (52.389,    4.541),
    "Italian Grand Prix":           (45.620,    9.289),
    "Azerbaijan Grand Prix":        (40.373,   49.853),
    "Singapore Grand Prix":         (1.291,   103.864),
    "United States Grand Prix":     (30.133,  -97.641),
    "Mexico City Grand Prix":       (19.404,  -99.091),
    "São Paulo Grand Prix":         (-23.701, -46.697),
    "Las Vegas Grand Prix":         (36.113, -115.173),
    "Qatar Grand Prix":             (25.490,   51.454),
    "Abu Dhabi Grand Prix":         (24.467,   54.603),
}

# Circuits where race starts at night or late afternoon (solar delta is lower)
_NIGHT_CIRCUITS = {
    "Bahrain Grand Prix",
    "Saudi Arabian Grand Prix",
    "Singapore Grand Prix",
    "Abu Dhabi Grand Prix",
    "Qatar Grand Prix",
    "Las Vegas Grand Prix",
}

# Per-circuit solar delta: track_temp ≈ air_temp + delta
# Based on typical asphalt characteristics; night races get lower delta
_SOLAR_DELTA: dict[str, float] = {
    "Bahrain Grand Prix":        6.0,
    "Saudi Arabian Grand Prix":  5.0,
    "Australian Grand Prix":     8.0,
    "Japanese Grand Prix":       7.0,
    "Chinese Grand Prix":        7.0,
    "Miami Grand Prix":         11.0,
    "Emilia Romagna Grand Prix": 9.0,
    "Monaco Grand Prix":         8.0,
    "Canadian Grand Prix":       9.0,
    "Spanish Grand Prix":       12.0,
    "Austrian Grand Prix":       9.0,
    "British Grand Prix":        7.0,
    "Hungarian Grand Prix":     12.0,
    "Belgian Grand Prix":        7.0,
    "Dutch Grand Prix":          8.0,
    "Italian Grand Prix":       10.0,
    "Azerbaijan Grand Prix":     9.0,
    "Singapore Grand Prix":      5.0,
    "United States Grand Prix": 12.0,
    "Mexico City Grand Prix":   11.0,
    "São Paulo Grand Prix":     10.0,
    "Las Vegas Grand Prix":      3.0,
    "Qatar Grand Prix":          5.0,
    "Abu Dhabi Grand Prix":      6.0,
}
_DEFAULT_SOLAR_DELTA = 8.0


def estimate_track_temp(air_temp_c: float, circuit_key: str) -> float:
    """Heuristic: track temp ≈ air temp + solar delta per circuit."""
    delta = _SOLAR_DELTA.get(circuit_key, _DEFAULT_SOLAR_DELTA)
    return round(air_temp_c + delta, 1)


def fetch_forecast(circuit_key: str, race_date: str) -> dict:
    """Fetch weather forecast from Open-Meteo for the circuit on race_date.

    Args:
        circuit_key: Must be a key in CIRCUIT_COORDS (= event_name from marts).
        race_date: ISO date string 'YYYY-MM-DD' (local race day).

    Returns:
        Dict with keys:
            air_temp_c (float): forecast max air temperature.
            rainfall_prob (float): precipitation probability 0..1.
            track_temp_c (float): derived track temperature.

    Raises:
        ValueError: if circuit_key is not in CIRCUIT_COORDS.
        httpx.HTTPError: on network failure.
    """
    if circuit_key not in CIRCUIT_COORDS:
        raise ValueError(
            f"Unknown circuit_key '{circuit_key}'. "
            f"Add coordinates to predict.weather.CIRCUIT_COORDS."
        )
    lat, lon = CIRCUIT_COORDS[circuit_key]

    resp = httpx.get(
        OPEN_METEO_URL,
        params={
            "latitude":   lat,
            "longitude":  lon,
            "daily":      "temperature_2m_max,precipitation_probability_max",
            "timezone":   "auto",
            "start_date": race_date,
            "end_date":   race_date,
        },
        timeout=10.0,
    )
    resp.raise_for_status()
    data = resp.json()

    daily = data.get("daily", {})
    temps = daily.get("temperature_2m_max", [None])
    precip = daily.get("precipitation_probability_max", [0])

    air_temp_c = float(temps[0]) if temps[0] is not None else 25.0
    rainfall_prob = float(precip[0] or 0) / 100.0  # API returns 0-100 integer

    return {
        "air_temp_c":    air_temp_c,
        "rainfall_prob": rainfall_prob,
        "track_temp_c":  estimate_track_temp(air_temp_c, circuit_key),
    }
