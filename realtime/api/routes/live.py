"""WebSocket /ws/live — pushes laps as they arrive from Redis."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws/live")
async def ws_live(websocket: WebSocket, session_id: str):
    await websocket.accept()
    try:
        raise NotImplementedError
    except WebSocketDisconnect:
        pass
