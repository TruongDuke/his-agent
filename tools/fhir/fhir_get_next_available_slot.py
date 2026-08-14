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
    "department":      "string — mã khoa (PEDIAT/CARDIO/ENDO/ENT/NEURO/GASTRO/RHEUMA/DERMA/OBGYN/OPHTHAL/UROLOGY/GENERAL/SURGERY/DENTAL/PULMO/ORTHO)",
    "date_from":       "string (tùy chọn) — YYYY-MM-DD. Mặc định hôm nay",
    "time_from":       (
        "string (tùy chọn) — HH:MM. Giờ user MUỐN khám. PHẢI truyền khi user nói giờ "
        "(VD '15h chiều mai' → date_from=ngày mai, time_from='15:00'; 'buổi chiều' → '13:00'; "
        "'buổi sáng' → '08:00'). Không truyền thì tool trả slot sớm nhất bất kể giờ."
    ),
    "practitioner_id": "string (tùy chọn) — UUID bác sĩ. Nếu truyền, chỉ lấy slot của bác sĩ này.",
}

_WEEKDAY_VI = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]


def _norm_time(raw: str) -> str:
    """'15h', '15', '15:00', '15h30' → 'HH:MM'. Trả rỗng nếu không hiểu."""
    t = str(raw or "").strip().lower().replace("giờ", "h")
    if not t:
        return ""
    t = t.replace("h", ":") if "h" in t else t
    t = t.rstrip(":") if t.endswith(":") else t
    parts = t.split(":")
    try:
        hh = int(parts[0])
        mm = int(parts[1]) if len(parts) > 1 and parts[1] else 0
    except (ValueError, IndexError):
        return ""
    if not (0 <= hh < 24 and 0 <= mm < 60):
        return ""
    return f"{hh:02d}:{mm:02d}"


def run(args: dict) -> dict:
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from _aidbox_client import fhir_get, extract_entries
    from datetime import date, timedelta

    dept = str(args.get("department") or "").strip().upper()
    if not dept:
        return {"error": "department is required"}
    filter_pract_id = str(args.get("practitioner_id") or "").strip()

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

    time_from = _norm_time(args.get("time_from"))

    # Ba mức ưu tiên, xét theo đúng thứ tự user quan tâm:
    #   1. đúng ngày user xin, từ giờ user xin trở đi
    #   2. ngày khác trong tuần, nhưng vẫn đúng khung giờ đó
    #   3. sớm nhất bất kể giờ — chỉ dùng khi hai mức trên không có
    exact = None       # (1)
    same_time = None   # (2)
    earliest = None    # (3)

    def _better(cur, cand):
        return cur is None or cand["start_iso"] < cur["start_iso"]

    for sched in schedules:
        sched_id = sched.get("id", "")
        actor_ref = ((sched.get("actor") or [{}])[0] or {}).get("reference", "")

        # Filter by practitioner if requested
        if filter_pract_id:
            sched_pract_id = actor_ref.split("/")[-1] if actor_ref.startswith("Practitioner/") else ""
            if sched_pract_id != filter_pract_id:
                continue
        pract_name = "Bác sĩ phụ trách"
        if actor_ref.startswith("Practitioner/"):
            pract = fhir_get(actor_ref)
            if isinstance(pract, dict) and pract.get("resourceType") == "Practitioner":
                name = (pract.get("name") or [{}])[0]
                given = " ".join(name.get("given") or [])
                resolved = f"BS. {name.get('family', '')} {given}".strip()
                if resolved and resolved != "BS.":
                    pract_name = resolved

        dept_name = ""
        stype = (sched.get("serviceType") or [{}])[0]
        if isinstance(stype, dict):
            coding = (stype.get("concept") or {}).get("coding") or [{}]
            dept_name = (coding[0] or {}).get("display", dept)

        slot_bundle = fhir_get("Slot", {
            "schedule": f"Schedule/{sched_id}",
            "status": "free",
            "start": f"ge{now_iso}",
            "_sort": "start",
            "_count": "50",
        })

        for s in extract_entries(slot_bundle):
            start_iso = s.get("start", "")
            if start_iso[:10] > d_to:
                continue
            d = date.fromisoformat(start_iso[:10])
            cand = {
                "slot_id":     s.get("id"),
                "date":        start_iso[:10],
                "date_vi":     f"{_WEEKDAY_VI[d.weekday()]} ({d.strftime('%d/%m/%Y')})",
                "time":        start_iso[11:16],
                "end_time":    (s.get("end") or "")[11:16],
                "department":  dept_name or dept,
                "practitioner": pract_name,
                "start_iso":   start_iso,
            }
            if _better(earliest, cand):
                earliest = cand
            if time_from and cand["time"] >= time_from:
                if cand["date"] == d_from and _better(exact, cand):
                    exact = cand
                elif _better(same_time, cand):
                    same_time = cand

    if not earliest:
        return {
            "found": False,
            "department": dept,
            "message": f"Không còn slot trống trong 7 ngày tới cho khoa {dept}.",
        }

    # Chọn slot + dựng câu xác nhận. Khi không đáp ứng đúng giờ user xin thì PHẢI nói ra,
    # không được lẳng lặng đưa slot khác như thể đó là thứ user yêu cầu — bệnh nhân sẽ
    # bấm đồng ý rồi hôm sau đến sai giờ.
    slot = exact or same_time or earliest
    matched = "exact" if exact else ("same_time" if same_time else "fallback")

    if not time_from:
        confirm = (f"Slot sớm nhất: {slot['department']}, {slot['date_vi']} lúc {slot['time']}, "
                   f"{slot['practitioner']}. Xác nhận đặt lịch này không?")
        note = ""
    elif matched == "exact":
        confirm = (f"Có slot đúng yêu cầu: {slot['department']}, {slot['date_vi']} lúc "
                   f"{slot['time']}, {slot['practitioner']}. Xác nhận đặt lịch này không?")
        note = ""
    elif matched == "same_time":
        confirm = (f"Ngày bạn chọn không còn slot từ {time_from} trở đi. "
                   f"Gần nhất cùng khung giờ là {slot['date_vi']} lúc {slot['time']}, "
                   f"{slot['practitioner']}. Bạn đặt lịch này nhé?")
        note = f"Không có slot {time_from} ngày {d_from}."
    else:
        confirm = (f"Rất tiếc, khoa {slot['department']} không còn slot nào từ {time_from} "
                   f"trở đi trong tuần tới. Slot trống sớm nhất là {slot['date_vi']} lúc "
                   f"{slot['time']}, {slot['practitioner']}. Bạn có muốn đặt giờ này không?")
        note = f"KHÔNG có slot nào từ {time_from} trở đi — đây là slot sớm nhất, KHÁC giờ user xin."

    return {
        "found": True,
        "slot_id":      slot["slot_id"],
        "department":   slot["department"],
        "date":         slot["date"],
        "date_vi":      slot["date_vi"],
        "time":         slot["time"],
        "practitioner": slot["practitioner"],
        "requested_time":   time_from or None,
        "matched_request":  matched == "exact" if time_from else None,
        "mismatch_note":    note or None,
        "confirm_message":  confirm,
        "instruction_for_llm": (
            f"SLOT ĐỀ XUẤT: department='{dept}', date='{slot['date']}', time='{slot['time']}'. "
            + (f"⚠ USER XIN {time_from} NHƯNG SLOT NÀY LÀ {slot['time']}. "
               "BẮT BUỘC nói rõ là không có giờ user xin TRƯỚC khi mời đặt giờ khác. "
               "TUYỆT ĐỐI KHÔNG trình bày slot này như thể đúng giờ user yêu cầu. "
               if time_from and matched != "exact" else "")
            + "Hiển thị confirm_message cho user và hỏi xác nhận. "
            "Khi user xác nhận: hỏi email rồi gọi NGAY fhir_create_appointment("
            f"department='{dept}', date='{slot['date']}', time='{slot['time']}', patient_email=...). "
            "TUYỆT ĐỐI KHÔNG gọi lại fhir_get_available_slots hay fhir_get_next_available_slot. "
            "KHÔNG hỏi user chọn giờ hay slot_id."
        ),
    }
