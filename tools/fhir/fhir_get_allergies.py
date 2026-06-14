"""Lấy danh sách dị ứng của bệnh nhân từ HIS (FHIR AllergyIntolerance).

Dùng khi:
  - Hiển thị section "DỊ ỨNG" trong panel hồ sơ BN
  - Trước khi kê đơn thuốc → check dị ứng tự động
  - Bác sĩ hỏi "BN X có dị ứng gì không"
"""
from __future__ import annotations

TOOL_NAME = "fhir_get_allergies"
CATEGORY  = "Healthcare"
DESCRIPTION = (
    "Lấy danh sách dị ứng đã ghi nhận của bệnh nhân từ HIS (FHIR AllergyIntolerance). "
    "Bao gồm dị ứng thuốc, thực phẩm, môi trường."
)
ARGS_SCHEMA = {
    "patient_id":   "string — ID bệnh nhân. BẮT BUỘC.",
    "active_only":  "boolean — chỉ lấy dị ứng đang active (mặc định True).",
}

_SEVERITY_VI = {
    "mild":     "Nhẹ",
    "moderate": "Vừa",
    "severe":   "Nặng",
}

_CATEGORY_VI = {
    "medication":  "Thuốc",
    "food":        "Thực phẩm",
    "environment": "Môi trường",
    "biologic":    "Sinh phẩm",
}


def run(args: dict) -> dict:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
    from _aidbox_client import fhir_get, extract_entries

    pid = str(args.get("patient_id") or "").strip()
    if not pid:
        return {"error": "patient_id là bắt buộc"}

    active_only = args.get("active_only")
    if active_only is None:
        active_only = True

    params = {
        "patient": f"Patient/{pid}",
        "_count": "50",
        "_sort": "-_lastUpdated",
    }

    bundle = fhir_get("AllergyIntolerance", params)
    if "error" in bundle:
        return bundle

    entries = extract_entries(bundle)
    allergies: list[dict] = []

    for a in entries:
        # Filter active
        if active_only:
            clinical = (((a.get("clinicalStatus") or {}).get("coding") or [{}])[0]).get("code", "")
            if clinical and clinical != "active":
                continue

        verification = (((a.get("verificationStatus") or {}).get("coding") or [{}])[0]).get("code", "")
        if verification == "entered-in-error":
            continue

        # Substance — lấy từ code.text hoặc display
        code_obj = a.get("code") or {}
        substance = code_obj.get("text") or ""
        if not substance:
            coding = (code_obj.get("coding") or [{}])[0]
            substance = coding.get("display") or coding.get("code") or "(không rõ)"

        # Category (list)
        categories = a.get("category") or []
        category = categories[0] if categories else "medication"

        # Criticality
        criticality = a.get("criticality") or ""

        # Reaction[0] — manifestation + severity
        reaction_text = ""
        reaction_severity = ""
        reactions = a.get("reaction") or []
        if reactions:
            r0 = reactions[0]
            manifestations = r0.get("manifestation") or []
            if manifestations:
                m0 = manifestations[0]
                concept = m0.get("concept") or {}
                reaction_text = concept.get("text") or ""
                if not reaction_text:
                    c0 = (concept.get("coding") or [{}])[0]
                    reaction_text = c0.get("display") or ""
            reaction_severity = r0.get("severity") or ""

        recorded = (a.get("recordedDate") or "")[:10]
        onset    = (a.get("onsetDateTime") or "")[:10]

        allergies.append({
            "id":               a.get("id"),
            "substance":        substance,
            "category":         category,
            "category_vi":      _CATEGORY_VI.get(category, category),
            "criticality":      criticality,
            "verification":     verification,
            "severity":         reaction_severity,
            "severity_vi":      _SEVERITY_VI.get(reaction_severity, ""),
            "reaction":         reaction_text or None,
            "onset_date":       onset or None,
            "recorded_date":    recorded or None,
        })

    # Summary text
    if not allergies:
        summary = "BN chưa ghi nhận dị ứng nào."
    else:
        high_crit = [a for a in allergies if a["criticality"] == "high"]
        summary_parts = []
        if high_crit:
            names = ", ".join(a["substance"] for a in high_crit)
            summary_parts.append(f"🚨 Dị ứng nặng: {names}")
        other = [a for a in allergies if a["criticality"] != "high"]
        if other:
            names = ", ".join(a["substance"] for a in other)
            summary_parts.append(f"Dị ứng khác: {names}")
        summary = " · ".join(summary_parts)

    return {
        "patient_id": pid,
        "count":      len(allergies),
        "allergies":  allergies,
        "summary":    summary,
    }
