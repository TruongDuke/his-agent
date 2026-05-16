"""Chat and session management routes."""

import uuid
import json as _json
import asyncio
import concurrent.futures

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from fastapi import HTTPException

from agent import chat, chat_stream
from api.models import ChatRequest, ChatResponse
from api.sessions import (
    _sessions,
    _doctor_current,
    _SESSIONS_DIR,
    _load_session,
    _save_session,
    _get_or_create_doctor_session,
    _new_doctor_session,
    _doctor_dir,
    _visible_messages,
)

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(body: ChatRequest):
    if body.role == "doctor" and body.doctor_id:
        pfx = f"doctor_{body.doctor_id}_"
        if body.session_id and body.session_id.startswith(pfx):
            session_id = body.session_id
            _doctor_current[body.doctor_id] = session_id
        else:
            session_id = _get_or_create_doctor_session(body.doctor_id)
    else:
        session_id = body.session_id or str(uuid.uuid4())
    history = _load_session(session_id)

    try:
        reply, updated_history = chat(
            body.message, history,
            role=body.role,
            doctor_name=body.doctor_name,
            doctor_id=body.doctor_id,
            image_base64=body.image_base64,
            image_mime=body.image_mime,
        )
        _save_session(session_id, updated_history)
        return ChatResponse(reply=reply, session_id=session_id)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def chat_stream_endpoint(body: ChatRequest):
    if body.role == "doctor" and body.doctor_id:
        pfx = f"doctor_{body.doctor_id}_"
        if body.session_id and body.session_id.startswith(pfx):
            session_id = body.session_id
            _doctor_current[body.doctor_id] = session_id
        else:
            session_id = _get_or_create_doctor_session(body.doctor_id)
    else:
        session_id = body.session_id or str(uuid.uuid4())
    history = list(_load_session(session_id))  # mutable copy
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def producer():
        try:
            for chunk in chat_stream(
                body.message, history,
                role=body.role,
                doctor_name=body.doctor_name,
                doctor_id=body.doctor_id,
                image_base64=body.image_base64,
                image_mime=body.image_mime,
            ):
                loop.call_soon_threadsafe(queue.put_nowait, chunk)
        except Exception as e:
            import traceback
            traceback.print_exc()
            err = f"data: {_json.dumps({'type': 'error', 'text': str(e)})}\n\n"
            loop.call_soon_threadsafe(queue.put_nowait, err)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

    async def generate():
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        executor.submit(producer)
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
            yield f"data: {_json.dumps({'session_id': session_id})}\n\n"
        finally:
            _save_session(session_id, history)
            executor.shutdown(wait=False)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete("/session/{session_id}")
async def clear_session(session_id: str):
    _sessions.pop(session_id, None)
    return {"ok": True}


@router.get("/session/doctor/{doctor_id}/current")
async def get_doctor_current(doctor_id: str):
    """Hội thoại đang active — dùng khi đăng nhập."""
    session_id = _get_or_create_doctor_session(doctor_id)
    history = _load_session(session_id)
    return {"session_id": session_id, "messages": _visible_messages(history)}


@router.get("/session/doctor/{doctor_id}/today")
async def get_doctor_today(doctor_id: str):
    return await get_doctor_current(doctor_id)


@router.post("/session/doctor/{doctor_id}/new")
async def new_doctor_session_endpoint(doctor_id: str):
    """Tạo hội thoại mới."""
    sid = _new_doctor_session(doctor_id)
    return {"session_id": sid}


@router.delete("/session/doctor/{doctor_id}/today")
async def clear_doctor_today(doctor_id: str):
    sid = _new_doctor_session(doctor_id)
    return {"ok": True, "session_id": sid}


@router.get("/session/doctor/{doctor_id}/conversations")
async def list_doctor_conversations(doctor_id: str):
    """Danh sách tất cả hội thoại (mới nhất trước)."""
    d = _SESSIONS_DIR / doctor_id
    if not d.exists():
        return {"conversations": []}
    result = []
    for f in sorted(d.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
        try:
            raw = _json.loads(f.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                msgs = _visible_messages(raw)
                title = next(
                    (m["content"][:45] for m in raw
                     if m.get("role") == "user" and isinstance(m.get("content"), str)),
                    "Hội thoại",
                )
                updated_at = ""
            else:
                msgs = _visible_messages(raw.get("messages", []))
                title = raw.get("title", "Hội thoại")
                updated_at = raw.get("updated_at", "")
            if not msgs:
                continue
            result.append({
                "conv_id": f.stem,
                "session_id": f"doctor_{doctor_id}_{f.stem}",
                "title": title,
                "updated_at": updated_at,
                "message_count": len(msgs),
            })
        except Exception:
            pass
    return {"conversations": result}


@router.get("/session/doctor/{doctor_id}/conversation/{conv_id}")
async def get_doctor_conversation(doctor_id: str, conv_id: str):
    """Load một hội thoại cụ thể."""
    session_id = f"doctor_{doctor_id}_{conv_id}"
    history = _load_session(session_id)
    return {"session_id": session_id, "messages": _visible_messages(history)}


@router.delete("/session/doctor/{doctor_id}/conversation/{conv_id}")
async def delete_doctor_conversation(doctor_id: str, conv_id: str):
    """Xóa một hội thoại."""
    sid = f"doctor_{doctor_id}_{conv_id}"
    _sessions.pop(sid, None)
    if _doctor_current.get(doctor_id) == sid:
        _doctor_current.pop(doctor_id, None)
    p = _doctor_dir(doctor_id) / f"{conv_id}.json"
    if p.exists():
        p.unlink()
    return {"ok": True}
