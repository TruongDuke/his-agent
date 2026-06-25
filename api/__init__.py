"""HIS Agent API — FastAPI application factory."""

import sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes import chat, scheduling, fhir, appointments, ui, auth, a2a

app = FastAPI(title="HIS Agent API", version="1.0.0")


@app.on_event("startup")
async def _warmup():
    """Pre-load sentence-transformer model so first user request is fast."""
    import asyncio
    sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _load_rag)


def _load_rag():
    try:
        from _rag_departments import retrieve_departments
        retrieve_departments("khám tổng quát", top_k=1)
        print("[startup] RAG model loaded ✓")
    except Exception as e:
        print(f"[startup] RAG warmup skipped: {e}")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(a2a.router)
app.include_router(scheduling.router)
app.include_router(fhir.router)
app.include_router(appointments.router)
app.mount("/static", StaticFiles(directory="static"), name="static")

# UI React (Vite build) — phục vụ assets nếu đã build (frontend/dist)
_DIST = Path(__file__).parent.parent / "frontend" / "dist"
if (_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=str(_DIST / "assets")), name="assets")

app.include_router(ui.router)
app.include_router(auth.router)
