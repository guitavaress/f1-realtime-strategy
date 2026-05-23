"""Canonical strategy definitions and FIA Art. 30.5 validation."""
from __future__ import annotations

# Canonical 1-stop and 2-stop strategies (compound sequences)
STRATEGIES: list[dict] = [
    {"name": "1-stop S→H",  "stints": ["SOFT", "HARD"]},
    {"name": "1-stop M→H",  "stints": ["MEDIUM", "HARD"]},
    {"name": "1-stop S→M",  "stints": ["SOFT", "MEDIUM"]},
    {"name": "2-stop S→M→H", "stints": ["SOFT", "MEDIUM", "HARD"]},
    {"name": "2-stop S→H→M", "stints": ["SOFT", "HARD", "MEDIUM"]},
    {"name": "2-stop M→S→H", "stints": ["MEDIUM", "SOFT", "HARD"]},
    # Wet-only (not filtered by is_dry_legal)
    {"name": "Full wet",    "stints": ["WET"]},
    {"name": "I→S",         "stints": ["INTERMEDIATE", "SOFT"]},
]

SLICK_COMPOUNDS = {"SOFT", "MEDIUM", "HARD"}


def is_dry_legal(compounds: list[str]) -> bool:
    """FIA Sporting Regulations Art. 30.5: dry race requires ≥2 distinct slick compounds."""
    slicks_used = {c for c in compounds if c in SLICK_COMPOUNDS}
    return len(slicks_used) >= 2


def dry_legal_strategies() -> list[dict]:
    """Return canonical strategies that comply with Art. 30.5 for a dry race."""
    return [s for s in STRATEGIES if is_dry_legal(s["stints"])]
