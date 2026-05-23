"""Utilities to determine the next F1 event."""
from __future__ import annotations

from pathlib import Path

import fastf1
import pandas as pd
from datetime import datetime, timezone

from realtime.config import FASTF1_CACHE_DIR

Path(FASTF1_CACHE_DIR).mkdir(parents=True, exist_ok=True)
fastf1.Cache.enable_cache(FASTF1_CACHE_DIR)


def next_event(year: int | None = None) -> pd.Series | None:
    """Return the next upcoming F1 event as a pandas Series, or None if season is over.

    Walks to the following year if the current calendar has no remaining events.
    Excludes pre-season testing entries.
    """
    if year is None:
        year = datetime.now(tz=timezone.utc).year

    def _first_future(y: int) -> pd.Series | None:
        schedule = fastf1.get_event_schedule(y, include_testing=False)
        now = datetime.now(tz=timezone.utc)
        future = schedule[pd.to_datetime(schedule["EventDate"], utc=True) > now]
        return future.iloc[0] if not future.empty else None

    event = _first_future(year)
    if event is None and year == datetime.now(tz=timezone.utc).year:
        event = _first_future(year + 1)
    return event
