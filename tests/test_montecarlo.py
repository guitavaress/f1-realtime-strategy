"""Tests for realtime.simulate.montecarlo and realtime.simulate.strategy."""
import pytest
from realtime.simulate.strategy import is_dry_legal, dry_legal_strategies


def test_is_dry_legal_two_compounds():
    assert is_dry_legal(["SOFT", "HARD"]) is True


def test_is_dry_legal_single_compound_fails():
    assert is_dry_legal(["SOFT"]) is False
    assert is_dry_legal(["MEDIUM", "MEDIUM"]) is False


def test_is_dry_legal_wet_compounds_not_counted():
    assert is_dry_legal(["INTERMEDIATE", "WET"]) is False


def test_is_dry_legal_mixed_wet_and_one_slick():
    assert is_dry_legal(["INTERMEDIATE", "SOFT"]) is False


def test_dry_legal_strategies_all_valid():
    for s in dry_legal_strategies():
        assert is_dry_legal(s["stints"]), f"Strategy '{s['name']}' failed Art. 30.5"


@pytest.mark.skip(reason="Fase 4 — not yet implemented")
def test_montecarlo_returns_distribution():
    from realtime.simulate.montecarlo import simulate
    result = simulate(
        strategy={"name": "1-stop S→H", "stints": ["SOFT", "HARD"]},
        forecast_id="00000000-0000-0000-0000-000000000000",
        circuit_key="British Grand Prix",
    )
    assert result["p10"] < result["p50"] < result["p90"]
