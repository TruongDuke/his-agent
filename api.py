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

# In-memory session store — đủ dùng cho demo/đồ án
# Production: thay bằng Redis hoặc PostgreSQL
_sessions: dict[str, list] = {}


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    role: str = "patient"
    doctor_name: str = ""


class ChatResponse(BaseModel):
    reply: str
    session_id: str


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(body: ChatRequest):
    session_id = body.session_id or str(uuid.uuid4())
    history = _sessions.get(session_id, [])

    try:
        reply, updated_history = chat(body.message, history, role=body.role, doctor_name=body.doctor_name)
        _sessions[session_id] = updated_history
        return ChatResponse(reply=reply, session_id=session_id)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/stream")
async def chat_stream_endpoint(body: ChatRequest):
    import asyncio, concurrent.futures, json as _json
    session_id = body.session_id or str(uuid.uuid4())
    history    = list(_sessions.get(session_id, []))  # mutable copy
    loop       = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def producer():
        try:
            for chunk in chat_stream(body.message, history, role=body.role, doctor_name=body.doctor_name):
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
            _sessions[session_id] = history  # persist mutated history
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


@app.get("/health")
async def health():
    return {"status": "ok", "sessions": len(_sessions)}


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
        tokens = q.strip().split()
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
async def api_appointments(date_str: str = "", practitioner_id: str = ""):
    url, auth = _aidbox()
    if not url:
        raise HTTPException(503, "AIDBOX_URL not configured")

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
    return {"date": target, "total": len(rows), "appointments": rows}


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
