"""Tool: hủy lịch hẹn của bệnh nhân."""

import httpx, os
from datetime import date

TOOL_NAME   = "fhir_cancel_appointment"
CATEGORY    = "Healthcare"
DESCRIPTION = (
    "Hủy lịch hẹn (Appointment) của bệnh nhân. "
    "Nếu có appointment_id thì hủy trực tiếp. "
    "Nếu không, tìm lịch hẹn theo patient_id + ngày/khoa rồi hủy. "
    "Chỉ hủy lịch có trạng thái booked hoặc pending."
)
ARGS_SCHEMA = {
    "patient_id":      "ID bệnh nhân (FHIR Patient ID). Bắt buộc trừ khi đã có appointment_id.",
    "appointment_id":  "ID lịch hẹn cụ thể. Nếu biết thì truyền thẳng, bỏ qua tìm kiếm.",
    "date":            "Ngày lịch hẹn cần hủy, định dạng YYYY-MM-DD. Dùng để lọc khi có nhiều lịch.",
    "department":      "Tên hoặc mã khoa (ví dụ: PULMO, Tim Mạch). Dùng để lọc khi có nhiều lịch.",
}


def _entries(bundle: dict, rtype: str):
    return [
        e["resource"] for e in (bundle.get("entry") or [])
        if e.get("resource", {}).get("resourceType") == rtype
    ]


def _dept_display(appt: dict) -> str:
    st = (appt.get("serviceType") or [{}])[0]
    coding = ((st.get("concept") or {}).get("coding") or [{}])[0]
    return coding.get("display", coding.get("code", ""))


def _cancel_one(url: str, auth, appt: dict) -> dict:
    """PATCH appointment status → cancelled, free up slot."""
    appt_id = appt["id"]
    with httpx.Client(timeout=15, auth=auth) as client:
        r = client.patch(
            f"{url}/fhir/Appointment/{appt_id}",
            json={"status": "cancelled"},
            headers={"Content-Type": "application/merge-patch+json"},
        )
        if r.status_code >= 400:
            return {"error": f"Không thể hủy: FHIR {r.status_code}"}

        # Giải phóng slot để người khác có thể đặt lại
        for slot_ref in appt.get("slot") or []:
            ref = slot_ref.get("reference", "")
            if ref.startswith("Slot/"):
                slot_id = ref.split("/")[1]
                client.patch(
                    f"{url}/fhir/Slot/{slot_id}",
                    json={"status": "free"},
                    headers={"Content-Type": "application/merge-patch+json"},
                )

    start = (appt.get("start") or "")[:16].replace("T", " ")
    return {
        "success":       True,
        "appointment_id": appt_id,
        "cancelled_slot": start,
        "department":    _dept_display(appt),
        "message":       f"Đã hủy lịch hẹn {start} — {_dept_display(appt)} thành công.",
    }


def run(args: dict) -> dict:
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
    from _aidbox_client import _config
    url, cid, sec = _config()
    auth = (cid, sec) if cid and sec else None
    if not url:
        return {"error": "AIDBOX_URL chưa được cấu hình"}

    appt_id = args.get("appointment_id", "").strip()

    # ── Hủy trực tiếp theo appointment_id ──
    if appt_id:
        with httpx.Client(timeout=15, auth=auth) as client:
            r = client.get(f"{url}/fhir/Appointment/{appt_id}")
        if r.status_code >= 400:
            return {"error": "Không tìm thấy lịch hẹn với ID này"}
        appt = r.json()
        if appt.get("status") not in ("booked", "pending"):
            return {"error": f"Lịch hẹn đang ở trạng thái '{appt.get('status')}', không thể hủy."}
        return _cancel_one(url, auth, appt)

    # ── Tìm lịch hẹn theo patient_id ──
    patient_id = args.get("patient_id", "").strip()
    if not patient_id:
        return {"error": "Cần cung cấp patient_id hoặc appointment_id"}

    today_str = str(date.today())
    params = [
        ("patient", f"Patient/{patient_id}"),
        ("date",    f"ge{today_str}T00:00:00"),
        ("_sort",   "date"),
        ("_count",  "50"),
    ]
    # Lọc theo ngày cụ thể nếu có
    appt_date = args.get("date", "").strip()
    if appt_date:
        params = [
            ("patient", f"Patient/{patient_id}"),
            ("date",    f"ge{appt_date}T00:00:00"),
            ("date",    f"le{appt_date}T23:59:59"),
            ("_sort",   "date"),
            ("_count",  "50"),
        ]

    try:
        with httpx.Client(timeout=15, auth=auth) as client:
            r = client.get(f"{url}/fhir/Appointment", params=params)
        bundle = r.json()
    except Exception as e:
        return {"error": str(e)}

    all_appts = _entries(bundle, "Appointment")

    # Chỉ lấy lịch có thể hủy
    cancellable = [a for a in all_appts if a.get("status") in ("booked", "pending")]

    if not cancellable:
        return {"error": "Không tìm thấy lịch hẹn sắp tới nào có thể hủy."}

    # Lọc thêm theo khoa nếu có
    dept_filter = args.get("department", "").strip().lower()
    if dept_filter:
        filtered = [a for a in cancellable
                    if dept_filter in _dept_display(a).lower()]
        if filtered:
            cancellable = filtered

    # Đúng 1 lịch → hủy luôn
    if len(cancellable) == 1:
        return _cancel_one(url, auth, cancellable[0])

    # Nhiều lịch → trả về danh sách để agent xác nhận với user
    options = []
    for a in cancellable:
        start = (a.get("start") or "")[:16].replace("T", " ")
        options.append({
            "appointment_id": a["id"],
            "start":          start,
            "department":     _dept_display(a),
            "status":         a.get("status"),
        })
    return {
        "multiple_found": True,
        "count":          len(options),
        "appointments":   options,
        "message":        "Tìm thấy nhiều lịch hẹn. Hỏi bệnh nhân muốn hủy lịch nào.",
    }
