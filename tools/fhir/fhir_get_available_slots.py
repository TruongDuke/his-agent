"""Get available appointment slots for a hospital department (FHIR R5)."""

TOOL_NAME = "fhir_get_available_slots"
CATEGORY = "Healthcare"
DESCRIPTION = (
    "Lấy các slot (khe giờ) khám còn trống của 1 khoa trong 1 khoảng ngày. "
    "Input: department (mã khoa — dùng ĐÚNG code từ fhir_suggest_department), "
    "date_from (tùy chọn, ISO YYYY-MM-DD — mặc định hôm nay), "
    "date_to (tùy chọn, mặc định +7 ngày). "
    "Trả về list slot với slot_id, giờ bắt đầu, bác sĩ — dùng slot_id "
    "cho fhir_create_appointment để đặt lịch."
)
ARGS_SCHEMA = {
    "department": (
        "string — MÃ khoa, ưu tiên dùng mã: "
        "CARDIO (Tim Mạch), ENDO (Nội Tiết), ENT (Tai Mũi Họng), "
        "NEURO (Thần Kinh), GASTRO (Tiêu Hóa), RHEUMA (Cơ Xương Khớp), "
        "DERMA (Da Liễu), OBGYN (Sản Phụ Khoa), PEDIAT (Nhi), "
        "OPHTHAL (Mắt), UROLOGY (Thận Tiết Niệu), GENERAL (Nội Tổng Quát), "
        "SURGERY (Ngoại), DENTAL (Răng Hàm Mặt), PULMO (Hô Hấp), "
        "ORTHO (Chấn Thương Chỉnh Hình), EMERG (Cấp cứu), INFECT (Truyền Nhiễm). "
        "Tool cũng nhận tên khoa tiếng Việt, nhưng chỉ tên CÓ THẬT — đừng tự nghĩ ra tên."
    ),
    "date_from": "string (tùy chọn) — YYYY-MM-DD. Mặc định hôm nay",
    "date_to":   "string (tùy chọn) — YYYY-MM-DD. Mặc định +7 ngày",
}


_WEEKDAY_VI = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]


def _fmt_date_vi(iso_date: str) -> str:
    """'2026-04-27' -> 'Thứ 2 (27/04/2026)'"""
    from datetime import date as _date
    try:
        d = _date.fromisoformat(iso_date[:10])
        return f"{_WEEKDAY_VI[d.weekday()]} ({d.strftime('%d/%m/%Y')})"
    except Exception:
        return iso_date[:10]


def run(args: dict) -> dict:
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
    from _aidbox_client import fhir_get, extract_entries
    from _departments import resolve_or_error
    from datetime import date, timedelta

    if not str(args.get("department") or "").strip():
        return {"error": "department is required"}

    # Chuẩn hóa mã/tên khoa qua bảng dùng chung (tools/shared/_departments.py).
    # Trước đây mỗi tool tự giữ bảng alias riêng, chỉ tool này có, và map sai
    # "ORTHOPEDICS" -> RHEUMA.
    dept, dept_display, err = resolve_or_error(args.get("department"))
    if err:
        return err

    today = date.today()
    d_from = str(args.get("date_from") or "").strip() or today.isoformat()
    d_to = str(args.get("date_to") or "").strip() or (today + timedelta(days=7)).isoformat()

    # Step 1: Find Schedule by department service-type
    sched_bundle = fhir_get("Schedule", {"service-type": f"urn:vn:department|{dept}"})
    if "error" in sched_bundle:
        return sched_bundle

    schedules = extract_entries(sched_bundle)
    if not schedules:
        return {
            "department": dept,
            "department_name": dept_display,
            "count": 0,
            "slots": [],
            "message": (f"{dept_display} ({dept}) chưa có lịch khám nào trong hệ thống. "
                        "Gợi ý bệnh nhân chọn khoa khác hoặc đến quầy tiếp nhận."),
        }

    # Step 2: Query free slots for each schedule (usually 1 schedule/dept)
    all_slots = []
    for sched in schedules:
        sched_id = sched.get("id", "")
        # Get Practitioner info once per schedule
        actor_ref = ((sched.get("actor") or [{}])[0] or {}).get("reference", "")
        pract_name = "Bác sĩ phụ trách"
        if actor_ref.startswith("Practitioner/"):
            pract = fhir_get(actor_ref)
            if isinstance(pract, dict) and pract.get("resourceType") == "Practitioner":
                name = (pract.get("name") or [{}])[0]
                given = " ".join(name.get("given") or [])
                resolved = f"BS. {name.get('family','')} {given}".strip()
                if resolved and resolved != "BS.":
                    pract_name = resolved

        dept_name = ""
        stype = (sched.get("serviceType") or [{}])[0]
        if isinstance(stype, dict):
            coding = (stype.get("concept") or {}).get("coding") or [{}]
            dept_name = (coding[0] or {}).get("display", "")

        slot_bundle = fhir_get("Slot", {
            "schedule": f"Schedule/{sched_id}",
            "status": "free",
            "start": f"ge{d_from}",
            "_sort": "start",
            "_count": "100",
        })
        if "error" in slot_bundle:
            return slot_bundle

        for s in extract_entries(slot_bundle):
            start_iso = s.get("start", "")
            if start_iso[:10] > d_to:
                continue
            all_slots.append({
                "slot_id": s.get("id"),
                "date": start_iso[:10],                        # "2026-04-27"
                "date_vi": _fmt_date_vi(start_iso),            # "Thứ 2 (27/04/2026)"
                "time": start_iso[11:16],                      # "08:30"
                "end_time": (s.get("end") or "")[11:16],
                "practitioner": pract_name,
                "department": dept_name or dept_display or dept,
            })

    # Sort by date+time
    all_slots.sort(key=lambda x: (x["date"], x["time"]))

    return {
        "today": today.isoformat(),
        "today_vi": _fmt_date_vi(today.isoformat()),
        "department": dept,
        "department_name": dept_display,
        "date_from": d_from,
        "date_to": d_to,
        "count": len(all_slots),
        "slots": all_slots[:30],
        "message": f"Có {len(all_slots)} slot trống từ {_fmt_date_vi(d_from)} đến {_fmt_date_vi(d_to)}." if all_slots
                   else f"Không có slot trống trong khoảng {_fmt_date_vi(d_from)} - {_fmt_date_vi(d_to)}. Thử khoảng khác?",
        "instruction_for_llm": (
            "Đây là kết quả đầy đủ. HÃY TRÌNH BÀY NGAY danh sách lịch trống cho người dùng — "
            "KHÔNG hỏi thêm ID bệnh nhân hay BHYT. "
            "Nếu người dùng muốn đặt lịch, hỏi tên bệnh nhân. "
            "Khi đặt lịch, PHẢI copy chính xác slot_id. KHÔNG tự sinh UUID mới."
        ),
    }
