"""Gửi email tóm tắt lần khám cho bệnh nhân.

Bao gồm: chẩn đoán + ghi chú + kế hoạch tái khám + đơn thuốc (nếu có).
Gọi sau khi bác sĩ "Kết thúc khám" trên UI.
"""
from __future__ import annotations

TOOL_NAME = "fhir_send_visit_summary"
CATEGORY  = "Healthcare"
DESCRIPTION = (
    "Gửi email tóm tắt lần khám cho bệnh nhân (chẩn đoán + đơn thuốc + kế hoạch). "
    "Gọi sau khi bác sĩ kết thúc khám và lưu ClinicalImpression."
)
ARGS_SCHEMA = {
    "patient_email":    "string — Email bệnh nhân. BẮT BUỘC.",
    "patient_name":     "string — Tên BN. Tùy chọn.",
    "visit_date":       "string — Ngày khám (YYYY-MM-DD). Tùy chọn, mặc định hôm nay.",
    "diagnosis":        "string — Chẩn đoán. BẮT BUỘC.",
    "notes":            "string — Ghi chú lâm sàng. Tùy chọn.",
    "plan":             "string — Kế hoạch/tái khám. Tùy chọn.",
    "medications":      "list[dict] — Danh sách thuốc: [{drug_name, instruction}]. Tùy chọn.",
    "practitioner_name":"string — Tên bác sĩ. Tùy chọn.",
}

SETTINGS_KEYS = ["gmail_user", "gmail_app_password", "gmail_from_name"]


def _format_date_vi(date_str: str) -> str:
    if not date_str or len(date_str) < 10:
        return "—"
    try:
        y, m, d = date_str[:10].split("-")
        return f"{d}/{m}/{y}"
    except Exception:
        return date_str


def run(args: dict) -> dict:
    import smtplib
    from datetime import date
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    patient_email = str(args.get("patient_email") or "").strip()
    if not patient_email:
        return {"error": "patient_email là bắt buộc"}

    diagnosis = str(args.get("diagnosis") or "").strip()
    if not diagnosis:
        return {"error": "diagnosis là bắt buộc"}

    cfg: dict = args.get("_settings") or {}
    gmail_user = (cfg.get("gmail_user") or "").strip()
    gmail_pass = (cfg.get("gmail_app_password") or "").strip()
    from_name  = (cfg.get("gmail_from_name") or "Bệnh viện Đa khoa Hà Nội").strip()

    if not gmail_user or not gmail_pass:
        return {"error": "Gmail chưa được cấu hình (GMAIL_USER / GMAIL_APP_PASSWORD)."}

    patient_name      = str(args.get("patient_name") or "Bệnh nhân").strip()
    notes             = str(args.get("notes") or "").strip()
    plan              = str(args.get("plan") or "").strip()
    practitioner_name = str(args.get("practitioner_name") or "").strip()
    visit_date        = str(args.get("visit_date") or "").strip()
    if not visit_date:
        visit_date = date.today().isoformat()
    visit_date_vi = _format_date_vi(visit_date)

    medications = args.get("medications") or []
    if not isinstance(medications, list):
        medications = []

    # ── Build medication HTML rows ──
    if medications:
        med_rows_html = "".join(
            f"""<tr>
                <td style="padding:8px 12px;border-bottom:1px solid #e0e0e0;font-weight:600">{m.get('drug_name','')}</td>
                <td style="padding:8px 12px;border-bottom:1px solid #e0e0e0">{m.get('instruction','')}</td>
            </tr>"""
            for m in medications
        )
        med_section = f"""
        <h3 style="color:#0f62fe;margin:24px 0 8px;font-size:15px">💊 Đơn thuốc</h3>
        <table style="width:100%;border-collapse:collapse;border:1px solid #e0e0e0">
          <thead>
            <tr style="background:#f4f4f4">
              <th style="padding:8px 12px;text-align:left;font-size:13px">Thuốc</th>
              <th style="padding:8px 12px;text-align:left;font-size:13px">Cách dùng</th>
            </tr>
          </thead>
          <tbody>{med_rows_html}</tbody>
        </table>
        <p style="color:#856404;background:#fff3cd;border-left:4px solid #ffc107;padding:10px 12px;margin-top:8px;font-size:13px">
          ⚠ Vui lòng dùng thuốc đúng liều theo chỉ định. Nếu có dấu hiệu bất thường, liên hệ lại với bác sĩ ngay.
        </p>
        """
    else:
        med_section = ""

    # ── Notes/Plan sections ──
    notes_html = f"""
        <h3 style="color:#0f62fe;margin:20px 0 6px;font-size:15px">📝 Ghi chú lâm sàng</h3>
        <p style="margin:0;color:#333;line-height:1.5;white-space:pre-line">{notes}</p>
    """ if notes else ""

    plan_html = f"""
        <h3 style="color:#0f62fe;margin:20px 0 6px;font-size:15px">📅 Kế hoạch / Tái khám</h3>
        <p style="margin:0;color:#333;line-height:1.5">{plan}</p>
    """ if plan else ""

    practitioner_html = f"""
        <p style="text-align:right;color:#666;font-size:13px;margin-top:24px">
          — <strong>{practitioner_name}</strong>
        </p>
    """ if practitioner_name else ""

    subject = f"📋 Tóm tắt khám {visit_date_vi} — {diagnosis[:60]}"

    body_html = f"""
<html><body style="font-family:Arial,sans-serif;max-width:640px;margin:auto;padding:20px;color:#222">
  <div style="background:#0f62fe;color:white;padding:20px;border-radius:8px 8px 0 0">
    <h2 style="margin:0">🏥 Bệnh viện Đa khoa Hà Nội</h2>
    <p style="margin:4px 0 0">Tóm tắt lần khám — {visit_date_vi}</p>
  </div>
  <div style="border:1px solid #e0e0e0;border-top:none;padding:24px;border-radius:0 0 8px 8px">
    <p>Xin chào <strong>{patient_name}</strong>,</p>
    <p>Sau lần khám ngày <strong>{visit_date_vi}</strong>, bác sĩ ghi nhận kết quả như sau:</p>

    <h3 style="color:#0f62fe;margin:20px 0 6px;font-size:15px">🩺 Chẩn đoán</h3>
    <p style="margin:0;color:#333;line-height:1.5;font-weight:600">{diagnosis}</p>

    {notes_html}
    {plan_html}
    {med_section}

    {practitioner_html}

    <div style="margin-top:24px;padding:12px;background:#f4f4f4;border-radius:4px;font-size:12px;color:#666">
      Email này được gửi tự động sau khi bác sĩ hoàn tất khám. Vui lòng không reply.
      Nếu cần hỗ trợ, liên hệ <strong>0243.868.6868</strong>.
    </div>
  </div>
</body></html>
"""

    try:
        msg = MIMEMultipart("alternative")
        msg["From"]    = f"{from_name} <{gmail_user}>"
        msg["To"]      = patient_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, [patient_email], msg.as_string())

        return {
            "success":  True,
            "sent_to":  patient_email,
            "subject":  subject,
            "med_count": len(medications),
            "message":  f"Đã gửi tóm tắt lần khám tới {patient_email}",
        }
    except Exception as e:
        return {"error": f"Gửi email thất bại: {e}"}
