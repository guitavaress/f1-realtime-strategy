"""Routes for live session monitoring.

- GET  /live/{session_id}   — renders the live feed page (Jinja template).
- WS   /ws/live?session_id= — pushes laps published to Redis channel ``lap:<session_id>``.
"""
from __future__ import annotations

import asyncio

import redis.asyncio as aioredis
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from realtime.config import REDIS_URL

router = APIRouter()
templates = Jinja2Templates(directory="realtime/api/templates")


@router.get("/live/{session_id}", response_class=HTMLResponse)
async def live_page(request: Request, session_id: str):
    """Render the live feed page for an active session_id."""
    return templates.TemplateResponse(
        request,
        "live.html",
        {"session_id": session_id},
    )


@router.websocket("/ws/live")
async def ws_live(websocket: WebSocket, session_id: str):
    """Subscribe to ``lap:<session_id>`` on Redis and forward messages to the client.

    The connection stays open until the client disconnects or the session ends
    (we don't auto-close — the worker just stops publishing).
    """
    await websocket.accept()

    redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    pubsub = redis_client.pubsub()
    channel = f"lap:{session_id}"
    await pubsub.subscribe(channel)

    try:
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg is not None and msg.get("type") == "message":
                await websocket.send_text(msg["data"])
            else:
                # No message: yield control so disconnects are detected promptly
                await asyncio.sleep(0)
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        await redis_client.close()
