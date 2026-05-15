"""Send appointment confirmation email to patient after booking."""

TOOL_NAME = "fhir_send_appointment_confirmation"
CATEGORY = "Healthcare"
DESCRIPTION = (
    "Gửi email xác nhận lịch khám cho bệnh nhân sau khi đặt lịch thành công. "
    "Input: appointment_id + patient_email. "
    "Đọc thông tin lịch từ Aidbox → gửi email HTML qua Gmail connector. "
    "Gọi sau fhir_create_appointment."
)
ARGS_SCHEMA = {
    "appointment_id": "string — ID của Appointment vừa tạo",
    "patient_email": "string — email của bệnh nhân để gửi xác nhận",
}

SETTINGS_KEYS = ["gmail_user", "gmail_app_password", "gmail_from_name"]


def run(args: dict) -> dict:
    import sys, os, smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    sys.path.insert(0, os.path.dirname(__file__))
    from _aidbox_client import fhir_get, extract_entries

    appt_id = str(args.get("appointment_id") or "").strip()
    patient_email = str(args.get("patient_email") or "").strip()

    if not appt_id:
        return {"error": "appointment_id is required"}
    if not patient_email:
        return {"error": "patient_email is required"}

    # Gmail credentials from connector
    cfg: dict = args.get("_settings") or {}
    gmail_user = (cfg.get("gmail_user") or "").strip()
    gmail_pass = (cfg.get("gmail_app_password") or "").strip()
    from_name = (cfg.get("gmail_from_name") or "Bệnh viện Đa khoa Hà Nội").strip()

    if not gmail_user or not gmail_pass:
        return {"error": "Gmail chưa được cấu hình. Vào Connectors → Gmail để thiết lập."}

    # Fetch appointment from Aidbox
    appt = fhir_get(f"Appointment/{appt_id}")
    if not appt or appt.get("resourceType") != "Appointment":
        return {"error": f"Không tìm thấy lịch hẹn {appt_id}"}

    # Extract appointment details
    start = appt.get("start", "")
    date_str = start[8:10] + "/" + start[5:7] + "/" + start[:4] if start else "N/A"
    time_str = start[11:16] if start else "N/A"

    dept_name = "N/A"
    doctor_name = "N/A"

    participants = appt.get("participant") or []
    for p in participants:
        actor = p.get("actor") or {}
        ref = actor.get("reference", "")
        if ref.startswith("Practitioner/"):
            pract = fhir_get(ref)
            if isinstance(pract, dict) and pract.get("name"):
                name = pract["name"][0]
                given = " ".join(name.get("given") or [])
                doctor_name = f"BS. {name.get('family', '')} {given}".strip()

    service_type = appt.get("serviceType") or []
    if service_type:
        coding = (service_type[0].get("concept") or {}).get("coding") or [{}]
        dept_name = coding[0].get("display", "N/A")

    # Build email
    subject = f"✅ Xác nhận lịch khám - {dept_name} - {date_str} {time_str}"
    body_html = f"""
<html><body style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px;">
  <div style="background: #0f62fe; color: white; padding: 20px; border-radius: 8px 8px 0 0;">
    <h2 style="margin:0">🏥 Bệnh viện Đa khoa Hà Nội</h2>
    <p style="margin:4px 0 0">Xác nhận lịch khám</p>
  </div>
  <div style="border: 1px solid #e0e0e0; border-top: none; padding: 24px; border-radius: 0 0 8px 8px;">
    <p>Xin chào,</p>
    <p>Lịch khám của bạn đã được xác nhận thành công:</p>
    <table style="width:100%; border-collapse: collapse; margin: 16px 0;">
      <tr style="background:#f4f4f4">
        <td style="padding:10px; font-weight:bold; width:40%">📅 Ngày khám</td>
        <td style="padding:10px">{date_str}</td>
      </tr>
      <tr>
        <td style="padding:10px; font-weight:bold">⏰ Giờ khám</td>
        <td style="padding:10px">{time_str}</td>
      </tr>
      <tr style="background:#f4f4f4">
        <td style="padding:10px; font-weight:bold">🏥 Khoa</td>
        <td style="padding:10px">{dept_name}</td>
      </tr>
      <tr>
        <td style="padding:10px; font-weight:bold">👨‍⚕️ Bác sĩ</td>
        <td style="padding:10px">{doctor_name}</td>
      </tr>
      <tr style="background:#f4f4f4">
        <td style="padding:10px; font-weight:bold">🔖 Mã lịch</td>
        <td style="padding:10px; font-family:monospace">{appt_id[:8].upper()}</td>
      </tr>
    </table>
    <div style="background:#fff3cd; border-left: 4px solid #ffc107; padding:12px; margin:16px 0; border-radius:4px">
      <strong>⚠️ Lưu ý:</strong>
      <ul style="margin:8px 0; padding-left:20px">
        <li>Vui lòng đến trước giờ hẹn <strong>15 phút</strong></li>
        <li>Mang theo <strong>CCCD/BHYT</strong> và hồ sơ bệnh án (nếu có)</li>
        <li>Nếu cần hủy/đổi lịch, liên hệ: <strong>0243.868.6868</strong></li>
      </ul>
    </div>
    <p style="color:#666; font-size:13px">Email này được gửi tự động. Vui lòng không reply.</p>
  </div>
</body></html>
"""

    # Send via Gmail SMTP
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{from_name} <{gmail_user}>"
        msg["To"] = patient_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, [patient_email], msg.as_string())

        return {
            "success": True,
            "sent_to": patient_email,
            "subject": subject,
            "appointment_id": appt_id,
            "message": f"Đã gửi email xác nhận lịch khám đến {patient_email}",
        }
    except Exception as e:
        return {"error": f"Gửi email thất bại: {e}"}
