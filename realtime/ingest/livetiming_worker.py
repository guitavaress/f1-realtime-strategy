"""Live timing worker: subscribes to fastf1.livetiming, parses laps, publishes to Redis.

Channel convention: lap:<session_id>  (JSON payload per lap)
"""
from __future__ import annotations


def run(session_id: str, year: int, round_number: int, session_type: str = "R") -> None:
    """Start the live timing listener for a session.

    Publishes each completed lap as JSON to Redis channel ``lap:<session_id>``.
    Blocks until the session ends or the process is interrupted.
    """
    raise NotImplementedError
