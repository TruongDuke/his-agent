"""Lưu sinh hiệu (vital signs) vào Aidbox dưới dạng FHIR Observation panel.

Dùng khi:
  - Bác sĩ/điều dưỡng nhập sinh hiệu trong chat
  - Form nhập nhanh từ UI

Một lần gọi → một FHIR Observation panel (LOINC 85353-1) gồm nhiều component:
huyết áp, mạch, nhịp thở, nhiệt độ, SpO2, cân nặng, chiều cao.

Tự động đánh dấu chỉ số bất thường (interpretation N/H/HH/L/LL) theo:
  - Huyết áp: QĐ 3192/QĐ-BYT 2010 + Hướng dẫn THA VNHA 2022 (đồng bộ ESC/ESH 2018)
  - Nhiệt độ, mạch, nhịp thở, SpO2: Bệnh học Nội khoa (ngưỡng người lớn, không áp dụng cho trẻ em)
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta

TOOL_NAME = "fhir_create_vitals"
CATEGORY  = "Healthcare"
DESCRIPTION = (
    "Lưu sinh hiệu của bệnh nhân vào HIS dưới dạng FHIR Observation panel "
    "(huyết áp, mạch, nhịp thở, nhiệt độ, SpO2, cân nặng, chiều cao). "
    "Tự động cảnh báo các chỉ số bất thường theo chuẩn Bộ Y tế và y khoa lâm sàng. "
    "Các chỉ số không cung cấp sẽ không được lưu."
)
ARGS_SCHEMA = {
    "patient_id":  "string — ID bệnh nhân (lấy từ fhir_search_patient). BẮT BUỘC.",
    "systolic":    "number — Huyết áp tâm thu (mmHg). VD: 130. Tùy chọn.",
    "diastolic":   "number — Huyết áp tâm trương (mmHg). VD: 85. Tùy chọn.",
    "heart_rate":  "number — Nhịp tim (bpm). VD: 88. Tùy chọn.",
    "resp_rate":   "number — Nhịp thở (lần/phút). VD: 18. Tùy chọn.",
    "temp":        "number — Nhiệt độ cơ thể (°C). VD: 37.2. Tùy chọn.",
    "spo2":        "number — Bão hòa oxy máu (%). VD: 98. Tùy chọn.",
    "weight":      "number — Cân nặng (kg). Tùy chọn.",
    "height":      "number — Chiều cao (cm). Tùy chọn.",
    "measured_at": (
        "string — Thời điểm đo, ISO 8601. VD: '2026-06-12T08:00:00+07:00'. "
        "Mặc định: thời điểm hiện tại."
    ),
}

# LOINC mapping cho component đơn lẻ: field → (loinc, display, unit, ucum)
_FIELDS = {
    "systolic":   ("8480-6",  "Huyết áp tâm thu",  "mmHg",    "mm[Hg]"),
    "diastolic":  ("8462-4",  "Huyết áp tâm trương", "mmHg",  "mm[Hg]"),
    "heart_rate": ("8867-4",  "Nhịp tim",          "lần/phút", "/min"),
    "resp_rate":  ("9279-1",  "Nhịp thở",          "lần/phút", "/min"),
    "temp":       ("8310-5",  "Nhiệt độ cơ thể",   "°C",      "Cel"),
    "spo2":       ("59408-5", "SpO2",              "%",       "%"),
    "weight":     ("29463-7", "Cân nặng",          "kg",      "kg"),
    "height":     ("8302-2",  "Chiều cao",         "cm",      "cm"),
}

# HL7 v3 ObservationInterpretation: N=normal, H=high, HH=critical high, L=low, LL=critical low
_INTERP_DISPLAY = {
    "N":  "Bình thường",
    "H":  "Cao",
    "HH": "Cao nguy hiểm",
    "L":  "Thấp",
    "LL": "Thấp nguy hiểm",
}

_CITATION = "QĐ 3192/QĐ-BYT 2010 (THA), VNHA 2022, Bệnh học Nội khoa"


def _safe_float(val):
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _interp_temp(t: float) -> tuple[str, str | None]:
    """°C người lớn."""
    if t < 35.0:   return "LL", "Hạ thân nhiệt (<35°C) — nguy hiểm"
    if t < 36.0:   return "L",  "Nhiệt độ thấp"
    if t <= 37.5:  return "N",  None
    if t < 38.5:   return "N",  None  # sốt nhẹ — không cảnh báo
    if t < 39.5:   return "H",  f"Sốt cao ({t}°C)"
    return "HH", f"Sốt rất cao ({t}°C) — nguy hiểm"


def _interp_hr(hr: float) -> tuple[str, str | None]:
    """bpm người lớn."""
    if hr < 40:    return "LL", f"Nhịp chậm nguy hiểm ({int(hr)} bpm)"
    if hr < 60:    return "L",  f"Nhịp chậm ({int(hr)} bpm)"
    if hr <= 100:  return "N",  None
    if hr <= 130:  return "H",  f"Nhịp nhanh ({int(hr)} bpm)"
    return "HH", f"Nhịp tim nhanh nguy hiểm ({int(hr)} bpm)"


def _interp_rr(rr: float) -> tuple[str, str | None]:
    """lần/phút người lớn."""
    if rr < 8:     return "LL", f"Thở chậm nguy hiểm ({int(rr)} l/p)"
    if rr < 12:    return "L",  f"Thở chậm ({int(rr)} l/p)"
    if rr <= 20:   return "N",  None
    if rr <= 25:   return "H",  f"Thở nhanh ({int(rr)} l/p)"
    return "HH", f"Thở nhanh nguy hiểm ({int(rr)} l/p)"


def _interp_spo2(s: float) -> tuple[str, str | None]:
    if s >= 95:    return "N",  None
    if s >= 91:    return "L",  f"Giảm oxy máu nhẹ (SpO2 {s}%)"
    return "LL", f"Giảm oxy máu nặng (SpO2 {s}%) — cần can thiệp"


def _interp_bp(sys_v: float | None, dia_v: float | None) -> tuple[str, str, str, str | None]:
    """
    Trả về (interp_sys, interp_dia, alert_level, alert_message).
    Phân độ theo BYT 3192/QĐ-BYT — lấy giai đoạn CAO HƠN của sys vs dia.
    """
    def stage_sys(v):
        if v is None: return None
        if v < 90:    return ("LL", "tụt")
        if v < 130:   return ("N",  "bt")
        if v < 140:   return ("N",  "bt-cao")
        if v < 160:   return ("H",  "THA độ 1")
        if v < 180:   return ("H",  "THA độ 2")
        return ("HH", "THA độ 3")

    def stage_dia(v):
        if v is None: return None
        if v < 60:    return ("LL", "tụt")
        if v < 85:    return ("N",  "bt")
        if v < 90:    return ("N",  "bt-cao")
        if v < 100:   return ("H",  "THA độ 1")
        if v < 110:   return ("H",  "THA độ 2")
        return ("HH", "THA độ 3")

    s = stage_sys(sys_v)
    d = stage_dia(dia_v)

    # Lấy mức nặng hơn
    order = {"N": 0, "L": 1, "LL": 2, "H": 1, "HH": 2}
    pick = None
    for st in (s, d):
        if st is None:
            continue
        if pick is None or order[st[0]] > order[pick[0]]:
            pick = st

    if pick is None:
        return "N", "N", "N", None

    interp_s = s[0] if s else "N"
    interp_d = d[0] if d else "N"
    level    = pick[0]
    label    = pick[1]

    if level == "N":
        return interp_s, interp_d, "N", None

    sys_str = f"{int(sys_v)}" if sys_v is not None else "?"
    dia_str = f"{int(dia_v)}" if dia_v is not None else "?"
    if label == "tụt":
        msg = f"Tụt huyết áp ({sys_str}/{dia_str} mmHg)"
    else:
        msg = f"{label} ({sys_str}/{dia_str} mmHg)"
    return interp_s, interp_d, level, msg


def _ref_range_text(field: str) -> str:
    return {
        "systolic":   "BT: 90–139 mmHg (BYT 3192/QĐ-BYT)",
        "diastolic":  "BT: 60–89 mmHg (BYT 3192/QĐ-BYT)",
        "heart_rate": "BT người lớn: 60–100 bpm",
        "resp_rate":  "BT người lớn: 12–20 l/p",
        "temp":       "BT: 36.5–37.5°C",
        "spo2":       "BT: ≥95%",
        "weight":     "",
        "height":     "",
    }.get(field, "")


def _build_component(field: str, value: float, interp: str | None) -> dict:
    loinc, display, unit, ucum = _FIELDS[field]
    comp = {
        "code": {"coding": [{"system": "http://loinc.org", "code": loinc, "display": display}]},
        "valueQuantity": {
            "value": value, "unit": unit,
            "system": "http://unitsofmeasure.org", "code": ucum,
        },
    }
    if interp and interp != "N":
        comp["interpretation"] = [{
            "coding": [{
                "system":  "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                "code":    interp,
                "display": _INTERP_DISPLAY.get(interp, interp),
            }]
        }]
    ref_txt = _ref_range_text(field)
    if ref_txt:
        comp["referenceRange"] = [{"text": ref_txt}]
    return comp


def run(args: dict) -> dict:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
    from _aidbox_client import fhir_post, fhir_get, patient_summary

    pid = str(args.get("patient_id") or "").strip()
    if not pid:
        return {"error": "patient_id là bắt buộc"}

    # ── Thu thập giá trị được cung cấp ──
    values: dict[str, float] = {}
    for field in _FIELDS:
        v = _safe_float(args.get(field))
        if v is not None:
            values[field] = v

    if not values:
        return {"error": "Phải cung cấp ít nhất 1 chỉ số sinh hiệu"}

    # ── Phân tích cảnh báo ──
    interp_map: dict[str, str] = {}
    alerts: list[dict] = []

    # BP — phân tích chung sys + dia
    sys_v = values.get("systolic")
    dia_v = values.get("diastolic")
    if sys_v is not None or dia_v is not None:
        i_sys, i_dia, level, msg = _interp_bp(sys_v, dia_v)
        if sys_v is not None:
            interp_map["systolic"]  = i_sys
        if dia_v is not None:
            interp_map["diastolic"] = i_dia
        if msg:
            alerts.append({
                "field":    "Huyết áp",
                "severity": "critical" if level == "HH" or level == "LL" else "warning",
                "interpretation": level,
                "message":  msg,
            })

    # Các chỉ số đơn lẻ
    single_interp_funcs = {
        "heart_rate": ("Mạch",      _interp_hr),
        "resp_rate":  ("Nhịp thở",  _interp_rr),
        "temp":       ("Nhiệt độ",  _interp_temp),
        "spo2":       ("SpO2",      _interp_spo2),
    }
    for field, (label, fn) in single_interp_funcs.items():
        if field not in values:
            continue
        interp, msg = fn(values[field])
        interp_map[field] = interp
        if msg:
            alerts.append({
                "field":          label,
                "severity":       "critical" if interp in ("HH", "LL") else "warning",
                "interpretation": interp,
                "message":        msg,
            })

    # ── Thời điểm đo ──
    measured_at = str(args.get("measured_at") or "").strip()
    if not measured_at:
        tz7 = timezone(timedelta(hours=7))
        measured_at = datetime.now(tz7).strftime("%Y-%m-%dT%H:%M:%S+07:00")

    # ── Build FHIR Observation panel ──
    components = [
        _build_component(field, values[field], interp_map.get(field))
        for field in _FIELDS if field in values
    ]

    observation = {
        "resourceType": "Observation",
        "status": "final",
        "category": [{
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                "code":   "vital-signs",
            }]
        }],
        "code": {"coding": [{
            "system":  "http://loinc.org",
            "code":    "85353-1",
            "display": "Vital signs panel",
        }]},
        "subject":           {"reference": f"Patient/{pid}"},
        "effectiveDateTime": measured_at,
        "component":         components,
    }

    # Interpretation ở mức panel (nặng nhất)
    if alerts:
        order = {"N": 0, "L": 1, "H": 1, "LL": 2, "HH": 2}
        top = max((a["interpretation"] for a in alerts), key=lambda c: order.get(c, 0))
        observation["interpretation"] = [{
            "coding": [{
                "system":  "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                "code":    top,
                "display": _INTERP_DISPLAY.get(top, top),
            }]
        }]

    # ── POST lên Aidbox ──
    result = fhir_post("Observation", observation)
    if "error" in result:
        return result

    obs_id   = result.get("id", "?")
    obs_date = (result.get("effectiveDateTime") or measured_at)[:10]

    # ── Patient summary để LLM có ngữ cảnh ──
    patient = fhir_get(f"Patient/{pid}")
    p_summary = patient_summary(patient) if "error" not in patient else {}

    # ── Summary chỉ số đã lưu ──
    vitals_saved: dict[str, str] = {}
    if "systolic" in values or "diastolic" in values:
        sv = f"{int(values['systolic'])}"  if "systolic"  in values else "?"
        dv = f"{int(values['diastolic'])}" if "diastolic" in values else "?"
        vitals_saved["Huyết áp"] = f"{sv}/{dv} mmHg"
    if "heart_rate" in values:
        vitals_saved["Mạch"]      = f"{int(values['heart_rate'])} bpm"
    if "resp_rate" in values:
        vitals_saved["Nhịp thở"]  = f"{int(values['resp_rate'])} l/p"
    if "temp" in values:
        vitals_saved["Nhiệt độ"]  = f"{values['temp']}°C"
    if "spo2" in values:
        vitals_saved["SpO2"]      = f"{int(values['spo2'])}%"
    if "weight" in values:
        vitals_saved["Cân nặng"]  = f"{values['weight']} kg"
    if "height" in values:
        vitals_saved["Chiều cao"] = f"{values['height']} cm"

    has_critical = any(a["severity"] == "critical" for a in alerts)
    if has_critical:
        summary = "Đã lưu sinh hiệu. ⚠ Có chỉ số nguy hiểm — cần xử trí ngay."
    elif alerts:
        summary = "Đã lưu sinh hiệu. ⚠ Có chỉ số bất thường."
    else:
        summary = "Đã lưu sinh hiệu. Tất cả chỉ số trong giới hạn bình thường."

    return {
        "saved":            True,
        "observation_id":   obs_id,
        "observation_date": obs_date,
        "patient_id":       pid,
        "patient_name":     p_summary.get("name"),
        "vitals_saved":     vitals_saved,
        "alerts":           alerts,
        "summary":          summary,
        "_citation":        _CITATION,
    }
