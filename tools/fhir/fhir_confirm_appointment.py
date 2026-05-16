"""Confirm a proposed appointment: set status=booked and send confirmation email."""

TOOL_NAME = "fhir_confirm_appointment"
CATEGORY = "Healthcare"
DESCRIPTION = (
    "Bác sĩ xác nhận lịch hẹn đang chờ (status=proposed → booked). "
    "Tự động gửi email xác nhận đến bệnh nhân nếu có email. "
    "Input: appointment_id (lấy từ fhir_get_pending_appointments)."
)
ARGS_SCHEMA = {
    "appointment_id": "string — ID của Appointment cần xác nhận",
}

SETTINGS_KEYS = ["gmail_user", "gmail_app_password", "gmail_from_name"]


def run(args: dict) -> dict:
    import sys, os, smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
    from _aidbox_client import _config
    import httpx

    appt_id = str(args.get("appointment_id") or "").strip()
    if not appt_id:
        return {"error": "appointment_id is required"}

    url, cid, sec = _config()
    auth = (cid, sec) if cid and sec else None

    cfg = args.get("_settings") or {}
    gmail_user = (cfg.get("gmail_user") or "").strip()
    gmail_pass = (cfg.get("gmail_app_password") or "").strip()
    from_name = (cfg.get("gmail_from_name") or "Bệnh viện Đa khoa Hà Nội").strip()

    with httpx.Client(timeout=15, auth=auth) as client:
        r = client.get(f"{url}/fhir/Appointment/{appt_id}")
        if r.status_code != 200:
            return {"error": f"Không tìm thấy lịch hẹn {appt_id}"}
        appt = r.json()
        if appt.get("status") != "proposed":
            return {"error": f"Lịch này không ở trạng thái chờ xác nhận (status={appt.get('status')})"}

        # Update status to booked
        appt["status"] = "booked"
        r2 = client.put(f"{url}/fhir/Appointment/{appt_id}", json=appt)
        if not (200 <= r2.status_code < 300):
            return {"error": f"Cập nhật thất bại (HTTP {r2.status_code})"}

        # Extract info for email
        start = appt.get("start", "")
        date_vi = start[8:10] + "/" + start[5:7] + "/" + start[:4] if start else "N/A"
        time_str = start[11:16] if start else "N/A"

        patient_name = "Bệnh nhân"
        patient_email = ""
        dept_name = "N/A"
        pract_name = "Bác sĩ phụ trách"
        booking_code = appt_id[:8].upper()

        for p in (appt.get("participant") or []):
            actor = p.get("actor") or {}
            ref = actor.get("reference", "")
            if ref.startswith("Patient/"):
                pr = client.get(f"{url}/fhir/{ref}")
                if pr.status_code == 200:
                    nm = (pr.json().get("name") or [{}])[0]
                    patient_name = f"{nm.get('family','')} {' '.join(nm.get('given',[]))}".strip()
            elif ref.startswith("Practitioner/"):
                pr = client.get(f"{url}/fhir/{ref}")
                if pr.status_code == 200:
                    nm = (pr.json().get("name") or [{}])[0]
                    pract_name = f"BS. {nm.get('family','')} {' '.join(nm.get('given',[]))}".strip()

        stype = appt.get("serviceType") or []
        if stype:
            coding = (stype[0].get("concept") or {}).get("coding") or [{}]
            dept_name = coding[0].get("display", "N/A")

        for note in (appt.get("note") or []):
            text = note.get("text", "")
            if text.startswith("__patient_email__:"):
                patient_email = text.replace("__patient_email__:", "").strip()

        # Send email
        email_sent = False
        email_error = None
        if patient_email and gmail_user and gmail_pass:
            try:
                subject = f"✅ Lịch khám đã được xác nhận - {dept_name} - {date_vi} {time_str}"
                html = f"""<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:20px">
  <div style="background:#0f62fe;color:white;padding:20px;border-radius:8px 8px 0 0">
    <h2 style="margin:0">🏥 Bệnh viện Đa khoa Hà Nội</h2>
    <p style="margin:4px 0 0">Xác nhận lịch khám</p>
  </div>
  <div style="border:1px solid #e0e0e0;border-top:none;padding:24px;border-radius:0 0 8px 8px">
    <p>Xin chào <strong>{patient_name}</strong>,</p>
    <p>Bác sĩ đã xác nhận lịch khám của bạn:</p>
    <table style="width:100%;border-collapse:collapse;margin:16px 0">
      <tr style="background:#f4f4f4"><td style="padding:10px;font-weight:bold;width:40%">📅 Ngày khám</td><td style="padding:10px">{date_vi}</td></tr>
      <tr><td style="padding:10px;font-weight:bold">⏰ Giờ khám</td><td style="padding:10px">{time_str}</td></tr>
      <tr style="background:#f4f4f4"><td style="padding:10px;font-weight:bold">🏥 Khoa</td><td style="padding:10px">{dept_name}</td></tr>
      <tr><td style="padding:10px;font-weight:bold">👨‍⚕️ Bác sĩ</td><td style="padding:10px">{pract_name}</td></tr>
      <tr style="background:#f4f4f4"><td style="padding:10px;font-weight:bold">🔖 Mã lịch</td><td style="padding:10px;font-family:monospace">{booking_code}</td></tr>
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
                email_sent = True
            except Exception as e:
                email_error = str(e)

    result = {
        "success": True,
        "appointment_id": appt_id,
        "status": "booked",
        "patient_name": patient_name,
        "department": dept_name,
        "date": date_vi,
        "time": time_str,
        "message": f"Đã xác nhận lịch khám cho {patient_name} — {dept_name} {date_vi} lúc {time_str}.",
    }
    if email_sent:
        result["email_sent"] = True
        result["email_to"] = patient_email
    elif patient_email and not email_sent:
        result["email_error"] = email_error
    return result
