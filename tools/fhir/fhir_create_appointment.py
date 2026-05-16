"""Book an appointment: create Appointment + mark Slot as busy (FHIR R5)."""
from __future__ import annotations

TOOL_NAME = "fhir_create_appointment"
CATEGORY = "Healthcare"
DESCRIPTION = (
    "Đặt lịch khám cho bệnh nhân. "
    "CÁCH GỌI CHUẨN (LUÔN DÙNG): patient_id + department + date + time. "
    "Tool tự tìm slot trống khớp với dept/date/time, tạo Appointment, đánh dấu slot busy. "
    "KHÔNG cần truyền slot_id — tự truyền department+date+time là đủ. "
    "Nếu truyền slot_id mà sai/giả → tool báo lỗi ngay."
)
ARGS_SCHEMA = {
    "patient_id":    "string — UUID bệnh nhân (từ fhir_search_patient hoặc fhir_register_new_patient)",
    "department":    "string — mã khoa: PEDIAT/CARDIO/ENDO/ENT/NEURO/GASTRO/RHEUMA/DERMA/OBGYN/OPHTHAL/UROLOGY/GENERAL/SURGERY/DENTAL/PULMO/ORTHO",
    "date":          "string — ngày khám YYYY-MM-DD (VD '2026-04-28')",
    "time":          "string — giờ bắt đầu HH:MM (VD '09:00')",
    "reason":        "string (tùy chọn) — lý do khám. Mặc định 'Khám theo yêu cầu'",
    "patient_email": "string (tùy chọn) — email bệnh nhân để gửi xác nhận tự động",
    "slot_id":       "string (tùy chọn, KHÔNG KHUYẾN NGHỊ) — chỉ dùng nếu có UUID slot chính xác từ fhir_get_available_slots",
    "clinical_note": (
        "string (tùy chọn) — Ghi chú lâm sàng đính kèm lịch hẹn. "
        "Dùng khi bệnh nhân đặt lịch qua sàng lọc SXHD: truyền tóm tắt "
        "kết quả dengue_symptom_assessment (severity, fever_day, triệu chứng chính). "
        "Ví dụ: 'Sàng lọc SXHD: warning — sốt ngày 3, đau bụng, nôn liên tục'"
    ),
}

SETTINGS_KEYS = ["gmail_user", "gmail_app_password", "gmail_from_name"]


def _resolve_slot_by_time(client, url: str, dept: str, date_str: str, time_str: str) -> tuple[str | None, str | None]:
    """Query slot khớp dept/date/time via dynamic schedule lookup. Returns (slot_id, error_msg)."""
    # Dynamic: find all schedules for this department via service-type coding
    r = client.get(
        f"{url}/fhir/Schedule",
        params={"service-type": f"urn:vn:department|{dept}", "_count": "20"},
    )
    if r.status_code != 200:
        return None, f"Lỗi tìm lịch khoa (HTTP {r.status_code})"

    sched_entries = (r.json().get("entry") or [])
    if not sched_entries:
        return None, f"Khoa '{dept}' chưa có lịch khám trong hệ thống. Gọi fhir_get_available_slots để kiểm tra khoa khác."

    want_prefix = f"{date_str}T{time_str}"  # "2026-04-27T08:30"
    for se in sched_entries:
        sched_id = (se.get("resource") or {}).get("id", "")
        if not sched_id:
            continue
        r2 = client.get(
            f"{url}/fhir/Slot",
            params={
                "schedule": f"Schedule/{sched_id}",
                "status": "free",
                "start": f"ge{date_str}",
                "_count": "50",
            },
        )
        if r2.status_code != 200:
            continue
        for e in (r2.json().get("entry") or []):
            slot = e.get("resource", {})
            if (slot.get("start") or "").startswith(want_prefix):
                return slot.get("id"), None

    return None, f"Không có slot trống ở khoa {dept} vào {date_str} lúc {time_str}. Gọi fhir_get_available_slots để xem slot nào đang trống."


def run(args: dict) -> dict:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
    from _aidbox_client import _config
    import httpx

    pid = str(args.get("patient_id") or "").strip()
    sid = str(args.get("slot_id") or "").strip()
    dept = str(args.get("department") or "").strip().upper()
    date_str = str(args.get("date") or "").strip()
    time_str = str(args.get("time") or "").strip()
    reason = str(args.get("reason") or "Khám theo yêu cầu").strip()
    patient_email = str(args.get("patient_email") or "").strip()
    clinical_note = str(args.get("clinical_note") or "").strip()

    if not pid:
        return {"error": "patient_id is required"}

    url, cid, sec = _config()
    if not url:
        return {"error": "AIDBOX_URL not configured"}
    auth = (cid, sec) if cid and sec else None

    with httpx.Client(timeout=15, auth=auth) as client:
        # Path A: resolve slot by (dept + date + time) if slot_id không có
        if not sid:
            if not (dept and date_str and time_str):
                return {"error": "Cần hoặc slot_id, hoặc đủ (department + date + time). Đã nhận: department=" + repr(dept) + ", date=" + repr(date_str) + ", time=" + repr(time_str)}
            resolved_sid, err = _resolve_slot_by_time(client, url, dept, date_str, time_str)
            if err:
                return {"error": err}
            sid = resolved_sid
        # Step 1: Fetch slot
        r = client.get(f"{url}/fhir/Slot/{sid}")
        if r.status_code != 200:
            return {"error": f"Slot không tồn tại (HTTP {r.status_code})"}
        slot = r.json()
        if slot.get("status") != "free":
            return {"error": f"Slot không còn trống (status={slot.get('status')}). Chọn slot khác."}

        slot_start = slot.get("start")
        slot_end = slot.get("end")
        sched_ref = (slot.get("schedule") or {}).get("reference", "")

        # Step 2: Get schedule → practitioner + serviceType
        r = client.get(f"{url}/fhir/{sched_ref}")
        if r.status_code != 200:
            return {"error": f"Không lấy được thông tin Schedule (HTTP {r.status_code})"}
        sched = r.json()

        actor_ref = ((sched.get("actor") or [{}])[0] or {}).get("reference", "")
        service_type = sched.get("serviceType", [])

        pract_name = "Bác sĩ phụ trách"
        if actor_ref.startswith("Practitioner/"):
            pr = client.get(f"{url}/fhir/{actor_ref}").json()
            if pr.get("resourceType") == "Practitioner":
                nm = (pr.get("name") or [{}])[0]
                resolved = f"BS. {nm.get('family','')} {' '.join(nm.get('given',[]))}".strip()
                if resolved and resolved != "BS.":
                    pract_name = resolved

        dept_name = ""
        if service_type and isinstance(service_type[0], dict):
            coding = (service_type[0].get("concept") or {}).get("coding") or [{}]
            dept_name = (coding[0] or {}).get("display", "")

        # Step 3: Verify patient exists
        r = client.get(f"{url}/fhir/Patient/{pid}")
        if r.status_code != 200:
            return {"error": f"Bệnh nhân không tồn tại (ID {pid})"}
        patient = r.json()
        p_name = (patient.get("name") or [{}])[0]
        patient_name = f"{p_name.get('family','')} {' '.join(p_name.get('given',[]))}".strip()

        # Step 4: Create Appointment — status "proposed" until doctor confirms
        appointment = {
            "resourceType": "Appointment",
            "status": "proposed",
            "serviceType": service_type,
            "reason": [{"concept": {"text": reason}}],
            "start": slot_start,
            "end": slot_end,
            "slot": [{"reference": f"Slot/{sid}"}],
            "participant": [
                {"actor": {"reference": f"Patient/{pid}"}, "status": "accepted"},
            ],
        }
        notes = []
        if clinical_note:
            notes.append({"text": clinical_note})
        if patient_email:
            notes.append({"text": f"__patient_email__:{patient_email}"})
        if notes:
            appointment["note"] = notes
        if actor_ref:
            appointment["participant"].append(
                {"actor": {"reference": actor_ref}, "status": "accepted"}
            )

        r = client.post(f"{url}/fhir/Appointment", json=appointment)
        if not (200 <= r.status_code < 300):
            return {"error": f"Tạo lịch thất bại (HTTP {r.status_code}): {r.text[:200]}"}
        appt = r.json()
        appt_id = appt.get("id")

        # Step 5: Mark slot as busy (PATCH or PUT)
        slot["status"] = "busy"
        r = client.put(f"{url}/fhir/Slot/{sid}", json=slot)
        slot_update_warning = None
        if not (200 <= r.status_code < 300):
            slot_update_warning = f"Slot update failed HTTP {r.status_code}"

        # Step 6: Tính queue number — số thứ tự trong ngày của khoa đó
        # Đếm tất cả appointment đã booked cho schedule này trong ngày
        queue_number = 1
        try:
            day_start = (slot_start or "")[:10]  # "2026-04-27"
            r = client.get(
                f"{url}/fhir/Appointment",
                params={
                    "date": f"ge{day_start}T00:00:00",
                    "actor": actor_ref or "",
                    "status": "booked",
                    "_count": "100",
                },
            )
            if r.status_code == 200:
                entries = r.json().get("entry", []) or []
                # Sort by start time, find position of our new appointment
                appts = [e.get("resource", {}) for e in entries]
                appts = [a for a in appts if (a.get("start") or "")[:10] == day_start]
                appts.sort(key=lambda a: a.get("start") or "")
                for idx, a in enumerate(appts, start=1):
                    if a.get("id") == appt_id:
                        queue_number = idx
                        break
        except Exception:
            pass  # fallback: queue_number = 1

    # User-friendly code: DEPT-DDMM-STT  (VD: CARDIO-2704-03)
    date_compact = (slot_start or "")[:10].replace("-", "")[4:]  # "2704" from "2026-04-27"
    booking_code = f"{dept_name_short_code(service_type)}-{date_compact}-{queue_number:02d}"

    time_vi = (slot_start or "")[:16].replace("T", " lúc ")
    result = {
        "success": True,
        "booking_code": booking_code,       # "CARDIO-2704-03"
        "queue_number": queue_number,       # số thứ tự trong ngày
        "patient_name": patient_name,
        "department": dept_name,
        "practitioner": pract_name,
        "start": (slot_start or "")[:16].replace("T", " "),
        "end": (slot_end or "")[:16].replace("T", " "),
        "reason": reason,
        "_appointment_id_internal": appt_id,  # giữ UUID cho hệ thống, tên có dấu _ để LLM bớt show
        "message": (
            f"Đã đặt lịch thành công!\n"
            f"Bệnh nhân: {patient_name}\n"
            f"Khoa: {dept_name}\n"
            f"Bác sĩ: {pract_name}\n"
            f"Thời gian: {time_vi}\n"
            f"Số thứ tự: {queue_number}\n"
            f"Mã lịch hẹn: {booking_code}"
        ),
    }
    if slot_update_warning:
        result["warning"] = slot_update_warning

    # Email sẽ được gửi khi bác sĩ confirm (fhir_confirm_appointment)
    if patient_email:
        result["patient_email"] = patient_email
        result["pending_confirmation"] = True
        result["note_for_doctor"] = f"Lịch chờ bác sĩ xác nhận. Email xác nhận sẽ gửi đến {patient_email} sau khi bác sĩ duyệt."

    return result


def dept_name_short_code(service_type: list) -> str:
    """Pick the department code from serviceType for display."""
    if not service_type or not isinstance(service_type[0], dict):
        return "APT"
    coding = (service_type[0].get("concept") or {}).get("coding") or [{}]
    return (coding[0] or {}).get("code", "APT") or "APT"
