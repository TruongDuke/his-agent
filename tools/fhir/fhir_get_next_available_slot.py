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
    "department":      ("string — MÃ khoa, ưu tiên dùng mã: PEDIAT/CARDIO/ENDO/ENT/NEURO/GASTRO/"
                        "RHEUMA/DERMA/OBGYN/OPHTHAL/UROLOGY/GENERAL/SURGERY/DENTAL/PULMO/ORTHO/"
                        "EMERG/INFECT. Tool cũng nhận tên khoa tiếng Việt, nhưng chỉ tên CÓ THẬT "
                        "— đừng tự nghĩ ra tên."),
    "date_from":       (
        "string (tùy chọn) — ngày user muốn khám. CHÉP NGUYÊN CỤM USER NÓI, đừng tự quy "
        "ra ngày: 'thứ hai tuần sau', 'chiều mai', 'ngày kia', '20/08'. Tool tự quy đổi. "
        "Bỏ trống nếu user không nói ngày."
    ),
    "time_from":       (
        "string (tùy chọn) — giờ user muốn khám. CHÉP NGUYÊN CỤM USER NÓI: '10h sáng', "
        "'3h chiều', '15h30', 'buổi chiều'. Tool tự quy đổi. Bỏ trống nếu user không nói giờ."
    ),
    "practitioner_id": "string (tùy chọn) — UUID bác sĩ. Nếu truyền, chỉ lấy slot của bác sĩ này.",
}

_WEEKDAY_VI = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]


def _resolve(raw_date: str, raw_time: str) -> tuple[str, str, bool]:
    """Quy đổi cụm ngày/giờ tiếng Việt sang ISO bằng code (xem _vi_dates).

    LLM tự cộng trừ ngày tháng thì hay lệch — "thứ hai tuần sau" từng ra Thứ 3 mà vẫn
    báo đúng yêu cầu. Nên nhận nguyên cụm user nói rồi quy đổi ở đây.
    Trả (date_iso, time_hhmm, hiểu_được_ngày). Rỗng nghĩa là user không nêu.
    """
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
    from _vi_dates import resolve_date, resolve_time

    raw_date = str(raw_date or "").strip()
    d = resolve_date(raw_date) if raw_date else None
    # Giờ có thể nằm trong chính cụm ngày ("chiều mai", "thứ 2 lúc 10h sáng")
    t = resolve_time(raw_time) or (resolve_time(raw_date) if raw_date else None)
    understood = bool(d) or not raw_date
    return (d.isoformat() if d else ""), (t or ""), understood


def run(args: dict) -> dict:
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
    from _aidbox_client import fhir_get, extract_entries
    from _departments import resolve_or_error
    from datetime import date, timedelta

    if not str(args.get("department") or "").strip():
        return {"error": "department is required"}
    # Nhận cả mã lẫn tên khoa: LLM hay truyền tên vì đó là thứ nó vừa nói với
    # bệnh nhân. Sai/mơ hồ thì trả lỗi có hướng dẫn để nó gọi lại đúng.
    dept, dept_display, err = resolve_or_error(args.get("department"))
    if err:
        return err
    filter_pract_id = str(args.get("practitioner_id") or "").strip()

    today = date.today()
    d_iso, t_iso, understood = _resolve(args.get("date_from"), args.get("time_from"))
    if not understood:
        return {
            "error": "unclear_date",
            "message": (f"Không hiểu ngày '{args.get('date_from')}'. Hỏi lại user muốn khám "
                        "ngày nào (VD 'thứ hai tuần sau', 'ngày mai', '20/08') — KHÔNG tự đoán."),
        }
    d_from = d_iso or today.isoformat()

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
        # Khoa có thật nhưng chưa cấu hình lịch khám (VD EMERG) — nói rõ để LLM
        # không tưởng là mình gọi sai tham số rồi thử lại vô ích.
        return {
            "error": "no_schedule_configured",
            "department": dept,
            "department_name": dept_display,
            "message": (f"{dept_display} ({dept}) chưa có lịch khám nào trong hệ thống. "
                        "Gợi ý bệnh nhân chọn khoa khác hoặc đến quầy tiếp nhận."),
        }

    time_from = t_iso

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
                "department":  dept_name or dept_display or dept,
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
            "department_name": dept_display,
            "message": f"Không còn slot trống trong 7 ngày tới cho {dept_display}.",
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
