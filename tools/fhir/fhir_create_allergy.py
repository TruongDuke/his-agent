"""Ghi nhận dị ứng của bệnh nhân vào HIS (FHIR AllergyIntolerance R5).

Dùng khi:
  - Bác sĩ/điều dưỡng ghi nhận dị ứng mới của BN (thuốc / thực phẩm / môi trường)
  - BN tự khai dị ứng trong tiền sử

Tuân thủ chuẩn:
  - HL7 FHIR R5 — AllergyIntolerance resource
  - WHO ICSR (Individual Case Safety Report) — severity coding
  - QĐ 1088/QĐ-BYT 2013 — Hướng dẫn theo dõi phản ứng có hại của thuốc
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta

TOOL_NAME = "fhir_create_allergy"
CATEGORY  = "Healthcare"
DESCRIPTION = (
    "Lưu dị ứng của bệnh nhân vào HIS (FHIR AllergyIntolerance R5). "
    "Hỗ trợ dị ứng thuốc, thực phẩm, môi trường. "
    "Sau khi lưu, sẽ tự động dùng để check khi bác sĩ kê đơn thuốc."
)
ARGS_SCHEMA = {
    "patient_id": "string — ID bệnh nhân. BẮT BUỘC.",
    "substance":  (
        "string — Chất gây dị ứng. VD: 'Penicillin', 'Sulfa', 'Tôm cua', 'Phấn hoa'. BẮT BUỘC."
    ),
    "category":   (
        "string — 'medication' | 'food' | 'environment' | 'biologic'. "
        "Mặc định 'medication'."
    ),
    "severity":   (
        "string — 'mild' | 'moderate' | 'severe'. Mặc định 'moderate'. "
        "Mức 'severe' = sốc phản vệ, phù mạch, hội chứng Stevens-Johnson."
    ),
    "reaction":   (
        "string — Mô tả phản ứng. VD: 'Nổi mày đay toàn thân', 'Sốc phản vệ', "
        "'Phù môi'. Tùy chọn."
    ),
    "verification": (
        "string — 'confirmed' (đã xác nhận lâm sàng) | 'unconfirmed' (BN tự khai chưa kiểm chứng). "
        "Mặc định 'unconfirmed'."
    ),
    "onset_date": (
        "string — Ngày phát hiện dị ứng (YYYY-MM-DD). Tùy chọn."
    ),
}

# Map severity tiếng Việt → FHIR severity code
_SEVERITY_MAP = {
    "mild":     ("mild",     "Nhẹ"),
    "moderate": ("moderate", "Vừa"),
    "severe":   ("severe",   "Nặng"),
}

# Criticality = high khi severity=severe (theo FHIR best practice)
_CRITICALITY_MAP = {
    "mild":     "low",
    "moderate": "low",
    "severe":   "high",
}


def run(args: dict) -> dict:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
    from _aidbox_client import fhir_post, fhir_get, patient_summary

    pid = str(args.get("patient_id") or "").strip()
    if not pid:
        return {"error": "patient_id là bắt buộc"}

    substance = str(args.get("substance") or "").strip()
    if not substance:
        return {"error": "substance (chất gây dị ứng) là bắt buộc"}

    category = str(args.get("category") or "medication").strip().lower()
    if category not in ("medication", "food", "environment", "biologic"):
        category = "medication"

    severity_raw = str(args.get("severity") or "moderate").strip().lower()
    severity, severity_vi = _SEVERITY_MAP.get(severity_raw, _SEVERITY_MAP["moderate"])
    criticality = _CRITICALITY_MAP[severity]

    reaction = str(args.get("reaction") or "").strip()

    verification = str(args.get("verification") or "unconfirmed").strip().lower()
    if verification not in ("confirmed", "unconfirmed", "refuted"):
        verification = "unconfirmed"

    onset_date = str(args.get("onset_date") or "").strip()

    # ── Build FHIR AllergyIntolerance ──
    allergy: dict = {
        "resourceType": "AllergyIntolerance",
        "clinicalStatus": {
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical",
                "code": "active",
                "display": "Active",
            }]
        },
        "verificationStatus": {
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-verification",
                "code": verification,
                "display": verification.capitalize(),
            }]
        },
        "type": {
            "coding": [{
                "system": "http://hl7.org/fhir/allergy-intolerance-type",
                "code": "allergy",
            }]
        },
        "category":    [category],
        "criticality": criticality,
        "code": {"text": substance},
        "patient":     {"reference": f"Patient/{pid}"},
        "recordedDate": datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="seconds"),
    }

    if onset_date:
        allergy["onsetDateTime"] = onset_date

    if reaction:
        allergy["reaction"] = [{
            "manifestation": [{
                "concept": {"text": reaction},
            }],
            "severity": severity,
        }]

    # ── POST lên Aidbox ──
    result = fhir_post("AllergyIntolerance", allergy)
    if "error" in result:
        return result

    allergy_id = result.get("id", "?")

    # ── Patient summary ──
    patient = fhir_get(f"Patient/{pid}")
    p_summary = patient_summary(patient) if "error" not in patient else {}

    return {
        "saved":         True,
        "allergy_id":    allergy_id,
        "patient_id":    pid,
        "patient_name":  p_summary.get("name"),
        "substance":     substance,
        "category":      category,
        "severity":      severity,
        "severity_vi":   severity_vi,
        "criticality":   criticality,
        "verification":  verification,
        "reaction":      reaction or None,
        "summary":       f"Đã ghi nhận dị ứng {substance} (mức {severity_vi}).",
        "_citation":     "HL7 FHIR R5 AllergyIntolerance; QĐ 1088/QĐ-BYT 2013",
    }
