"""Connector for the undercut-f1 sidecar (https://github.com/JustAman62/undercut-f1).

undercut-f1 is a .NET/C# service that connects to F1's SignalR stream and exposes
data via a Swagger-documented REST API. It is more reliable than FastF1 livetiming
for sustained live sessions (C# SignalR client is more stable than the Python one).

Usage (Fase 2+):
    - Run `docker compose up undercut` to start the sidecar.
    - livetiming_worker.py falls back to this connector when FastF1 livetiming drops.

Connection: HTTP polling or WebSocket to UNDERCUT_URL (default http://undercut:5000).
"""
from __future__ import annotations

from typing import AsyncIterator

import httpx

from realtime.config import UNDERCUT_URL


async def is_available() -> bool:
    """Return True if the undercut-f1 sidecar is reachable."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{UNDERCUT_URL}/health")
            return r.status_code == 200
    except httpx.TransportError:
        return False


async def get_laps(session_id: str) -> AsyncIterator[dict]:
    """Async generator yielding lap dicts from the undercut-f1 REST stream.

    Each dict has keys: driver, lap_number, laptime_s, compound, tyre_life, stint.

    Args:
        session_id: UUID of the live.session row (used for correlation).

    Yields:
        One dict per completed lap as reported by undercut-f1.
    """
    raise NotImplementedError
