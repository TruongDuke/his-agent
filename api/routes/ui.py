"""UI routes — serve the HTML frontend and health check."""

from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from api.sessions import _sessions

router = APIRouter()

_STATIC = Path(__file__).parent.parent.parent / "static"


@router.get("/", response_class=HTMLResponse)
async def chat_ui():
    return (_STATIC / "index.html").read_text(encoding="utf-8")


@router.get("/health")
async def health():
    return {"status": "ok", "sessions": len(_sessions)}
