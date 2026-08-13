"""Tool: lấy danh sách lịch hẹn của bác sĩ theo khoảng ngày."""

import httpx, os
from datetime import date, timedelta

TOOL_NAME   = "fhir_get_doctor_schedule"
CATEGORY    = "Healthcare"
DESCRIPTION = (
    "Lấy danh sách lịch hẹn của một bác sĩ (practitioner) theo khoảng thời gian. "
    "Dùng khi bác sĩ hỏi 'tuần này tôi có lịch gì', 'hôm nay tôi khám bao nhiêu người', "
    "'lịch của tôi từ ngày X đến ngày Y', v.v."
)
ARGS_SCHEMA = {
    "practitioner_id": "ID của bác sĩ (Practitioner resource ID trong FHIR). Bắt buộc.",
    "date_from":       "Ngày bắt đầu, định dạng YYYY-MM-DD. Mặc định: hôm nay.",
    "date_to":         "Ngày kết thúc, định dạng YYYY-MM-DD. Mặc định: hôm nay + 7 ngày.",
}


def _patient_name(p: dict) -> str:
    nm = (p.get("name") or [{}])[0]
    return f"{nm.get('family', '')} {' '.join(nm.get('given') or [])}".strip()


def _entries(bundle: dict, rtype: str):
    return [
        e["resource"] for e in (bundle.get("entry") or [])
        if e.get("resource", {}).get("resourceType") == rtype
    ]


def run(args: dict) -> dict:
    prac_id = args.get("practitioner_id", "").strip()
    if not prac_id:
        return {"error": "Thiếu practitioner_id"}

    today  = date.today()
    d_from = args.get("date_from") or str(today)
    d_to   = args.get("date_to")   or str(today + timedelta(days=7))

    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
    from _aidbox_client import _config
    url, cid, sec = _config()
    auth = (cid, sec) if cid and sec else None
    if not url:
        return {"error": "AIDBOX_URL chưa được cấu hình"}

    # Dùng list of tuples để truyền 2 tham số date (duplicate key)
    params = [
        ("actor",  f"Practitioner/{prac_id}"),  #lich hẹn của bác sĩ này
        ("date",   f"ge{d_from}T00:00:00"),  # ngày bắt đầu
        ("date",   f"le{d_to}T23:59:59"),  # ngày kết thúc  ge/le (greater/less-equal
        ("_sort",  "date"),
        ("_count", "100"),
    ]

    try:
        with httpx.Client(timeout=15, auth=auth) as client:
            r = client.get(f"{url}/fhir/Appointment", params=params)
        if r.status_code >= 400:
            return {"error": f"FHIR {r.status_code}: {r.text[:300]}"}
        bundle = r.json()
    except Exception as e:
        return {"error": str(e)}

    appointments = _entries(bundle, "Appointment")
    if not appointments:
        return {
            "total": 0,
            "appointments": [],
            "message": f"Không có lịch hẹn từ {d_from} đến {d_to}.",
        }

    # Batch-fetch tên bệnh nhân
    patient_ids = set()
    for appt in appointments:
        for part in appt.get("participant") or []:
            ref = (part.get("actor") or {}).get("reference", "")
            if ref.startswith("Patient/"):
                patient_ids.add(ref.split("/")[1])

    p_names = {}  # type: dict
    if patient_ids:  #gom tất cả ID bệnh nhân trong danh sách lịch hẹn, fetch 1 lần để giảm số request
        try:
            with httpx.Client(timeout=15, auth=auth) as client:
                r2 = client.get(
                    f"{url}/fhir/Patient",
                    params={"_id": ",".join(patient_ids), "_count": "100"}, # fetch tất cả bệnh nhân trong 1 request
                )
            for p in _entries(r2.json(), "Patient"):
                p_names[p["id"]] = _patient_name(p)
        except Exception:
            pass

    rows = [] #tra về danh sách lịch hẹn với thông tin bệnh nhân, phòng ban, thời gian, trạng thái với dữ liệu dễ trình baỳ
    for appt in appointments:
        patient_name = ""
        for part in appt.get("participant") or []:
            ref = (part.get("actor") or {}).get("reference", "")
            if ref.startswith("Patient/"):
                patient_name = p_names.get(ref.split("/")[1], "")

        st     = (appt.get("serviceType") or [{}])[0]
        coding = ((st.get("concept") or {}).get("coding") or [{}])[0]
        dept   = coding.get("display", coding.get("code", ""))

        start  = (appt.get("start") or "")[:16].replace("T", " ")
        rows.append({
            "start":        start,
            "patient_name": patient_name,
            "department":   dept,
            "status":       appt.get("status", ""),
        })

    return {
        "total":        len(rows),
        "date_from":    d_from,
        "date_to":      d_to,
        "appointments": rows,
    }
