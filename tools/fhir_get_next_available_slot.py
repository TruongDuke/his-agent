"""Get the single earliest available slot for a department (for URGENT triage flow)."""

TOOL_NAME = "fhir_get_next_available_slot"
CATEGORY = "Healthcare"
DESCRIPTION = (
    "Lấy slot trống SỚM NHẤT của một khoa — dùng cho luồng URGENT triage. "
    "Trả về đúng 1 slot gần nhất (ngày + giờ + bác sĩ). "
    "Khác với fhir_get_available_slots (trả về danh sách): tool này chỉ trả 1 slot để đặt luôn, "
    "không cần user chọn. Dùng khi urgency_level=URGENT và cần đặt lịch nhanh nhất có thể."
)
ARGS_SCHEMA = {
    "department": "string — mã khoa (PEDIAT/CARDIO/ENDO/ENT/NEURO/GASTRO/RHEUMA/DERMA/OBGYN/OPHTHAL/UROLOGY/GENERAL/SURGERY/DENTAL/PULMO/ORTHO)",
    "date_from":  "string (tùy chọn) — YYYY-MM-DD. Mặc định hôm nay",
}

_WEEKDAY_VI = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]


def run(args: dict) -> dict:
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from _aidbox_client import fhir_get, extract_entries
    from datetime import date, timedelta

    dept = str(args.get("department") or "").strip().upper()
    if not dept:
        return {"error": "department is required"}

    today = date.today()
    d_from = str(args.get("date_from") or "").strip() or today.isoformat()

    # Search up to 7 days ahead to find first available slot
    d_to = (date.fromisoformat(d_from) + timedelta(days=7)).isoformat()

    # Current datetime in Vietnam timezone (UTC+7) for filtering past slots
    from datetime import datetime, timezone, timedelta as td
    now_vn = datetime.now(timezone(td(hours=7)))
    now_iso = now_vn.strftime("%Y-%m-%dT%H:%M")

    # Find schedules for this department
    sched_bundle = fhir_get("Schedule", {"service-type": f"urn:vn:department|{dept}"})
    schedules = extract_entries(sched_bundle)
    if not schedules:
        return {"error": f"Không tìm thấy lịch khám cho khoa '{dept}'"}

    earliest = None

    for sched in schedules:
        sched_id = sched.get("id", "")
        actor_ref = ((sched.get("actor") or [{}])[0] or {}).get("reference", "")
        pract_name = ""
        if actor_ref.startswith("Practitioner/"):
            pract = fhir_get(actor_ref)
            if isinstance(pract, dict) and pract.get("resourceType") == "Practitioner":
                name = (pract.get("name") or [{}])[0]
                given = " ".join(name.get("given") or [])
                pract_name = f"BS. {name.get('family', '')} {given}".strip()

        dept_name = ""
        stype = (sched.get("serviceType") or [{}])[0]
        if isinstance(stype, dict):
            coding = (stype.get("concept") or {}).get("coding") or [{}]
            dept_name = (coding[0] or {}).get("display", dept)

        slot_bundle = fhir_get("Slot", {
            "schedule": f"Schedule/{sched_id}",
            "status": "free",
            "start": f"ge{d_from}",
            "_sort": "start",
            "_count": "20",
        })

        for s in extract_entries(slot_bundle):
            start_iso = s.get("start", "")
            if start_iso[:10] > d_to:
                continue
            # Bỏ qua slot đã qua giờ hiện tại (so sánh YYYY-MM-DDTHH:MM)
            if start_iso[:16] <= now_iso:
                continue
            if earliest is None or start_iso < earliest["start_iso"]:
                d = date.fromisoformat(start_iso[:10])
                weekday = _WEEKDAY_VI[d.weekday()]
                earliest = {
                    "slot_id":     s.get("id"),
                    "date":        start_iso[:10],
                    "date_vi":     f"{weekday} ({d.strftime('%d/%m/%Y')})",
                    "time":        start_iso[11:16],
                    "end_time":    (s.get("end") or "")[11:16],
                    "department":  dept_name or dept,
                    "practitioner": pract_name,
                    "start_iso":   start_iso,
                }

    if not earliest:
        return {
            "found": False,
            "department": dept,
            "message": f"Không còn slot trống trong 7 ngày tới cho khoa {dept}.",
        }

    slot = earliest
    return {
        "found": True,
        "department":   slot["department"],
        "date":         slot["date"],
        "date_vi":      slot["date_vi"],
        "time":         slot["time"],
        "practitioner": slot["practitioner"],
        "confirm_message": (
            f"Slot sớm nhất: {slot['department']}, "
            f"{slot['date_vi']} lúc {slot['time']}, "
            f"{slot['practitioner']}. "
            "Xác nhận đặt lịch này không?"
        ),
        "instruction_for_llm": (
            f"SLOT SỚM NHẤT: department='{dept}', date='{slot['date']}', time='{slot['time']}'. "
            "Hiển thị confirm_message cho user và hỏi xác nhận. "
            "Khi user xác nhận: hỏi email rồi gọi NGAY fhir_create_appointment("
            f"department='{dept}', date='{slot['date']}', time='{slot['time']}', patient_email=...). "
            "TUYỆT ĐỐI KHÔNG gọi lại fhir_get_available_slots hay fhir_get_next_available_slot. "
            "KHÔNG hỏi user chọn giờ hay slot_id."
        ),
    }
