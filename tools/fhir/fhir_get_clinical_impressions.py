"""Lấy ghi chú lâm sàng (ClinicalImpression) của bệnh nhân sau mỗi lần khám."""
from __future__ import annotations

TOOL_NAME = "fhir_get_clinical_impressions"
CATEGORY = "Healthcare"
DESCRIPTION = (
    "Lấy lịch sử ghi chú lâm sàng của bệnh nhân sau mỗi lần khám "
    "(chẩn đoán sơ bộ, ghi chú, kế hoạch tái khám). "
    "Dùng khi bệnh nhân hỏi 'bác sĩ dặn tôi gì?', 'lần khám trước kết luận gì?', "
    "hoặc bác sĩ muốn xem lại ghi chú của các lần khám trước. "
    "Input: patient_id (bắt buộc)."
)
ARGS_SCHEMA = {
    "patient_id": "string — ID bệnh nhân (lấy từ fhir_search_patient hoặc context hiện tại)",
    "count":      "number (tùy chọn) — số ghi chú cần lấy, mặc định 5",
}


def run(args: dict) -> dict:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
    from _aidbox_client import _config
    import httpx
    

    pid = str(args.get("patient_id") or "").strip()
    if not pid:
        return {"error": "patient_id is required"}

    count = int(args.get("count") or 5)

    url, cid, sec = _config()
    if not url:
        return {"error": "AIDBOX_URL not configured"}
    auth = (cid, sec) if cid and sec else None

    with httpx.Client(timeout=15, auth=auth) as client:
        r = client.get(f"{url}/fhir/ClinicalImpression", params={
            "subject": f"Patient/{pid}",
            "_sort":   "-date",
            "_count":  str(count),
        })
        if r.status_code >= 400:
            return {"error": f"Lỗi FHIR HTTP {r.status_code}"}

        entries = r.json().get("entry") or []

    if not entries:
        return {
            "found": False,
            "message": "Chưa có ghi chú lâm sàng nào cho bệnh nhân này.",
        }

    impressions = []
    for e in entries:
        ci = e["resource"]
        notes_raw = ci.get("note") or []
        note_text = ""
        plan_text = ""
        for n in notes_raw:
            t = n.get("text", "")
            if t.startswith("__plan__:"):
                plan_text = t[len("__plan__:"):]
            else:
                note_text = t

        date_str = (ci.get("date") or "")[:10]
        performer = (ci.get("performer") or {}).get("reference", "")

        impressions.append({
            "date":      date_str,
            "diagnosis": ci.get("description", ""),
            "notes":     note_text,
            "plan":      plan_text,
            "doctor":    performer,
        })

    return {
        "found":       True,
        "total":       len(impressions),
        "impressions": impressions,
    }
