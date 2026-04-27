"""Book an appointment: create Appointment + mark Slot as busy (FHIR R5)."""

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
    sys.path.insert(0, os.path.dirname(__file__))
    from _aidbox_client import _config
    import httpx

    pid = str(args.get("patient_id") or "").strip()
    sid = str(args.get("slot_id") or "").strip()
    dept = str(args.get("department") or "").strip().upper()
    date_str = str(args.get("date") or "").strip()
    time_str = str(args.get("time") or "").strip()
    reason = str(args.get("reason") or "Khám theo yêu cầu").strip()
    patient_email = str(args.get("patient_email") or "").strip()

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

        pract_name = ""
        if actor_ref.startswith("Practitioner/"):
            pr = client.get(f"{url}/fhir/{actor_ref}").json()
            if pr.get("resourceType") == "Practitioner":
                nm = (pr.get("name") or [{}])[0]
                pract_name = f"BS. {nm.get('family','')} {' '.join(nm.get('given',[]))}".strip()

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

        # Step 4: Create Appointment
        appointment = {
            "resourceType": "Appointment",
            "status": "booked",
            "serviceType": service_type,
            "reason": [{"concept": {"text": reason}}],
            "start": slot_start,
            "end": slot_end,
            "slot": [{"reference": f"Slot/{sid}"}],
            "participant": [
                {"actor": {"reference": f"Patient/{pid}"}, "status": "accepted"},
            ],
        }
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

    # Auto-send confirmation email if patient_email provided
    if patient_email and appt_id:
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            cfg = args.get("_settings") or {}
            gmail_user = (cfg.get("gmail_user") or "").strip()
            gmail_pass = (cfg.get("gmail_app_password") or "").strip()
            from_name = (cfg.get("gmail_from_name") or "Bệnh viện Đa khoa Hà Nội").strip()

            if gmail_user and gmail_pass:
                date_str_vi = (slot_start or "")[:10]
                date_vi = date_str_vi[8:] + "/" + date_str_vi[5:7] + "/" + date_str_vi[:4]
                time_vi_short = (slot_start or "")[11:16]
                subject = f"✅ Xác nhận lịch khám - {dept_name} - {date_vi} {time_vi_short}"
                html = f"""<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:20px">
  <div style="background:#0f62fe;color:white;padding:20px;border-radius:8px 8px 0 0">
    <h2 style="margin:0">🏥 Bệnh viện Đa khoa Hà Nội</h2>
    <p style="margin:4px 0 0">Xác nhận lịch khám</p>
  </div>
  <div style="border:1px solid #e0e0e0;border-top:none;padding:24px;border-radius:0 0 8px 8px">
    <p>Xin chào <strong>{patient_name}</strong>,</p>
    <p>Lịch khám của bạn đã được xác nhận:</p>
    <table style="width:100%;border-collapse:collapse;margin:16px 0">
      <tr style="background:#f4f4f4"><td style="padding:10px;font-weight:bold;width:40%">📅 Ngày khám</td><td style="padding:10px">{date_vi}</td></tr>
      <tr><td style="padding:10px;font-weight:bold">⏰ Giờ khám</td><td style="padding:10px">{time_vi_short}</td></tr>
      <tr style="background:#f4f4f4"><td style="padding:10px;font-weight:bold">🏥 Khoa</td><td style="padding:10px">{dept_name}</td></tr>
      <tr><td style="padding:10px;font-weight:bold">👨‍⚕️ Bác sĩ</td><td style="padding:10px">{pract_name}</td></tr>
      <tr style="background:#f4f4f4"><td style="padding:10px;font-weight:bold">🔖 Mã lịch</td><td style="padding:10px;font-family:monospace">{booking_code}</td></tr>
      <tr><td style="padding:10px;font-weight:bold">🔢 Số thứ tự</td><td style="padding:10px">{queue_number}</td></tr>
    </table>
    <div style="background:#fff3cd;border-left:4px solid #ffc107;padding:12px;margin:16px 0;border-radius:4px">
      <strong>⚠️ Lưu ý:</strong>
      <ul style="margin:8px 0;padding-left:20px">
        <li>Vui lòng đến trước giờ hẹn <strong>15 phút</strong></li>
        <li>Mang theo <strong>CCCD/BHYT</strong> và hồ sơ bệnh án (nếu có)</li>
        <li>Hủy/đổi lịch: <strong>0243.868.6868</strong></li>
      </ul>
    </div>
    <p style="color:#666;font-size:13px">Email này được gửi tự động. Vui lòng không reply.</p>
  </div>
</body></html>"""
                msg = MIMEMultipart("alternative")
                msg["From"] = f"{from_name} <{gmail_user}>"
                msg["To"] = patient_email
                msg["Subject"] = subject
                msg.attach(MIMEText(html, "html", "utf-8"))
                with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as srv:
                    srv.ehlo(); srv.starttls()
                    srv.login(gmail_user, gmail_pass)
                    srv.sendmail(gmail_user, [patient_email], msg.as_string())
                result["email_sent"] = True
                result["email_to"] = patient_email
        except Exception as e:
            result["email_error"] = str(e)

    return result


def dept_name_short_code(service_type: list) -> str:
    """Pick the department code from serviceType for display."""
    if not service_type or not isinstance(service_type[0], dict):
        return "APT"
    coding = (service_type[0].get("concept") or {}).get("coding") or [{}]
    return (coding[0] or {}).get("code", "APT") or "APT"
