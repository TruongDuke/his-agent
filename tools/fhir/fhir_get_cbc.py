"""Lấy kết quả CBC mới nhất của bệnh nhân từ Aidbox và chạy sàng lọc SXHD.

Flow:
  1. Fetch Patient → lấy gender (để chọn Hct baseline đúng giới)
  2. Fetch 2 CBC panel gần nhất (LOINC 58410-2) → component extraction
  3. Gọi dengue_cbc_predict.run() với dữ liệu thực từ FHIR
  4. Trả về CBC thô + kết quả sàng lọc SXHD trong một response
"""
from __future__ import annotations

TOOL_NAME = "fhir_get_cbc"
CATEGORY  = "Healthcare"
DESCRIPTION = (
    "Lấy kết quả xét nghiệm CBC (công thức máu) mới nhất của bệnh nhân từ HIS "
    "và tự động chạy sàng lọc Sốt Xuất Huyết Dengue. "
    "Input: patient_id. Tùy chọn: fever_day (ngày sốt thứ mấy). "
    "Output: chỉ số CBC thô (PLT, WBC, HCT, HGB, AST, ALT) + đánh giá SXHD "
    "(dengue_likelihood, findings, khuyến nghị). "
    "Dùng khi bác sĩ muốn xem CBC hoặc đánh giá nguy cơ SXHD từ hồ sơ bệnh nhân."
)
ARGS_SCHEMA = {
    "patient_id": "string — ID bệnh nhân (lấy từ fhir_search_patient). BẮT BUỘC.",
    "fever_day":  "number — Ngày sốt thứ mấy. Tùy chọn nhưng khuyến nghị để đánh giá giai đoạn.",
}

# LOINC codes CBC components
_LOINC_MAP = {
    "777-3":  "plt",
    "6690-2": "wbc",
    "4544-3": "hct",
    "718-7":  "hgb",
    "1920-8": "ast",
    "1742-6": "alt",
}

_LOINC_DISPLAY = {
    "777-3":  "Platelets (PLT)",
    "6690-2": "WBC (Bạch cầu)",
    "4544-3": "Hematocrit (HCT)",
    "718-7":  "Hemoglobin (HGB)",
    "1920-8": "AST (SGOT)",
    "1742-6": "ALT (SGPT)",
}


def _extract_components(observation: dict) -> dict:
    """Trích giá trị từ component[] của CBC panel."""
    result = {}
    for comp in observation.get("component", []):
        coding = (comp.get("code", {}).get("coding") or [{}])[0]
        loinc  = coding.get("code", "")
        key    = _LOINC_MAP.get(loinc)
        if key:
            val = (comp.get("valueQuantity") or {}).get("value")
            if val is not None:
                result[key] = float(val)
    return result


def run(args: dict) -> dict:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
    from _aidbox_client import fhir_get, extract_entries, patient_summary

    pid = str(args.get("patient_id") or "").strip()
    if not pid:
        return {"error": "patient_id là bắt buộc"}

    fever_day = args.get("fever_day")

    # ── 1. Lấy thông tin Patient (gender) ──
    patient_bundle = fhir_get(f"Patient/{pid}")
    if "error" in patient_bundle:
        return patient_bundle

    p_summary = patient_summary(patient_bundle)
    gender_fhir = (patient_bundle.get("gender") or "").lower()
    gender = "male" if gender_fhir == "male" else ("female" if gender_fhir == "female" else "")

    # ── 2. Fetch 2 CBC panel gần nhất ──
    bundle = fhir_get("Observation", {
        "subject":  f"Patient/{pid}",
        "code":     "58410-2",
        "_sort":    "-date",
        "_count":   "2",
    })
    if "error" in bundle:
        return bundle

    entries = [e for e in extract_entries(bundle) if e.get("status") != "entered-in-error"]

    if not entries:
        return {
            "patient_id":  pid,
            "patient_name": p_summary.get("name"),
            "cbc_found":   False,
            "message":     "Không tìm thấy kết quả CBC trong hồ sơ bệnh nhân.",
        }

    # CBC mới nhất
    latest = entries[0]
    latest_date = (latest.get("effectiveDateTime") or "")[:10]
    cbc = _extract_components(latest)

    # CBC lần trước (nếu có) → lấy plt_previous trong cùng đợt bệnh
    plt_previous = None
    prev_date = None
    if len(entries) >= 2:
        from datetime import date, timedelta
        today = date.today()
        if fever_day is not None:
            episode_start = today - timedelta(days=int(fever_day))
        else:
            episode_start = today - timedelta(days=7)

        prev_date_str = (entries[1].get("effectiveDateTime") or "")[:10]
        try:
            if prev_date_str and date.fromisoformat(prev_date_str) >= episode_start:
                prev_cbc = _extract_components(entries[1])
                plt_previous = prev_cbc.get("plt")
                prev_date = prev_date_str
        except ValueError:
            pass

    if not cbc.get("plt"):
        return {
            "patient_id":   pid,
            "patient_name": p_summary.get("name"),
            "cbc_found":    True,
            "cbc_date":     latest_date,
            "error":        "CBC panel không có giá trị PLT — không thể chạy sàng lọc SXHD.",
        }

    # ── 3. Gọi dengue_cbc_predict ──
    import importlib, pathlib
    dengue_mod = importlib.import_module("tools.dengue.dengue_cbc_predict")

    dengue_args = {k: v for k, v in cbc.items()}
    dengue_args["gender"] = gender
    if plt_previous is not None:
        dengue_args["plt_previous"] = plt_previous
    if fever_day is not None:
        dengue_args["fever_day"] = fever_day

    dengue_result = dengue_mod.run(dengue_args)

    # ── 4. Build response ──
    cbc_display = {}
    for loinc, key in _LOINC_MAP.items():
        val = cbc.get(key)
        if val is not None:
            cbc_display[_LOINC_DISPLAY[loinc]] = val

    return {
        "patient_id":    pid,
        "patient_name":  p_summary.get("name"),
        "patient_gender": gender_fhir or "unknown",
        "cbc_found":     True,
        "cbc_date":      latest_date,
        "prev_cbc_date": prev_date,
        "cbc_values":    cbc_display,
        "dengue_screening": dengue_result,
    }
