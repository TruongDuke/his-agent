"""UC-D1 Sàng lọc Sốt Xuất Huyết Dengue theo tiêu chuẩn Bộ Y tế Việt Nam."""

TOOL_NAME = "dengue_symptom_assessment"
CATEGORY = "Healthcare"
DESCRIPTION = (
    "Phân loại mức độ sốt xuất huyết Dengue (SXHD) dựa trên triệu chứng bệnh nhân khai báo. "
    "Áp dụng tiêu chuẩn phân độ 4 lớp của Bộ Y tế Việt Nam. "
    "Trả về: severity (none/mild/warning/severe), recommendation, next_action, urgency_color. "
    "Dùng khi đã thu thập đủ thông tin qua hội thoại với bệnh nhân về các triệu chứng SXHD. "
    "KHÔNG thay thế chẩn đoán lâm sàng — chỉ là công cụ sàng lọc ban đầu."
)
ARGS_SCHEMA = {
    "in_epidemic_area": (
        "boolean — Bệnh nhân đang ở/vừa đến vùng có dịch SXHD không? (true/false)"
    ),
    "fever_days": (
        "number — Số ngày sốt (0 = không sốt). Sốt > 7 ngày không điển hình cho SXHD cấp."
    ),
    "symptoms": (
        "array of string — Triệu chứng cơ bản có mặt. "
        "Giá trị hợp lệ: 'nausea_vomiting', 'rash', 'body_pain', 'skin_bleeding'. "
        "Ví dụ: ['nausea_vomiting', 'body_pain']"
    ),
    "warning_signs": (
        "array of string (tùy chọn) — Dấu hiệu cảnh báo. "
        "Giá trị hợp lệ: 'abdominal_pain', 'persistent_vomiting', 'mucosal_bleeding', "
        "'oliguria', 'lethargy'."
    ),
    "severe_signs": (
        "array of string (tùy chọn) — Dấu hiệu nặng. "
        "Giá trị hợp lệ: 'shock_signs', 'severe_bleeding', 'organ_failure'."
    ),
}

_VALID_SYMPTOMS = {"nausea_vomiting", "rash", "body_pain", "skin_bleeding"}
_VALID_WARNING  = {"abdominal_pain", "persistent_vomiting", "mucosal_bleeding", "oliguria", "lethargy"}
_VALID_SEVERE   = {"shock_signs", "severe_bleeding", "organ_failure"}

_SYMPTOM_LABEL = {
    "nausea_vomiting":    "Buồn nôn / nôn ói",
    "rash":               "Phát ban / nổi mẩn đỏ",
    "body_pain":          "Đau cơ / đau khớp / nhức hố mắt",
    "skin_bleeding":      "Xuất huyết dưới da / bầm tím",
    "abdominal_pain":     "Đau bụng nhiều / đau vùng gan",
    "persistent_vomiting":"Nôn ói liên tục nhiều lần",
    "mucosal_bleeding":   "Chảy máu niêm mạc (răng, mũi, phân đen…)",
    "oliguria":           "Tiểu ít / nước tiểu sẫm màu",
    "lethargy":           "Vật vã / lờ đờ / mệt lả",
    "shock_signs":        "Dấu hiệu sốc (tụt HA, ngất, tay chân lạnh…)",
    "severe_bleeding":    "Xuất huyết ồ ạt không cầm",
    "organ_failure":      "Suy tạng (vàng da, co giật, rối loạn ý thức…)",
}


def _load_protocol() -> dict:
    import json, os
    path = os.path.join(os.path.dirname(__file__), "..", "knowledge_base", "dengue_protocol.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _to_set(val):
    if not val:
        return set()
    if isinstance(val, list):
        return {str(v).strip() for v in val}
    if isinstance(val, str):
        import json as _json
        try:
            parsed = _json.loads(val)
            if isinstance(parsed, list):
                return {str(v).strip() for v in parsed}
        except Exception:
            pass
        # comma-separated fallback
        return {v.strip().strip('"').strip("'") for v in val.split(",") if v.strip()}
    return {str(val).strip()}


def _labels(fields):
    return [_SYMPTOM_LABEL.get(f, f) for f in fields]


_CITATION = "Phụ lục 2 · QĐ 2760/QĐ-BYT 2023 · Bộ Y tế Việt Nam · WHO Dengue Guidelines 2009"


def run(args: dict) -> dict:
    result = _run(args)
    result["_citation"] = _CITATION
    return result


def _run(args: dict) -> dict:
    proto = _load_protocol()
    rules = proto["classification_rules"]
    meta  = proto["meta"]

    # --- Parse inputs ---
    in_epidemic_area = args.get("in_epidemic_area")
    # Accept both bool and string "true"/"false"
    if isinstance(in_epidemic_area, str):
        in_epidemic_area = in_epidemic_area.strip().lower() in ("true", "yes", "có", "1")
    else:
        in_epidemic_area = bool(in_epidemic_area)

    try:
        fever_days = float(args.get("fever_days", 0) or 0)
    except (ValueError, TypeError):
        fever_days = 0.0

    symptoms     = _to_set(args.get("symptoms"))     & _VALID_SYMPTOMS
    warning_signs = _to_set(args.get("warning_signs")) & _VALID_WARNING
    severe_signs  = _to_set(args.get("severe_signs"))  & _VALID_SEVERE

    # --- Layer 4: Severe — stop immediately ---
    if severe_signs:
        r = rules["severe"]
        return {
            "severity":             "severe",
            "severity_label":       r["severity_label"],
            "urgency_color":        r["urgency_color"],
            "met_criteria":         _labels(symptoms),
            "basic_symptoms":       _labels(symptoms),
            "warning_signs":        _labels(warning_signs),
            "abnormal_signs":       _labels(severe_signs),
            "summary":              r["summary"],
            "recommendation":       r["recommendation"],
            "next_action":          r["next_action"],
            "suggested_department": r.get("suggested_department"),
            "home_care":            None,
            "disclaimer":           meta["disclaimer"],
        }

    # --- Layer 1: Epidemiology gate ---
    if not in_epidemic_area:
        r = rules["none"]
        return {
            "severity":        "none",
            "severity_label":  r["severity_label"],
            "urgency_color":   r["urgency_color"],
            "met_criteria":    [],
            "basic_symptoms":  _labels(symptoms),
            "warning_signs":   [],
            "abnormal_signs":  [],
            "fail_reason":     "Không đủ điều kiện dịch tễ (không ở/đến vùng có dịch).",
            "summary":         r["summary"],
            "recommendation":  r["recommendation"],
            "next_action":     r["next_action"],
            "home_care":       None,
            "disclaimer":      meta["disclaimer"],
        }

    if fever_days <= 0:
        r = rules["none"]
        return {
            "severity":        "none",
            "severity_label":  r["severity_label"],
            "urgency_color":   r["urgency_color"],
            "met_criteria":    [],
            "basic_symptoms":  _labels(symptoms),
            "warning_signs":   [],
            "abnormal_signs":  [],
            "fail_reason":     "Không có sốt.",
            "summary":         r["summary"],
            "recommendation":  r["recommendation"],
            "next_action":     r["next_action"],
            "home_care":       None,
            "disclaimer":      meta["disclaimer"],
        }

    if fever_days > 7:
        r = rules["none"]
        return {
            "severity":        "none",
            "severity_label":  r["severity_label"],
            "urgency_color":   r["urgency_color"],
            "met_criteria":    [],
            "basic_symptoms":  _labels(symptoms),
            "warning_signs":   [],
            "abnormal_signs":  [],
            "fail_reason":     f"Sốt {int(fever_days)} ngày — quá 7 ngày, không điển hình SXHD cấp.",
            "summary":         r["summary"],
            "recommendation":  r["recommendation"],
            "next_action":     r["next_action"],
            "home_care":       None,
            "disclaimer":      meta["disclaimer"],
        }

    # --- Layer 2: Basic symptoms (need ≥2) ---
    if len(symptoms) < 2:
        r = rules["none"]
        return {
            "severity":        "none",
            "severity_label":  r["severity_label"],
            "urgency_color":   r["urgency_color"],
            "met_criteria":    _labels(symptoms),
            "basic_symptoms":  _labels(symptoms),
            "warning_signs":   [],
            "abnormal_signs":  [],
            "fail_reason":     f"Chỉ có {len(symptoms)}/4 triệu chứng cơ bản (cần ≥2).",
            "summary":         r["summary"],
            "recommendation":  r["recommendation"],
            "next_action":     r["next_action"],
            "home_care":       None,
            "disclaimer":      meta["disclaimer"],
        }

    # --- Layer 3: Warning signs ---
    if warning_signs:
        r = rules["warning"]
        return {
            "severity":             "warning",
            "severity_label":       r["severity_label"],
            "urgency_color":        r["urgency_color"],
            "met_criteria":         _labels(symptoms),
            "basic_symptoms":       _labels(symptoms),
            "warning_signs":        _labels(warning_signs),
            "abnormal_signs":       _labels(warning_signs),
            "summary":              r["summary"],
            "recommendation":       r["recommendation"],
            "next_action":          r["next_action"],
            "suggested_department": r.get("suggested_department"),
            "home_care":            None,
            "disclaimer":           meta["disclaimer"],
        }

    # --- Mild SXHD ---
    r = rules["mild"]
    return {
        "severity":        "mild",
        "severity_label":  r["severity_label"],
        "urgency_color":   r["urgency_color"],
        "met_criteria":    _labels(symptoms),
        "basic_symptoms":  _labels(symptoms),
        "warning_signs":   [],
        "abnormal_signs":  [],
        "summary":         r["summary"],
        "recommendation":  r["recommendation"],
        "next_action":     r["next_action"],
        "home_care":       r.get("home_care"),
        "disclaimer":     meta["disclaimer"],
    }
