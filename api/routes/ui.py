"""UI routes — serve the HTML frontend and health check."""

from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from api.sessions import _sessions

router = APIRouter()

_ROOT = Path(__file__).parent.parent.parent
_STATIC = _ROOT / "static"
_DIST = _ROOT / "frontend" / "dist"


@router.get("/", response_class=HTMLResponse)
async def chat_ui():
    """Ưu tiên UI React (frontend/dist) nếu đã build; nếu chưa thì dùng UI vanilla."""
    react_index = _DIST / "index.html"
    if react_index.exists():
        return react_index.read_text(encoding="utf-8")
    return (_STATIC / "index.html").read_text(encoding="utf-8")


@router.get("/old", response_class=HTMLResponse)
async def old_ui():
    """UI vanilla cũ (fallback)."""
    return (_STATIC / "index.html").read_text(encoding="utf-8")


@router.get("/health")
async def health():
    return {"status": "ok", "sessions": len(_sessions)}
