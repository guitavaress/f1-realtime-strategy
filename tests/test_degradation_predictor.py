"""Tests for realtime.predict.degradation and realtime.predict.model.

Requires fixtures/tyre_weather_profile.sql and fixtures/circuit_tyre_profile.sql
loaded into a local Postgres test DB.
"""
import pytest


@pytest.mark.skip(reason="Fase 1 — not yet implemented")
def test_get_weather_profile_returns_dataframe():
    from realtime.predict.degradation import get_weather_profile
    df = get_weather_profile("British Grand Prix", "25-30")
    assert not df.empty
    assert "compound" in df.columns


@pytest.mark.skip(reason="Fase 1 — not yet implemented")
def test_weather_profile_fallback_to_circuit_profile():
    from realtime.predict.degradation import get_circuit_profile
    df = get_circuit_profile("British Grand Prix")
    assert not df.empty
