"""Query the Pirelli compound allocation for a given (year, round_number).

Primary source: staging.pirelli_compound_allocations (dbt seed from f1-data-pipeline).
The table must exist — run `dbt seed` in the pipeline before using this module.
"""
from __future__ import annotations

from realtime.db import read_df


def get_allocation(year: int, round_number: int) -> dict[str, str]:
    """Return Pirelli compound allocation for a GP.

    Returns:
        Dict with keys 'SOFT', 'MEDIUM', 'HARD' mapped to compound names ('C1'..'C5').
        Empty dict if the round is not in the seed (e.g. 2021 or earlier, or future GPs
        not yet added to the CSV).
    """
    df = read_df(
        """
        SELECT c_soft, c_medium, c_hard
        FROM staging.pirelli_compound_allocations
        WHERE year = :year AND round_number = :round_number
        LIMIT 1
        """,
        year=year,
        round_number=round_number,
    )
    if df.empty:
        return {}
    row = df.iloc[0]
    return {
        "SOFT":   row["c_soft"],
        "MEDIUM": row["c_medium"],
        "HARD":   row["c_hard"],
    }
