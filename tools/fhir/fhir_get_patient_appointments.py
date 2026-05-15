"""Tool: lấy danh sách lịch hẹn sắp tới của bệnh nhân."""
from __future__ import annotations


import httpx, os
from datetime import date

TOOL_NAME   = "fhir_get_patient_appointments"
CATEGORY    = "Healthcare"
DESCRIPTION = (
    "Lấy danh sách lịch hẹn của một bệnh nhân theo patient_id. "
    "Mặc định chỉ lấy lịch từ hôm nay trở đi (sắp tới). "
    "Dùng khi bệnh nhân hỏi 'tôi có lịch hẹn nào không', 'lịch khám sắp tới của tôi', "
    "hoặc khi bác sĩ muốn xem lịch hẹn tiếp theo của bệnh nhân."
)
ARGS_SCHEMA = {
    "patient_id":    "ID bệnh nhân (FHIR Patient ID). Bắt buộc.",
    "include_past":  "Có lấy lịch đã qua không? 'true' hoặc 'false'. Mặc định: false (chỉ lịch sắp tới).",
    "date_from":     "Ngày bắt đầu lọc, YYYY-MM-DD. Mặc định: hôm nay.",
}


def _aidbox():
    url  = os.getenv("AIDBOX_URL", "").rstrip("/")
    cid  = os.getenv("AIDBOX_CLIENT_ID", "")
    sec  = os.getenv("AIDBOX_CLIENT_SECRET", "")
    auth = (cid, sec) if cid and sec else None
    return url, auth


def _entries(bundle: dict, rtype: str):
    return [
        e["resource"] for e in (bundle.get("entry") or [])
        if e.get("resource", {}).get("resourceType") == rtype
    ]


def _pract_name(p: dict) -> str:
    nm = (p.get("name") or [{}])[0]
    name = f"{nm.get('family', '')} {' '.join(nm.get('given') or [])}".strip()
    return f"BS. {name}" if name else ""


def run(args: dict) -> dict:
    patient_id   = args.get("patient_id", "").strip()
    if not patient_id:
        return {"error": "Thiếu patient_id"}

    url, auth = _aidbox()
    if not url:
        return {"error": "AIDBOX_URL chưa được cấu hình"}

    include_past = str(args.get("include_past", "false")).lower() == "true"
    d_from       = args.get("date_from") or str(date.today())

    params = [
        ("patient", f"Patient/{patient_id}"),
        ("_sort",   "date"),
        ("_count",  "50"),
    ]
    if not include_past:
        params.append(("date", f"ge{d_from}T00:00:00"))

    try:
        with httpx.Client(timeout=15, auth=auth) as client:
            r = client.get(f"{url}/fhir/Appointment", params=params)
        if r.status_code >= 400:
            return {"error": f"FHIR {r.status_code}: {r.text[:200]}"}
        bundle = r.json()
    except Exception as e:
        return {"error": str(e)}

    appointments = _entries(bundle, "Appointment")
    if not appointments:
        msg = "Không có lịch hẹn sắp tới." if not include_past else "Không có lịch hẹn nào."
        return {"total": 0, "appointments": [], "message": msg}

    # Batch-fetch tên bác sĩ
    pract_ids = set()
    for appt in appointments:
        for part in appt.get("participant") or []:
            ref = (part.get("actor") or {}).get("reference", "")
            if ref.startswith("Practitioner/"):
                pract_ids.add(ref.split("/")[1])

    pr_names: dict[str, str] = {}
    if pract_ids:
        try:
            with httpx.Client(timeout=15, auth=auth) as client:
                r2 = client.get(f"{url}/fhir/Practitioner",
                                params={"_id": ",".join(pract_ids), "_count": "100"})
            for p in _entries(r2.json(), "Practitioner"):
                pr_names[p["id"]] = _pract_name(p)
        except Exception:
            pass

    rows = []
    for appt in appointments:
        pract_name = ""
        for part in appt.get("participant") or []:
            ref = (part.get("actor") or {}).get("reference", "")
            if ref.startswith("Practitioner/"):
                pract_name = pr_names.get(ref.split("/")[1], "")

        st     = (appt.get("serviceType") or [{}])[0]
        coding = ((st.get("concept") or {}).get("coding") or [{}])[0]
        dept   = coding.get("display", coding.get("code", ""))

        start  = (appt.get("start") or "")[:16].replace("T", " ")
        status = appt.get("status", "")
        note   = ((appt.get("note") or [{}])[0]).get("text", "")

        row = {
            "appointment_id": appt["id"],
            "start":          start,
            "department":     dept,
            "practitioner":   pract_name,
            "status":         status,
        }
        if note:
            row["clinical_note"] = note
        rows.append(row)

    return {"total": len(rows), "appointments": rows}
