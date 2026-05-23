"""GET /compare/{session_id} — residuals page for a completed session."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="realtime/api/templates")


@router.get("/compare/{session_id}", response_class=HTMLResponse)
async def compare(request: Request, session_id: str):
    raise NotImplementedError
