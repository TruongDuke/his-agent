"""Get appointments waiting for doctor confirmation (status=proposed)."""

TOOL_NAME = "fhir_get_pending_appointments"
CATEGORY = "Healthcare"
DESCRIPTION = (
    "Lấy danh sách lịch hẹn đang chờ bác sĩ xác nhận (status=proposed). "
    "Mỗi lịch gồm: tên bệnh nhân, triệu chứng, khoa, ngày giờ, email bệnh nhân. "
    "Dùng khi bác sĩ hỏi 'có lịch nào chờ xác nhận không?' hoặc muốn review lịch pending."
)
ARGS_SCHEMA = {
    "date_from": "string (tùy chọn) — YYYY-MM-DD. Mặc định hôm nay",
    "date_to":   "string (tùy chọn) — YYYY-MM-DD. Mặc định 7 ngày tới",
}


def run(args: dict) -> dict:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
    from _aidbox_client import _config
    from datetime import date, timedelta
    import httpx

    url, cid, sec = _config()
    if not url:
        return {"error": "AIDBOX_URL not configured"}
    auth = (cid, sec) if cid and sec else None

    today = date.today().isoformat()
    date_from = str(args.get("date_from") or "").strip() or today
    date_to = str(args.get("date_to") or "").strip() or (date.fromisoformat(date_from) + timedelta(days=7)).isoformat()

    with httpx.Client(timeout=15, auth=auth) as client:
        r = client.get(f"{url}/fhir/Appointment", params={
            "status": "proposed",
            "date": f"ge{date_from}T00:00:00",
            "_count": "50",
            "_sort": "date",
        })
        if r.status_code != 200:
            return {"error": f"Lỗi truy vấn FHIR (HTTP {r.status_code})"}

        entries = r.json().get("entry") or []
        results = []

        for e in entries:
            appt = e.get("resource", {})
            appt_id = appt.get("id", "")
            start = appt.get("start", "")
            if start[:10] > date_to:
                continue

            date_vi_str = start[8:10] + "/" + start[5:7] + "/" + start[:4] if start else "N/A"
            time_str = start[11:16] if start else "N/A"

            # Extract patient name
            patient_name = "N/A"
            patient_id = None
            dept_name = "N/A"
            practitioner_name = "N/A"
            clinical_note = ""
            patient_email = ""

            for p in (appt.get("participant") or []):
                actor = p.get("actor") or {}
                ref = actor.get("reference", "")
                display = actor.get("display", "")
                if ref.startswith("Patient/"):  # FHIR FHIR cho phép reference kèm sẵn một field display = tên người, lưu ngay tại đó 
                    patient_id = ref.split("/")[-1]
                    if display:
                        patient_name = display
                    else:  # display không có, phải fetch resource Patient để lấy tên
                        pr = client.get(f"{url}/fhir/{ref}") 
                        if pr.status_code == 200:
                            nm = (pr.json().get("name") or [{}])[0]
                            patient_name = f"{nm.get('family','')} {' '.join(nm.get('given',[]))}".strip()
                elif ref.startswith("Practitioner/"):
                    if display:
                        practitioner_name = display
                    else:
                        pr = client.get(f"{url}/fhir/{ref}")
                        if pr.status_code == 200:
                            nm = (pr.json().get("name") or [{}])[0]
                            practitioner_name = f"BS. {nm.get('family','')} {' '.join(nm.get('given',[]))}".strip()

            stype = appt.get("serviceType") or []
            if stype:
                coding = (stype[0].get("concept") or {}).get("coding") or [{}]
                dept_name = coding[0].get("display", "N/A")

            # Extract notes: clinical_note and patient_email
            for note in (appt.get("note") or []):
                text = note.get("text", "")
                if text.startswith("__patient_email__:"):
                    patient_email = text.replace("__patient_email__:", "").strip()
                else:
                    clinical_note = text

            # Extract reason
            reason = ""
            for r_item in (appt.get("reason") or []):
                reason = (r_item.get("concept") or {}).get("text", "")
                break

            results.append({
                "appointment_id": appt_id,
                "patient_name":   patient_name,
                "patient_id":     patient_id,
                "patient_email":  patient_email,
                "department":     dept_name,
                "practitioner":   practitioner_name,
                "date":           date_vi_str,
                "time":           time_str,
                "reason":         reason,
                "symptoms":       clinical_note,
            })

    if not results:
        return {"found": False, "count": 0, "message": "Không có lịch nào đang chờ xác nhận."}

    return {"found": True, "count": len(results), "pending": results}
