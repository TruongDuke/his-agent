"""Lưu kết quả CBC vào Aidbox dưới dạng FHIR Observation (panel + component).

Dùng khi:
  - Bác sĩ nhập tay kết quả CBC từ phiếu xét nghiệm
  - Agent trích xuất giá trị từ ảnh phiếu xét nghiệm (vision)
  - LIS ngoài hệ thống gửi kết quả qua bác sĩ

Sau khi lưu, tự động chạy fhir_get_cbc để trả ngay kết quả sàng lọc SXHD.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta

TOOL_NAME = "fhir_create_cbc"
CATEGORY  = "Healthcare"
DESCRIPTION = (
    "Lưu kết quả xét nghiệm CBC vào hồ sơ bệnh nhân trong HIS (FHIR Observation). "
    "Dùng khi bác sĩ nhập tay hoặc đọc từ ảnh phiếu xét nghiệm. "
    "Sau khi lưu, tự động trả về kết quả sàng lọc Sốt Xuất Huyết Dengue. "
    "Các chỉ số không cung cấp sẽ không được lưu vào hồ sơ."
)
ARGS_SCHEMA = {
    "patient_id":   "string — ID bệnh nhân (lấy từ fhir_search_patient). BẮT BUỘC.",
    "plt":          "number — Tiểu cầu (Platelets), K/μL. Ví dụ: 85. BẮT BUỘC.",
    "wbc":          "number — Bạch cầu (WBC), K/μL. Ví dụ: 3.2. Tùy chọn.",
    "hct":          "number — Hematocrit, %. Ví dụ: 44.5. Tùy chọn.",
    "hgb":          "number — Hemoglobin, g/dL. Ví dụ: 13.5. Tùy chọn.",
    "ast":          "number — AST (SGOT), U/L. Tùy chọn.",
    "alt":          "number — ALT (SGPT), U/L. Tùy chọn.",
    "fever_day":    "number — Ngày sốt thứ mấy (dùng cho sàng lọc SXHD). Tùy chọn.",
    "collected_at": (
        "string — Thời điểm lấy mẫu, ISO 8601. Ví dụ: '2026-05-11T08:00:00+07:00'. "
        "Mặc định: thời điểm hiện tại."
    ),
}

# LOINC mapping: field_name → (loinc_code, display, unit_label, ucum_code)
_FIELDS = {
    "plt": ("777-3",  "Platelets",   "10*3/uL", "10*3/uL"),
    "wbc": ("6690-2", "WBC",         "10*3/uL", "10*3/uL"),
    "hct": ("4544-3", "Hematocrit",  "%",       "%"),
    "hgb": ("718-7",  "Hemoglobin",  "g/dL",    "g/dL"),
    "ast": ("1920-8", "AST",         "U/L",     "U/L"),
    "alt": ("1742-6", "ALT",         "U/L",     "U/L"),
}


def _safe_float(val):
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def run(args: dict) -> dict:
    import sys, os, importlib
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
    from _aidbox_client import fhir_post, fhir_get, patient_summary

    pid = str(args.get("patient_id") or "").strip()
    if not pid:
        return {"error": "patient_id là bắt buộc"}

    plt = _safe_float(args.get("plt"))
    if plt is None:
        return {"error": "plt (tiểu cầu) là bắt buộc để lưu CBC"}

    # ── Thu thập các giá trị được cung cấp ──
    values = {}
    for field in _FIELDS:
        v = _safe_float(args.get(field))
        if v is not None:
            values[field] = v

    # ── Thời điểm lấy mẫu ──
    collected_at = str(args.get("collected_at") or "").strip()
    if not collected_at:
        tz7 = timezone(timedelta(hours=7))
        collected_at = datetime.now(tz7).strftime("%Y-%m-%dT%H:%M:%S+07:00")

    # ── Build FHIR Observation ──
    components = []
    for field, (loinc, display, unit, ucum) in _FIELDS.items():
        val = values.get(field)
        if val is None:
            continue
        components.append({
            "code": {"coding": [{"system": "http://loinc.org", "code": loinc, "display": display}]},
            "valueQuantity": {
                "value":  val,
                "unit":   unit,
                "system": "http://unitsofmeasure.org",
                "code":   ucum,
            },
        })

    observation = {
        "resourceType": "Observation",
        "status": "final",
        "category": [{
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                "code":   "laboratory",
            }]
        }],
        "code": {"coding": [{
            "system":  "http://loinc.org",
            "code":    "58410-2",
            "display": "CBC panel",
        }]},
        "subject":           {"reference": f"Patient/{pid}"},
        "effectiveDateTime": collected_at,
        "component":         components,
    }

    # ── POST lên Aidbox ──
    result = fhir_post("Observation", observation)
    if "error" in result:
        return result

    obs_id   = result.get("id", "?")
    obs_date = (result.get("effectiveDateTime") or collected_at)[:10]

    # ── Chạy sàng lọc SXHD ngay sau khi lưu ──
    dengue_mod = importlib.import_module("tools.dengue.dengue_cbc_predict")

    # Lấy gender từ Patient để chọn baseline Hct đúng
    patient = fhir_get(f"Patient/{pid}")
    gender_fhir = (patient.get("gender") or "").lower() if "error" not in patient else ""
    gender = "male" if gender_fhir == "male" else ("female" if gender_fhir == "female" else "")
    p_summary = patient_summary(patient) if "error" not in patient else {}

    dengue_args = {**values, "gender": gender}
    fever_day = _safe_float(args.get("fever_day"))
    if fever_day is not None:
        dengue_args["fever_day"] = fever_day

    # ── Tìm plt_previous trong cùng đợt bệnh ──
    try:
        from datetime import date
        today = date.today()
        if fever_day is not None:
            # Cửa sổ: từ ngày khởi phát sốt (buffer thêm 1 ngày)
            episode_start = today - timedelta(days=int(fever_day))
        else:
            # Không biết fever_day → an toàn lấy 7 ngày gần nhất
            episode_start = today - timedelta(days=7)

        prev_bundle = fhir_get("Observation", {
            "subject":  f"Patient/{pid}",
            "code":     "http://loinc.org|58410-2",
            "_sort":    "-date",
            "_count":   "2",
        })
        prev_obs_list = [
            e.get("resource", {})
            for e in (prev_bundle.get("entry") or [])
            if e.get("resource", {}).get("id") != obs_id
        ]
        for prev_obs in prev_obs_list:
            prev_date_str = (prev_obs.get("effectiveDateTime") or "")[:10]
            if not prev_date_str:
                continue
            try:
                prev_date = date.fromisoformat(prev_date_str)
            except ValueError:
                continue
            if prev_date < episode_start:
                break  # đã qua cửa sổ, không dùng CBC cũ hơn
            for comp in (prev_obs.get("component") or []):
                coding = (comp.get("code", {}).get("coding") or [{}])[0]
                if coding.get("code") == "777-3":  # PLT LOINC
                    prev_plt = _safe_float((comp.get("valueQuantity") or {}).get("value"))
                    if prev_plt is not None:
                        dengue_args["plt_previous"] = prev_plt
                        dengue_args["_plt_previous_date"] = prev_date_str
                    break
            if "plt_previous" in dengue_args:
                break
    except Exception:
        pass  # plt_previous không bắt buộc, bỏ qua nếu lỗi

    dengue_result = dengue_mod.run(dengue_args)

    # ── Summary chỉ số đã lưu ──
    labels = {"plt": "PLT", "wbc": "WBC", "hct": "HCT", "hgb": "HGB", "ast": "AST", "alt": "ALT"}
    units  = {"plt": "K/μL", "wbc": "K/μL", "hct": "%", "hgb": "g/dL", "ast": "U/L", "alt": "U/L"}
    saved_summary = {labels[k]: f"{v} {units[k]}" for k, v in values.items()}

    out = {
        "saved": True,
        "observation_id":   obs_id,
        "observation_date": obs_date,
        "patient_id":       pid,
        "patient_name":     p_summary.get("name"),
        "cbc_saved":        saved_summary,
        "dengue_screening": dengue_result,
    }
    if "plt_previous" in dengue_args:
        out["plt_previous_used"] = {
            "plt":  dengue_args["plt_previous"],
            "date": dengue_args.get("_plt_previous_date", ""),
        }
    return out
