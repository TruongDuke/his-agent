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


def run(args: dict) -> dict:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
    from _aidbox_client import _config
    import httpx

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

    return {
        "success": True,
        "appointment_id": appt_id,
        "status": "cancelled",
        "patient_name": patient_name,
        "reason": reason,
        "slot_freed": bool(slot_ref),
        "message": f"Đã từ chối lịch hẹn của {patient_name}. Slot đã được giải phóng.",
    }
