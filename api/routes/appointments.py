"""Pending appointment routes — list, confirm, reject."""

import os
import httpx
from datetime import date as _date_cls, timedelta
from fastapi import APIRouter, HTTPException

from api.deps import _aidbox, _entries, _patient_name, _pract_name

router = APIRouter()


@router.get("/api/pending-appointments")
async def api_pending_appointments(date_from: str = "", date_to: str = ""):
    url, auth = _aidbox()
    if not url:
        raise HTTPException(503, "AIDBOX_URL not configured")

    d_from = date_from or str(_date_cls.today())
    d_to   = date_to   or str(_date_cls.today() + timedelta(days=7))

    async with httpx.AsyncClient(timeout=20, auth=auth) as client:
        r = await client.get(f"{url}/fhir/Appointment", params=[
            ("status", "proposed"),
            ("date",   f"ge{d_from}T00:00:00"),
            ("_count", "100"),
            ("_sort",  "date"),
        ])
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text[:300])
        entries = r.json().get("entry") or []

        patient_ids = set()
        pract_ids   = set()
        for e in entries:
            appt = e.get("resource", {})
            for p in (appt.get("participant") or []):
                ref = (p.get("actor") or {}).get("reference", "")
                if ref.startswith("Patient/"):
                    patient_ids.add(ref.split("/")[1])
                elif ref.startswith("Practitioner/"):
                    pract_ids.add(ref.split("/")[1])

        p_names: dict = {}
        if patient_ids:
            r2 = await client.get(f"{url}/fhir/Patient",
                                  params={"_id": ",".join(patient_ids), "_count": "100"})
            for p in _entries(r2.json(), "Patient"):
                p_names[p["id"]] = _patient_name(p)

        pr_names: dict = {}
        if pract_ids:
            r3 = await client.get(f"{url}/fhir/Practitioner",
                                  params={"_id": ",".join(pract_ids), "_count": "100"})
            for p in _entries(r3.json(), "Practitioner"):
                pr_names[p["id"]] = _pract_name(p)

    rows = []
    for e in entries:
        appt = e.get("resource", {})
        if (appt.get("start") or "")[:10] > d_to:
            continue
        start        = appt.get("start", "")
        date_vi      = start[8:10] + "/" + start[5:7] + "/" + start[:4] if start else ""
        time_str     = start[11:16] if start else ""
        patient_name = ""
        pract_name   = ""
        patient_id   = None

        for p in (appt.get("participant") or []):
            ref = (p.get("actor") or {}).get("reference", "")
            if ref.startswith("Patient/"):
                patient_id   = ref.split("/")[1]
                patient_name = p_names.get(patient_id, "")
            elif ref.startswith("Practitioner/"):
                pract_name = pr_names.get(ref.split("/")[1], "")

        coding = (((appt.get("serviceType") or [{}])[0]).get("concept") or {}).get("coding") or [{}]
        dept   = coding[0].get("display", "")

        clinical_note = ""
        patient_email = ""
        for note in (appt.get("note") or []):
            text = note.get("text", "")
            if text.startswith("__patient_email__:"):
                patient_email = text.replace("__patient_email__:", "").strip()
            else:
                clinical_note = text

        reason = ""
        for r_item in (appt.get("reason") or []):
            reason = (r_item.get("concept") or {}).get("text", "")
            break

        rows.append({
            "appointment_id": appt.get("id", ""),
            "patient_name":   patient_name,
            "patient_id":     patient_id,
            "patient_email":  patient_email,
            "department":     dept,
            "practitioner":   pract_name,
            "date":           date_vi,
            "time":           time_str,
            "reason":         reason,
            "symptoms":       clinical_note,
        })

    rows.sort(key=lambda a: a["date"] + a["time"])
    return {"total": len(rows), "pending": rows}


@router.post("/api/confirm-appointment/{appointment_id}")
async def api_confirm_appointment(appointment_id: str):
    from tools.fhir.fhir_confirm_appointment import run as confirm_run
    result = confirm_run({
        "appointment_id": appointment_id,
        "_settings": {
            "gmail_user":         os.getenv("GMAIL_USER", ""),
            "gmail_app_password": os.getenv("GMAIL_APP_PASSWORD", ""),
            "gmail_from_name":    os.getenv("GMAIL_FROM_NAME", "Bệnh viện Đa khoa Hà Nội"),
        }
    })
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.post("/api/reject-appointment/{appointment_id}")
async def api_reject_appointment(appointment_id: str, reason: str = "Bác sĩ từ chối lịch hẹn"):
    from tools.fhir.fhir_reject_appointment import run as reject_run
    result = reject_run({"appointment_id": appointment_id, "reason": reason})
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result
