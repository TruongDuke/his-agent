"""Scheduling routes — departments, schedules, slots, booking."""

import httpx
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from api.deps import _aidbox, _entries, _pract_name

router = APIRouter()


# ── /api/departments ──────────────────────────────────────────
@router.get("/api/departments")
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


# ── /api/schedules?department= ───────────────────────────────
@router.get("/api/schedules")
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
@router.get("/api/slots")
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


@router.post("/api/book-appointment")
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
