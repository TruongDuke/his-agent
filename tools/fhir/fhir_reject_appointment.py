"""Reject a proposed appointment: set status=cancelled."""

TOOL_NAME = "fhir_reject_appointment"
CATEGORY = "Healthcare"
DESCRIPTION = (
    "Bác sĩ từ chối lịch hẹn đang chờ (status=proposed → cancelled). "
    "Input: appointment_id và reason (lý do từ chối, tùy chọn)."
)
ARGS_SCHEMA = {
    "appointment_id": "string — ID của Appointment cần từ chối",
    "reason":         "string (tùy chọn) — lý do từ chối để ghi chú",
}

SETTINGS_KEYS = ["gmail_user", "gmail_app_password", "gmail_from_name"]


def run(args: dict) -> dict:
    import sys, os, smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
    from _aidbox_client import _config
    import httpx

    cfg = args.get("_settings") or {}
    gmail_user = (cfg.get("gmail_user") or "").strip()
    gmail_pass = (cfg.get("gmail_app_password") or "").strip()
    from_name = (cfg.get("gmail_from_name") or "Bệnh viện Đa khoa Hà Nội").strip()

    appt_id = str(args.get("appointment_id") or "").strip()
    reason = str(args.get("reason") or "Bác sĩ từ chối lịch hẹn").strip()
    if not appt_id:
        return {"error": "appointment_id is required"}

    url, cid, sec = _config()
    auth = (cid, sec) if cid and sec else None

    with httpx.Client(timeout=15, auth=auth) as client:
        r = client.get(f"{url}/fhir/Appointment/{appt_id}")
        if r.status_code != 200:
            return {"error": f"Không tìm thấy lịch hẹn {appt_id}"}
        appt = r.json()
        if appt.get("status") != "proposed":
            return {"error": f"Lịch này không ở trạng thái chờ xác nhận (status={appt.get('status')})"}

        # Cancel appointment — R5 dùng "cancellationReason" (2 chữ l), R4 mới là "cancelationReason".
        # Sai chính tả → Aidbox trả 422 unknown-key và toàn bộ thao tác từ chối hỏng.
        appt["status"] = "cancelled"
        appt["cancellationReason"] = {"text": reason}

        r2 = client.put(f"{url}/fhir/Appointment/{appt_id}", json=appt)
        if not (200 <= r2.status_code < 300):
            return {"error": f"Cập nhật thất bại (HTTP {r2.status_code})"}

        # Free the slot back — chỉ làm SAU khi hủy lịch thành công. Nếu giải phóng trước mà PUT lỗi
        # thì slot trống nhưng lịch vẫn "proposed" → người khác đặt trùng vào slot đó.
        slot_ref = ((appt.get("slot") or [{}])[0] or {}).get("reference", "")
        if slot_ref:
            rs = client.get(f"{url}/fhir/{slot_ref}")
            if rs.status_code == 200:
                slot = rs.json()
                slot["status"] = "free"
                client.put(f"{url}/fhir/{slot_ref}", json=slot)

        patient_name = "Bệnh nhân"
        for p in (appt.get("participant") or []):
            ref = (p.get("actor") or {}).get("reference", "")
            if ref.startswith("Patient/"):
                pr = client.get(f"{url}/fhir/{ref}")
                if pr.status_code == 200:
                    nm = (pr.json().get("name") or [{}])[0]
                    patient_name = f"{nm.get('family','')} {' '.join(nm.get('given',[]))}".strip()

        # Thông tin dựng email
        start = appt.get("start", "")
        date_vi = start[8:10] + "/" + start[5:7] + "/" + start[:4] if start else "N/A"
        time_str = start[11:16] if start else "N/A"
        stype = appt.get("serviceType") or []
        dept_name = "N/A"
        if stype:
            coding = (stype[0].get("concept") or {}).get("coding") or [{}]
            dept_name = coding[0].get("display", "N/A")

        patient_email = ""
        for note in (appt.get("note") or []):
            t = note.get("text", "")
            if t.startswith("__patient_email__:"):
                patient_email = t.replace("__patient_email__:", "").strip()

    # ── Báo cho bệnh nhân ──
    # Xác nhận thì có email, từ chối thì trước đây im lặng — bệnh nhân ngồi chờ mãi
    # không biết lịch đã bị hủy, tới ngày vẫn đến viện. Hủy lịch càng phải báo.
    email_sent = False
    email_error = None
    if patient_email and gmail_user and gmail_pass:
        try:
            html = f"""<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:20px">
  <div style="background:#a2191f;color:white;padding:20px;border-radius:8px 8px 0 0">
    <h2 style="margin:0">🏥 Bệnh viện Đa khoa Hà Nội</h2>
    <p style="margin:4px 0 0">Lịch khám không được duyệt</p>
  </div>
  <div style="border:1px solid #e0e0e0;border-top:none;padding:24px;border-radius:0 0 8px 8px">
    <p>Xin chào <strong>{patient_name}</strong>,</p>
    <p>Rất tiếc, lịch khám của bạn <strong>chưa được bác sĩ duyệt</strong> nên đã bị hủy:</p>
    <table style="width:100%;border-collapse:collapse;margin:16px 0">
      <tr style="background:#f4f4f4"><td style="padding:10px;font-weight:bold;width:40%">📅 Ngày khám</td><td style="padding:10px">{date_vi}</td></tr>
      <tr><td style="padding:10px;font-weight:bold">⏰ Giờ khám</td><td style="padding:10px">{time_str}</td></tr>
      <tr style="background:#f4f4f4"><td style="padding:10px;font-weight:bold">🏥 Khoa</td><td style="padding:10px">{dept_name}</td></tr>
      <tr><td style="padding:10px;font-weight:bold">📝 Lý do</td><td style="padding:10px">{reason}</td></tr>
    </table>
    <div style="background:#e8f4f8;border-left:4px solid #0f62fe;padding:12px;margin:16px 0;border-radius:4px">
      <strong>Bạn có thể đặt lịch khác:</strong>
      <ul style="margin:8px 0;padding-left:20px">
        <li>Đặt lại trên hệ thống — khung giờ này đã được mở lại cho người khác, vui lòng chọn giờ mới</li>
        <li>Hoặc gọi <strong>0243.868.6868</strong> để được hỗ trợ</li>
      </ul>
    </div>
    <p style="color:#666;font-size:13px">Email này được gửi tự động. Vui lòng không reply.</p>
  </div>
</body></html>"""
            msg = MIMEMultipart("alternative")
            msg["From"] = f"{from_name} <{gmail_user}>"
            msg["To"] = patient_email
            msg["Subject"] = f"❌ Lịch khám {date_vi} {time_str} không được duyệt - {dept_name}"
            msg.attach(MIMEText(html, "html", "utf-8"))
            with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as srv:
                srv.ehlo(); srv.starttls()
                srv.login(gmail_user, gmail_pass)
                srv.sendmail(gmail_user, [patient_email], msg.as_string())
            email_sent = True
        except Exception as e:  # noqa: BLE001 — gửi mail hỏng không được làm hỏng việc hủy lịch
            email_error = str(e)

    result = {
        "success": True,
        "appointment_id": appt_id,
        "status": "cancelled",
        "patient_name": patient_name,
        "reason": reason,
        "slot_freed": bool(slot_ref),
        "message": f"Đã từ chối lịch hẹn của {patient_name}. Slot đã được giải phóng.",
    }
    if email_sent:
        result["email_sent"] = True
        result["email_to"] = patient_email
        result["message"] += f" Đã gửi email báo hủy tới {patient_email}."
    elif patient_email:
        result["email_error"] = email_error or "Gmail chưa cấu hình"
        result["message"] += " ⚠ Chưa gửi được email báo cho bệnh nhân."
    else:
        result["message"] += " Lịch này không có email nên không báo được cho bệnh nhân."
    return result
