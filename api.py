"""HIS Agent API — FastAPI HTTP server."""

import uuid, os
from pathlib import Path
from datetime import date as _date
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
import httpx
_STATIC = Path(__file__).parent / "static"
from pydantic import BaseModel

from agent import chat, chat_stream

app = FastAPI(title="HIS Agent API", version="1.0.0")


@app.on_event("startup")
async def _warmup():
    """Pre-load sentence-transformer model so first user request is fast."""
    import asyncio, sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent / "tools"))
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

# Session store — in-memory + persist to disk
# Doctor sessions: data/sessions/{doctor_id}/{conv_uuid}.json  (per conversation)
# Patient sessions: data/sessions/patient/{session_id}.json
import json as _json
from datetime import date as _date, datetime as _datetime

_sessions: dict[str, list] = {}          # session_id → messages
_doctor_current: dict[str, str] = {}     # doctor_id → active session_id
_SESSIONS_DIR = Path(__file__).parent / "data" / "sessions"
_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def _doctor_dir(doctor_id: str) -> Path:
    d = _SESSIONS_DIR / doctor_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _get_or_create_doctor_session(doctor_id: str) -> str:
    if doctor_id in _doctor_current:
        return _doctor_current[doctor_id]
    d = _SESSIONS_DIR / doctor_id
    if d.exists():
        files = sorted(d.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        if files:
            sid = f"doctor_{doctor_id}_{files[0].stem}"
            _doctor_current[doctor_id] = sid
            return sid
    return _new_doctor_session(doctor_id)


def _new_doctor_session(doctor_id: str) -> str:
    conv_uuid = str(uuid.uuid4())
    sid = f"doctor_{doctor_id}_{conv_uuid}"
    _doctor_current[doctor_id] = sid
    return sid


def _load_session(session_id: str) -> list:
    if session_id in _sessions:
        return _sessions[session_id]
    if session_id.startswith("doctor_"):
        parts = session_id[len("doctor_"):].rsplit("_", 1)
        if len(parts) == 2:
            p = _doctor_dir(parts[0]) / f"{parts[1]}.json"
            if p.exists():
                try:
                    raw = _json.loads(p.read_text(encoding="utf-8"))
                    msgs = raw["messages"] if isinstance(raw, dict) else raw
                    _sessions[session_id] = msgs
                    return msgs
                except Exception:
                    pass
    return []


def _save_session(session_id: str, history: list) -> None:
    _sessions[session_id] = history
    if not session_id.startswith("doctor_"):
        return
    parts = session_id[len("doctor_"):].rsplit("_", 1)
    if len(parts) != 2:
        return
    doctor_id, conv_file = parts
    p = _doctor_dir(doctor_id) / f"{conv_file}.json"
    now = _datetime.now().isoformat(timespec="seconds")
    conv = None
    if p.exists():
        try:
            raw = _json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                conv = raw
        except Exception:
            pass
    if conv is None:
        title = next(
            (m["content"][:45] for m in history
             if m.get("role") == "user" and isinstance(m.get("content"), str)),
            "Hội thoại mới",
        )
        conv = {"session_id": session_id, "title": title,
                "created_at": now, "updated_at": now, "messages": history}
    else:
        conv["messages"] = history
        conv["updated_at"] = now
    try:
        p.write_text(_json.dumps(conv, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _visible_messages(history: list) -> list:
    """Lọc chỉ user + assistant text messages để hiển thị."""
    return [
        {"role": m["role"], "content": m["content"]}
        for m in history
        if m.get("role") in ("user", "assistant")
        and isinstance(m.get("content"), str)
        and m.get("content", "").strip()
    ]


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    role: str = "patient"
    doctor_name: str = ""
    doctor_id: str = ""
    image_base64: str = ""
    image_mime: str = "image/jpeg"


class ChatResponse(BaseModel):
    reply: str
    session_id: str


@app.post("/chat", response_model=ChatResponse)
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
        reply, updated_history = chat(body.message, history, role=body.role, doctor_name=body.doctor_name, doctor_id=body.doctor_id, image_base64=body.image_base64, image_mime=body.image_mime)
        _save_session(session_id, updated_history)
        return ChatResponse(reply=reply, session_id=session_id)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/stream")
async def chat_stream_endpoint(body: ChatRequest):
    import asyncio, concurrent.futures, json as _json
    if body.role == "doctor" and body.doctor_id:
        pfx = f"doctor_{body.doctor_id}_"
        if body.session_id and body.session_id.startswith(pfx):
            session_id = body.session_id
            _doctor_current[body.doctor_id] = session_id
        else:
            session_id = _get_or_create_doctor_session(body.doctor_id)
    else:
        session_id = body.session_id or str(uuid.uuid4())
    history    = list(_load_session(session_id))  # mutable copy
    loop       = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def producer():
        try:
            for chunk in chat_stream(body.message, history, role=body.role, doctor_name=body.doctor_name, doctor_id=body.doctor_id, image_base64=body.image_base64, image_mime=body.image_mime):
                loop.call_soon_threadsafe(queue.put_nowait, chunk)
        except Exception as e:
            import traceback; traceback.print_exc()
            err = f"data: {_json.dumps({'type':'error','text':str(e)})}\n\n"
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


@app.delete("/session/{session_id}")
async def clear_session(session_id: str):
    _sessions.pop(session_id, None)
    return {"ok": True}


@app.get("/session/doctor/{doctor_id}/current")
async def get_doctor_current(doctor_id: str):
    """Hội thoại đang active — dùng khi đăng nhập."""
    session_id = _get_or_create_doctor_session(doctor_id)
    history = _load_session(session_id)
    return {"session_id": session_id, "messages": _visible_messages(history)}


@app.get("/session/doctor/{doctor_id}/today")
async def get_doctor_today(doctor_id: str):
    return await get_doctor_current(doctor_id)


@app.post("/session/doctor/{doctor_id}/new")
async def new_doctor_session_endpoint(doctor_id: str):
    """Tạo hội thoại mới."""
    sid = _new_doctor_session(doctor_id)
    return {"session_id": sid}


@app.delete("/session/doctor/{doctor_id}/today")
async def clear_doctor_today(doctor_id: str):
    sid = _new_doctor_session(doctor_id)
    return {"ok": True, "session_id": sid}


@app.get("/session/doctor/{doctor_id}/conversations")
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


@app.get("/session/doctor/{doctor_id}/conversation/{conv_id}")
async def get_doctor_conversation(doctor_id: str, conv_id: str):
    """Load một hội thoại cụ thể."""
    session_id = f"doctor_{doctor_id}_{conv_id}"
    history = _load_session(session_id)
    return {"session_id": session_id, "messages": _visible_messages(history)}


@app.delete("/session/doctor/{doctor_id}/conversation/{conv_id}")
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


@app.get("/health")
async def health():
    return {"status": "ok", "sessions": len(_sessions)}


# ── /api/departments ───────────────────────────────────────────
@app.get("/api/departments")
async def api_departments():
    url, auth = _aidbox()
    if not url:
        raise HTTPException(503, "AIDBOX_URL not configured")
    async with httpx.AsyncClient(timeout=15, auth=auth) as client:
        r = await client.get(f"{url}/fhir/Schedule", params={"_count": "200"})
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text[:300])
    seen: dict[str, str] = {}
    for s in _entries(r.json(), "Schedule"):
        for st in s.get("serviceType") or []:
            coding = ((st.get("concept") or {}).get("coding") or [{}])[0]
            code = coding.get("code", "")
            display = coding.get("display", "")
            if code and code not in seen:
                seen[code] = display
    return {"departments": [{"code": k, "name": v} for k, v in seen.items()]}


# ── /api/schedules?department= ────────────────────────────────
@app.get("/api/schedules")
async def api_schedules_by_dept(department: str = ""):
    url, auth = _aidbox()
    if not url:
        raise HTTPException(503, "AIDBOX_URL not configured")
    async with httpx.AsyncClient(timeout=15, auth=auth) as client:
        r = await client.get(f"{url}/fhir/Schedule", params={"_count": "200"})
        schedules = _entries(r.json(), "Schedule")

    result, pract_ids = [], []
    for s in schedules:
        dept_name = ""
        for st in s.get("serviceType") or []:
            coding = ((st.get("concept") or {}).get("coding") or [{}])[0]
            if not department or coding.get("code") == department:
                dept_name = coding.get("display", "")
                break
        if not dept_name:
            continue
        actor_ref = ((s.get("actor") or [{}])[0]).get("reference", "")
        pid = actor_ref.split("/")[1] if "/" in actor_ref else ""
        result.append({"schedule_id": s["id"], "practitioner_id": pid,
                        "department": dept_name, "doctor_name": ""})
        if pid:
            pract_ids.append(pid)

    if pract_ids:
        async with httpx.AsyncClient(timeout=15, auth=auth) as client:
            r2 = await client.get(f"{url}/fhir/Practitioner",
                                  params={"_id": ",".join(set(pract_ids)), "_count": "100"})
        p_names = {p["id"]: _pract_name(p) for p in _entries(r2.json(), "Practitioner")}
        for row in result:
            row["doctor_name"] = p_names.get(row["practitioner_id"], "BS. (Chưa rõ)")

    return {"schedules": result}


# ── /api/slots?schedule_id=&date= ────────────────────────────
@app.get("/api/slots")
async def api_slots(schedule_id: str, date: str):
    url, auth = _aidbox()
    if not url:
        raise HTTPException(503, "AIDBOX_URL not configured")
    params = [
        ("schedule", f"Schedule/{schedule_id}"),
        ("status", "free"),
        ("start", f"ge{date}T00:00:00"),
        ("start", f"le{date}T23:59:59"),
        ("_count", "100"), ("_sort", "start"),
    ]
    async with httpx.AsyncClient(timeout=15, auth=auth) as client:
        r = await client.get(f"{url}/fhir/Slot", params=params)
    slots = []
    for s in _entries(r.json(), "Slot"):
        start, end = s.get("start", ""), s.get("end", "")
        slots.append({
            "slot_id": s["id"], "start": start, "end": end,
            "start_time": start[11:16] if len(start) >= 16 else "",
            "end_time":   end[11:16]   if len(end)   >= 16 else "",
        })
    return {"slots": slots, "date": date}


# ── /api/book-appointment ─────────────────────────────────────
class BookingRequest(BaseModel):
    slot_id: str
    schedule_id: str
    patient_id: str | None = None
    patient_name: str = ""
    patient_phone: str = ""
    reason: str = ""


@app.post("/api/book-appointment")
async def api_book_appointment(body: BookingRequest):
    url, auth = _aidbox()
    if not url:
        raise HTTPException(503, "AIDBOX_URL not configured")

    async with httpx.AsyncClient(timeout=15, auth=auth) as client:
        slot_r = await client.get(f"{url}/fhir/Slot/{body.slot_id}")
        if slot_r.status_code >= 400:
            raise HTTPException(404, "Slot not found")
        slot  = slot_r.json()
        sched = (await client.get(f"{url}/fhir/Schedule/{body.schedule_id}")).json()

    actor_ref    = ((sched.get("actor") or [{}])[0]).get("reference", "")
    service_type = sched.get("serviceType", [])

    participants = [{"actor": {"reference": actor_ref}, "status": "accepted"}]
    if body.patient_id:
        participants.append({"actor": {"reference": f"Patient/{body.patient_id}"},
                             "status": "accepted"})

    appt: dict = {
        "resourceType": "Appointment",
        "status": "booked",
        "slot": [{"reference": f"Slot/{body.slot_id}"}],
        "start": slot.get("start"),
        "end":   slot.get("end"),
        "serviceType": service_type,
        "participant": participants,
    }
    if body.reason:
        appt["reason"] = [{"concept": {"text": body.reason}}]
    if body.patient_name:
        appt["description"] = f"BN: {body.patient_name}" + (
            f" | SĐT: {body.patient_phone}" if body.patient_phone else "")

    async with httpx.AsyncClient(timeout=15, auth=auth) as client:
        r = await client.post(f"{url}/fhir/Appointment", json=appt)
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text[:300])
        await client.patch(
            f"{url}/fhir/Slot/{body.slot_id}",
            json={"status": "busy"},
            headers={"Content-Type": "application/merge-patch+json"},
        )

    return {"ok": True, "appointment_id": r.json().get("id", "")}


@app.get("/", response_class=HTMLResponse)
async def chat_ui():
    return (_STATIC / "index.html").read_text(encoding="utf-8")


# ── /api/practitioners ────────────────────────────────────────
@app.get("/api/practitioners")
async def api_practitioners():
    url, auth = _aidbox()
    if not url:
        raise HTTPException(503, "AIDBOX_URL not configured")

    async with httpx.AsyncClient(timeout=15, auth=auth) as client:
        r = await client.get(f"{url}/fhir/Practitioner",
                             params={"_count": "50", "_sort": "family"})
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text[:300])
        bundle = r.json()

    rows = []
    for p in _entries(bundle, "Practitioner"):
        qual = (p.get("qualification") or [{}])[0]
        specialty = (
            (qual.get("code") or {}).get("text")
            or ((qual.get("code") or {}).get("coding") or [{}])[0].get("display", "")
        )
        rows.append({
            "id":        p.get("id", ""),
            "name":      _pract_name(p),
            "specialty": specialty,
        })
    return {"total": len(rows), "practitioners": rows}


# ── FHIR helpers ──────────────────────────────────────────────
def _aidbox():
    url = os.getenv("AIDBOX_URL", "").rstrip("/")
    cid = os.getenv("AIDBOX_CLIENT_ID", "")
    sec = os.getenv("AIDBOX_CLIENT_SECRET", "")
    return url, (cid, sec) if cid and sec else None


def _patient_name(p: dict) -> str:
    nm = (p.get("name") or [{}])[0]
    return f"{nm.get('family', '')} {' '.join(nm.get('given') or [])}".strip()


def _pract_name(p: dict) -> str:
    nm = (p.get("name") or [{}])[0]
    name = f"{nm.get('family', '')} {' '.join(nm.get('given') or [])}".strip()
    return f"BS. {name}" if name else ""


def _entries(bundle: dict, rtype: str) -> list[dict]:
    return [
        e["resource"] for e in (bundle.get("entry") or [])
        if e.get("resource", {}).get("resourceType") == rtype
    ]


# ── /api/patients ──────────────────────────────────────────────
@app.get("/api/patients")
async def api_patients(q: str = "", count: int = Query(default=30, alias="_count")):
    url, auth = _aidbox()
    if not url:
        raise HTTPException(503, "AIDBOX_URL not configured")

    params: dict = {"_count": str(count), "_sort": "-_lastUpdated"}
    if q:
        q = q.strip()
        if q.lstrip("+").isdigit() or (q.startswith("0") and len(q) >= 9):
            params["telecom"] = q
        else:
            tokens = q.split()
            if len(tokens) == 1:
                params["family"] = tokens[0]
            else:
                params["family"] = tokens[0]
                params["given"]  = " ".join(tokens[1:])

    async with httpx.AsyncClient(timeout=15, auth=auth) as client:
        r = await client.get(f"{url}/fhir/Patient", params=params)
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text[:300])
        bundle = r.json()

    patients = _entries(bundle, "Patient")
    rows = []
    for p in patients:
        phone = next(
            (t.get("value") for t in (p.get("telecom") or []) if t.get("system") == "phone"),
            ""
        )
        rows.append({
            "id":         p.get("id", ""),
            "name":       _patient_name(p),
            "gender":     "Nam" if p.get("gender") == "male" else "Nữ" if p.get("gender") == "female" else "",
            "birth_date": p.get("birthDate", ""),
            "phone":      phone,
        })
    return {"total": bundle.get("total", len(rows)), "patients": rows}


# ── /api/appointments ─────────────────────────────────────────
@app.get("/api/appointments")
async def api_appointments(date_str: str = "", practitioner_id: str = "",
                           date_from: str = "", date_to: str = ""):
    url, auth = _aidbox()
    if not url:
        raise HTTPException(503, "AIDBOX_URL not configured")

    if date_from or date_to:
        d_from = date_from or str(_date.today())
        d_to   = date_to   or str(_date.today())
        params = [
            ("date",   f"ge{d_from}T00:00:00"),
            ("date",   f"le{d_to}T23:59:59"),
            ("_count", "200"),
        ]
    else:
        target = date_str or str(_date.today())
        params = [
            ("date", f"ge{target}T00:00:00"),
            ("date", f"le{target}T23:59:59"),
            ("_count", "100"),
        ]
    if practitioner_id:
        params.append(("actor", f"Practitioner/{practitioner_id}"))

    async with httpx.AsyncClient(timeout=20, auth=auth) as client:
        r = await client.get(f"{url}/fhir/Appointment", params=params)
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text[:300])
        bundle = r.json()
        appointments = _entries(bundle, "Appointment")

        # Collect patient + practitioner IDs
        patient_ids = set()
        pract_ids   = set()
        for appt in appointments:
            for part in appt.get("participant") or []:
                ref = (part.get("actor") or {}).get("reference", "")
                if ref.startswith("Patient/"):
                    patient_ids.add(ref.split("/")[1])
                elif ref.startswith("Practitioner/"):
                    pract_ids.add(ref.split("/")[1])

        # Batch-fetch patients
        p_names: dict[str, str] = {}
        if patient_ids:
            r2 = await client.get(f"{url}/fhir/Patient",
                                  params={"_id": ",".join(patient_ids), "_count": "100"})
            for p in _entries(r2.json(), "Patient"):
                p_names[p["id"]] = _patient_name(p)

        # Batch-fetch practitioners
        pr_names: dict[str, str] = {}
        if pract_ids:
            r3 = await client.get(f"{url}/fhir/Practitioner",
                                  params={"_id": ",".join(pract_ids), "_count": "100"})
            for p in _entries(r3.json(), "Practitioner"):
                pr_names[p["id"]] = _pract_name(p)

    rows = []
    for appt in appointments:
        patient_name = ""
        pract_name   = ""
        for part in appt.get("participant") or []:
            ref = (part.get("actor") or {}).get("reference", "")
            if ref.startswith("Patient/"):
                patient_name = p_names.get(ref.split("/")[1], "")
            elif ref.startswith("Practitioner/"):
                pract_name = pr_names.get(ref.split("/")[1], "")

        st = (appt.get("serviceType") or [{}])[0]
        coding = ((st.get("concept") or {}).get("coding") or [{}])[0]
        dept = coding.get("display", coding.get("code", ""))

        reason_list = appt.get("reason") or []
        reason = (reason_list[0].get("concept") or {}).get("text", "") if reason_list else ""

        rows.append({
            "patient_name": patient_name,
            "practitioner": pract_name,
            "department":   dept,
            "start":        (appt.get("start") or "")[:16].replace("T", " "),
            "status":       appt.get("status", ""),
            "reason":       reason,
        })

    rows.sort(key=lambda a: a["start"])
    date_label = locals().get("d_from") or locals().get("target", "")
    return {"date": date_label, "total": len(rows), "appointments": rows}


# ── /api/observations ─────────────────────────────────────────
@app.get("/api/observations")
async def api_observations(patient_id: str = "", category: str = "all",
                           count: int = Query(default=30, alias="_count")):
    url, auth = _aidbox()
    if not url:
        raise HTTPException(503, "AIDBOX_URL not configured")

    params: list = [("_count", str(count)), ("_sort", "-date")]
    if patient_id:
        params.append(("subject", f"Patient/{patient_id}"))
    if category == "vital-signs":
        params.append(("category", "vital-signs"))
    elif category == "laboratory":
        params.append(("category", "laboratory"))

    async with httpx.AsyncClient(timeout=15, auth=auth) as client:
        r = await client.get(f"{url}/fhir/Observation", params=params)
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text[:300])
        bundle = r.json()
        observations = _entries(bundle, "Observation")

        # Collect patient IDs
        patient_ids = set()
        for obs in observations:
            ref = (obs.get("subject") or {}).get("reference", "")
            if ref.startswith("Patient/"):
                patient_ids.add(ref.split("/")[1])

        p_names: dict[str, str] = {}
        if patient_ids:
            r2 = await client.get(f"{url}/fhir/Patient",
                                  params={"_id": ",".join(patient_ids), "_count": "100"})
            for p in _entries(r2.json(), "Patient"):
                p_names[p["id"]] = _patient_name(p)

    _LOINC_VI = {
        "8480-6": "HA tâm thu", "8462-4": "HA tâm trương",
        "29463-7": "Cân nặng", "8302-2": "Chiều cao", "39156-5": "BMI",
        "8867-4": "Nhịp tim", "9279-1": "Nhịp thở", "8310-5": "Nhiệt độ",
        "59408-5": "SpO2", "2339-0": "Glucose máu", "4548-4": "HbA1c",
        "2093-3": "Cholesterol TP", "2160-0": "Creatinine", "3094-0": "Ure",
    }

    rows = []
    for obs in observations:
        ref = (obs.get("subject") or {}).get("reference", "")
        pid = ref.split("/")[1] if ref.startswith("Patient/") else ""

        coding = ((obs.get("code") or {}).get("coding") or [{}])[0]
        loinc  = coding.get("code", "")
        name   = _LOINC_VI.get(loinc) or coding.get("display") or (obs.get("code") or {}).get("text", "")

        # Extract value
        value = ""
        unit  = ""
        if "valueQuantity" in obs:
            vq    = obs["valueQuantity"]
            value = str(vq.get("value", ""))
            unit  = vq.get("unit", vq.get("code", ""))
        elif "valueString" in obs:
            value = obs["valueString"]
        elif "valueCodeableConcept" in obs:
            value = (obs["valueCodeableConcept"].get("text") or
                     ((obs["valueCodeableConcept"].get("coding") or [{}])[0]).get("display", ""))

        rows.append({
            "patient_name": p_names.get(pid, ""),
            "name":         name,
            "value":        value,
            "unit":         unit,
            "status":       obs.get("status", ""),
            "date":         (obs.get("effectiveDateTime") or obs.get("issued") or "")[:10],
        })

    return {"total": bundle.get("total", len(rows)), "observations": rows}


# ── /api/patient/{id} — detail panel ──────────────────────────
import asyncio as _asyncio

@app.get("/api/patient/{patient_id}")
async def api_patient_detail(patient_id: str):
    url, auth = _aidbox()
    if not url:
        raise HTTPException(503, "AIDBOX_URL not configured")

    today = str(_date.today())

    async with httpx.AsyncClient(timeout=15, auth=auth) as client:
        pt_r, obs_r, appt_r = await _asyncio.gather(
            client.get(f"{url}/fhir/Patient/{patient_id}"),
            client.get(f"{url}/fhir/Observation",
                       params={"subject": f"Patient/{patient_id}",
                               "_sort": "-date", "_count": "20"}),
            client.get(f"{url}/fhir/Appointment",
                       params=[("patient", f"Patient/{patient_id}"),
                                ("date", f"ge{today}T00:00:00"),
                                ("_sort", "date"), ("_count", "10")]),
        )

    # ── Patient demographics ──
    if pt_r.status_code >= 400:
        raise HTTPException(pt_r.status_code, "Patient not found")
    pt = pt_r.json()
    nm   = (pt.get("name") or [{}])[0]
    name = f"{nm.get('family', '')} {' '.join(nm.get('given') or [])}".strip()
    phone = next((t.get("value") for t in (pt.get("telecom") or [])
                  if t.get("system") == "phone"), "")
    birth = pt.get("birthDate", "")
    age   = ""
    if birth:
        try:
            age = str(_date.today().year - int(birth[:4]))
        except Exception:
            pass

    # ── Observations → split vital-signs / laboratory ──
    _LOINC_VI = {
        "8480-6": ("HA tâm thu",     "vital"), "8462-4": ("HA tâm trương", "vital"),
        "29463-7": ("Cân nặng",       "vital"), "8302-2": ("Chiều cao",      "vital"),
        "39156-5": ("BMI",            "vital"), "8867-4": ("Nhịp tim",       "vital"),
        "9279-1":  ("Nhịp thở",       "vital"), "8310-5": ("Nhiệt độ",       "vital"),
        "59408-5": ("SpO2",           "vital"), "2339-0": ("Glucose máu",    "lab"),
        "4548-4":  ("HbA1c",          "lab"),   "2093-3": ("Cholesterol TP", "lab"),
        "2160-0":  ("Creatinine",     "lab"),   "3094-0": ("Ure",            "lab"),
    }
    vitals, labs = [], []
    seen = set()
    for obs in _entries(obs_r.json(), "Observation"):
        coding = ((obs.get("code") or {}).get("coding") or [{}])[0]
        loinc  = coding.get("code", "")
        meta   = _LOINC_VI.get(loinc)
        label  = (meta[0] if meta else None) or coding.get("display") or (obs.get("code") or {}).get("text", "")
        if not label or label in seen:
            continue
        seen.add(label)
        cat = (meta[1] if meta else None) or \
              ((obs.get("category") or [{}])[0].get("coding") or [{}])[0].get("code", "lab")

        val, unit = "", ""
        if "valueQuantity" in obs:
            vq = obs["valueQuantity"]
            val  = str(vq.get("value", ""))
            unit = vq.get("unit", vq.get("code", ""))
        elif "valueString" in obs:
            val = obs["valueString"]

        row = {"name": label, "value": val, "unit": unit,
               "date": (obs.get("effectiveDateTime") or obs.get("issued") or "")[:10]}
        (vitals if cat == "vital" else labs).append(row)

    # ── Upcoming appointments ──
    appts = []
    for appt in _entries(appt_r.json(), "Appointment"):
        pract_name = ""
        for part in appt.get("participant") or []:
            ref = (part.get("actor") or {}).get("reference", "")
            if ref.startswith("Practitioner/"):
                pract_name = ref  # resolved below if needed

        st     = (appt.get("serviceType") or [{}])[0]
        coding = ((st.get("concept") or {}).get("coding") or [{}])[0]
        dept   = coding.get("display", coding.get("code", ""))
        start  = (appt.get("start") or "")[:16].replace("T", " ")
        appts.append({"start": start, "department": dept, "status": appt.get("status", "")})

    return {
        "id":         patient_id,
        "name":       name,
        "gender":     "Nam" if pt.get("gender") == "male" else "Nữ" if pt.get("gender") == "female" else "",
        "age":        age,
        "birth_date": birth,
        "phone":      phone,
        "vitals":     vitals[:6],
        "labs":       labs[:8],
        "appointments": appts,
    }


class RegisterPatientRequest(BaseModel):
    name: str
    gender: str
    birth_date: str
    phone: str = ""
    address: str = ""


@app.post("/api/register-patient")
async def api_register_patient(body: RegisterPatientRequest):
    url, auth = _aidbox()
    if not url:
        raise HTTPException(503, "AIDBOX_URL not configured")

    parts = body.name.strip().split()
    family = parts[0] if parts else body.name
    given  = parts[1:] if len(parts) > 1 else []

    fhir_patient: dict = {
        "resourceType": "Patient",
        "name": [{"use": "official", "family": family, "given": given}],
        "gender": body.gender,
        "birthDate": body.birth_date,
    }
    if body.phone:
        fhir_patient["telecom"] = [{"system": "phone", "value": body.phone, "use": "mobile"}]
    if body.address:
        fhir_patient["address"] = [{"use": "home", "text": body.address}]

    async with httpx.AsyncClient(timeout=15, auth=auth) as client:
        r = await client.post(f"{url}/fhir/Patient", json=fhir_patient)

    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text[:300])

    created = r.json()
    return {"patient_id": created.get("id", ""), "name": body.name}
