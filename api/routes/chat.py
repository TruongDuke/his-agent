"""Chat and session management routes."""

import uuid
import json as _json
import asyncio
import concurrent.futures

from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse
from fastapi import HTTPException

from agent import chat, chat_stream
from api.doctor_config import load_cbc_config, compile_cbc_prompt
from api.models import ChatRequest, ChatResponse
from api.tokens import resolve_token
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


def _doctor_cbc_extra(body: ChatRequest) -> str:
    """Block chỉ dẫn trình bày báo cáo CBC theo cấu hình của bác sĩ."""
    if body.role == "doctor" and body.doctor_id:
        return compile_cbc_prompt(load_cbc_config(body.doctor_id))
    return ""


def _resolve_patient(body: ChatRequest, token: str) -> tuple[str, str]:
    """Trả về (patient_id, patient_name) đã xác thực từ token, hoặc rỗng nếu guest."""
    if body.role != "patient" or not token: # lấy từ login token
        return "", "" 
    info = resolve_token(token)
    if info and info["role"] == "patient":
        return info["fhir_id"], info["name"]
    return "", ""


@router.post("/chat", response_model=ChatResponse) #khởi tạo hội thoại mới hoặc tiếp tục hội thoại cũ
async def chat_endpoint(body: ChatRequest, x_session_token: str = Header(default="")): #body = tin nhắn
    if body.role == "doctor" and body.doctor_id: #xác định session_id cho bác sĩ, nếu có doctor_id thì tạo session riêng cho bác sĩ đó
        pfx = f"doctor_{body.doctor_id}_"
        if body.session_id and body.session_id.startswith(pfx):
            session_id = body.session_id
            _doctor_current[body.doctor_id] = session_id
        else:
            session_id = _get_or_create_doctor_session(body.doctor_id)
    else:
        session_id = body.session_id or str(uuid.uuid4())
    history = _load_session(session_id)
    patient_id, patient_name = _resolve_patient(body, x_session_token)

    # Khi bác sĩ mở session mới (lịch sử rỗng) và gửi __init__
    # → inject kế hoạch pending vào system prompt để agent chủ động nhắc
    extra_system = ""
    is_init = body.message.strip() == "__init__"
    if is_init and not history:
        try:
            base = "http://localhost:8000"
            if body.role == "doctor" and body.doctor_id:
                r = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: __import__("httpx").get(
                        f"{base}/api/doctor/{body.doctor_id}/pending-plans",
                        timeout=10,
                    )
                )
                plans = r.json().get("plans", []) if r.status_code == 200 else []
                if plans:
                    lines = "\n".join(
                        f"- {p['patient_name']} ({p['date']}): {p['plan']}"
                        for p in plans
                    )
                    extra_system = (
                        "=== KẾ HOẠCH CHƯA THEO DÕI ===\n"
                        "Bác sĩ có các kế hoạch từ lần khám gần đây chưa được theo dõi:\n"
                        f"{lines}\n"
                        "Hãy chủ động nhắc bác sĩ về các kế hoạch này khi chào hỏi."
                    )
            elif body.role == "patient" and patient_id:
                r = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: __import__("httpx").get(
                        f"{base}/api/patient/{patient_id}/clinical-impressions",
                        timeout=10,
                    )
                )
                impressions = r.json().get("impressions", []) if r.status_code == 200 else []
                latest = next((i for i in impressions if i.get("plan")), None)
                if latest:
                    extra_system = (
                        "=== KẾ HOẠCH TÁI KHÁM TỪ BÁC SĨ ===\n"
                        f"Lần khám gần nhất ({latest['date']}), bác sĩ ghi:\n"
                        f"- Chẩn đoán: {latest['diagnosis']}\n"
                        f"- Kế hoạch: {latest['plan']}\n"
                        "Hãy chủ động nhắc bệnh nhân về kế hoạch này khi chào hỏi "
                        "và hỏi xem tình trạng hiện tại thế nào."
                    )
        except Exception:
            pass

    cbc_extra = _doctor_cbc_extra(body)
    if cbc_extra:
        extra_system = f"{extra_system}\n\n{cbc_extra}" if extra_system else cbc_extra

    try:
        reply, updated_history = chat( #gọi đến agent.py để xử lý hội thoại, trả về phản hồi và lịch sử đã cập nhật
            body.message if not is_init else "Xin chào",
            history,
            role=body.role,
            doctor_name=body.doctor_name,
            doctor_id=body.doctor_id,
            patient_id=patient_id,
            patient_name=patient_name,
            image_base64=body.image_base64,
            image_mime=body.image_mime,
            extra_system=extra_system,
        )
        _save_session(session_id, updated_history)
        return ChatResponse(reply=reply, session_id=session_id) #bê câu trả lời reply về cho web
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def chat_stream_endpoint(body: ChatRequest, x_session_token: str = Header(default="")):
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
    patient_id, patient_name = _resolve_patient(body, x_session_token)
    extra_system = _doctor_cbc_extra(body)
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue() # quầy trung chuyển

    def producer():
        try:
            for chunk in chat_stream( # agent YIELD từng chunk, mỗi chunk là 1 phần của phản hồi, nhét vào queue để stream về client
                body.message, history,
                role=body.role,
                doctor_name=body.doctor_name,
                doctor_id=body.doctor_id,
                patient_id=patient_id,
                patient_name=patient_name,
                image_base64=body.image_base64,
                image_mime=body.image_mime,
                extra_system=extra_system,
            ):
                loop.call_soon_threadsafe(queue.put_nowait, chunk) # đẩy chunk vào queue
        except Exception as e:
            import traceback
            traceback.print_exc()
            err = f"data: {_json.dumps({'type': 'error', 'text': str(e)})}\n\n"
            loop.call_soon_threadsafe(queue.put_nowait, err)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel hết hàng

    async def generate():
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        executor.submit(producer) # chạy producer trong thread riêng để không block event loop
        try:
            while True:
                item = await queue.get() # lấy từng chunk từ queue
                if item is None:
                    break
                yield item # yield chunk về client
            yield f"data: {_json.dumps({'session_id': session_id})}\n\n"
        finally:
            _save_session(session_id, history)
            executor.shutdown(wait=False) # xong hết mới lưu lịch sử

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
