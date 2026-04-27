"""UC-03 Triage thông minh: đánh giá mức độ ưu tiên từ triệu chứng + bệnh nền."""

TOOL_NAME = "fhir_triage_assessment"
CATEGORY = "Healthcare"
DESCRIPTION = (
    "Đánh giá mức độ ưu tiên khám dựa trên triệu chứng + bệnh nền (triage). "
    "Trả về: urgency_level (EMERGENCY/URGENT/SEMI_URGENT/ROUTINE), "
    "recommended_action, khoa phù hợp, và câu hỏi follow-up nếu cần thêm thông tin. "
    "Dùng khi bệnh nhân MÔ TẢ TRIỆU CHỨNG thay vì biết trước muốn khám khoa nào. "
    "Nếu kết quả là EMERGENCY → KHÔNG đặt lịch, báo gọi 115 ngay. "
    "Nếu URGENT → đặt slot sớm nhất trong ngày. "
    "Nếu SEMI_URGENT/ROUTINE → đặt lịch bình thường."
)
ARGS_SCHEMA = {
    "symptoms":         "string — mô tả triệu chứng tự do (VD: 'đau ngực, khó thở, toát mồ hôi')",
    "onset":            "string (tùy chọn) — 'sudden' hoặc 'gradual'. Mặc định 'gradual'",
    "severity":         "string (tùy chọn) — 'mild'/'moderate'/'severe'. Mặc định 'moderate'",
    "known_conditions": "string (tùy chọn) — bệnh nền user tự khai (VD: 'tiểu đường, tăng huyết áp')",
    "patient_id":       "string (tùy chọn) — UUID bệnh nhân để đọc bệnh nền từ hồ sơ Aidbox",
}


def _load_kb() -> dict:
    import json, os
    kb_path = os.path.join(os.path.dirname(__file__), "knowledge_base", "triage_kb.json")
    with open(kb_path, encoding="utf-8") as f:
        return json.load(f)


def _normalize(text: str) -> str:
    import unicodedata, re
    text = text.lower().strip()
    text = unicodedata.normalize("NFC", text)
    return text


def _keywords_match(text: str, keywords: list[str]) -> list[str]:
    """Trả về list keywords nào khớp trong text."""
    matched = []
    norm = _normalize(text)
    for kw in keywords:
        if _normalize(kw) in norm:
            matched.append(kw)
    return matched


_LEVEL_PRIORITY = {"EMERGENCY": 4, "URGENT": 3, "SEMI_URGENT": 2, "ROUTINE": 1}
_UPGRADE_MAP = {
    "ROUTINE → SEMI_URGENT": ("ROUTINE", "SEMI_URGENT"),
    "SEMI_URGENT → URGENT":  ("SEMI_URGENT", "URGENT"),
    "ROUTINE → URGENT":      ("ROUTINE", "URGENT"),
    "SEMI_URGENT → EMERGENCY": ("SEMI_URGENT", "EMERGENCY"),
}


def _upgrade(current: str, rule: str) -> str:
    pair = _UPGRADE_MAP.get(rule)
    if not pair:
        return current
    from_level, to_level = pair
    if _LEVEL_PRIORITY.get(current, 0) <= _LEVEL_PRIORITY.get(from_level, 0):
        return to_level
    return current


def run(args: dict) -> dict:
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from _aidbox_client import fhir_get, extract_entries

    symptoms_raw   = str(args.get("symptoms") or "").strip()
    onset          = str(args.get("onset") or "gradual").strip().lower()
    severity       = str(args.get("severity") or "moderate").strip().lower()
    known_cond_raw = str(args.get("known_conditions") or "").strip()
    patient_id     = str(args.get("patient_id") or "").strip()

    if not symptoms_raw:
        return {"error": "symptoms is required"}

    kb = _load_kb()
    symptoms_text = symptoms_raw

    # --- Bước 1: Thu thập bệnh nền ---
    all_conditions: list[str] = []

    # Từ user khai
    if known_cond_raw:
        all_conditions.append(known_cond_raw)

    # Từ Aidbox nếu có patient_id
    if patient_id:
        try:
            cond_bundle = fhir_get("Condition", {"subject": f"Patient/{patient_id}", "_count": "20"})
            for c in extract_entries(cond_bundle):
                text = (c.get("code") or {}).get("text")
                if text:
                    all_conditions.append(text)
        except Exception:
            pass

    conditions_text = " ".join(all_conditions).lower()

    # --- Bước 2: Kiểm tra single red flags ---
    for srf in kb["single_red_flags"]:
        matched = _keywords_match(symptoms_text, srf["keywords"])
        if matched:
            return {
                "urgency_level": "EMERGENCY",
                "matched_rule": srf["id"],
                "rule_name": srf["note"],
                "matched_symptoms": matched,
                "action": srf["action"],
                "department": "EMERG",
                "message": srf["message"],
                "follow_up_questions": [],
                "disclaimer": kb["meta"]["disclaimer"],
            }

    # --- Bước 3: Kiểm tra red flag combos ---
    best_combo = None
    best_level_priority = 0

    for rfc in kb["red_flag_combos"]:
        # Check required symptoms
        required = rfc.get("symptoms_required", [])
        any_symptoms = rfc.get("symptoms_any", [])
        min_add = rfc.get("min_additional", 1)

        req_matched = all(
            any(_normalize(r) in _normalize(symptoms_text) for r in [req])
            for req in required
        ) if required else True

        if not req_matched:
            continue

        any_matched = _keywords_match(symptoms_text, any_symptoms)

        # Check onset if rule requires sudden onset
        if rfc.get("onset") == "sudden" and onset != "sudden":
            continue

        # Check risk_condition if rule requires it
        if rfc.get("risk_condition"):
            rc_keywords = {
                "diabetes":      ["tiểu đường", "đái tháo đường"],
                "hypertension":  ["tăng huyết áp", "cao huyết áp"],
                "heart_failure": ["suy tim"],
                "asthma":        ["hen suyễn", "hen phế quản"],
            }.get(rfc["risk_condition"], [rfc["risk_condition"]])
            if not _keywords_match(conditions_text, rc_keywords):
                continue

        if len(any_matched) >= min_add or (not any_symptoms and req_matched):
            level = rfc["level"]
            if _LEVEL_PRIORITY.get(level, 0) > best_level_priority:
                best_level_priority = _LEVEL_PRIORITY[level]
                best_combo = {
                    "matched_rule": rfc["id"],
                    "rule_name": rfc["name"],
                    "matched_symptoms": any_matched,
                    "level": level,
                    "action": rfc["action"],
                    "department": rfc.get("department", "GENERAL"),
                    "message": rfc["message"],
                }

    if best_combo:
        return {
            "urgency_level": best_combo["level"],
            "matched_rule": best_combo["matched_rule"],
            "rule_name": best_combo["rule_name"],
            "matched_symptoms": best_combo["matched_symptoms"],
            "action": best_combo["action"],
            "department": best_combo["department"],
            "message": best_combo["message"],
            "follow_up_questions": [],
            "disclaimer": kb["meta"]["disclaimer"],
        }

    # --- Bước 4: Urgency map (single symptom) ---
    best_map = None
    best_map_priority = 0
    follow_up_questions: list[str] = []

    for um in kb["urgency_map"]:
        matched = _keywords_match(symptoms_text, um["symptom_keywords"])
        if matched:
            level = um["default_level"]
            # Severity override
            if severity == "severe" and _LEVEL_PRIORITY.get(level, 0) < _LEVEL_PRIORITY["URGENT"]:
                level = "URGENT"
            if _LEVEL_PRIORITY.get(level, 0) > best_map_priority:
                best_map_priority = _LEVEL_PRIORITY[level]
                best_map = {
                    "level": level,
                    "department": um.get("department", "GENERAL"),
                    "note": um.get("note", ""),
                    "matched_symptoms": matched,
                }
                follow_up_questions = um.get("ask_more", [])

    # --- Bước 5: Áp dụng risk boosters ---
    applied_boosters: list[str] = []
    current_level = (best_map["level"] if best_map else "SEMI_URGENT")

    for rb in kb["risk_boosters"]:
        cond_matched = _keywords_match(conditions_text, rb["condition_keywords"])
        sym_matched  = _keywords_match(symptoms_text, rb["symptom_triggers"])
        if cond_matched and sym_matched:
            new_level = _upgrade(current_level, rb["upgrade"])
            if new_level != current_level:
                current_level = new_level
                applied_boosters.append(f"{rb['id']}: {rb['reason']}")

    dept = best_map["department"] if best_map else "GENERAL"
    action_key = {
        "EMERGENCY":   "escalate_er",
        "URGENT":      "book_today",
        "SEMI_URGENT": "book_next_available",
        "ROUTINE":     "book_normal",
    }.get(current_level, "book_normal")

    action_info = kb["actions"].get(action_key, {})

    # --- Bước 6: Gợi ý bác sĩ quen (nếu có patient_id) ---
    preferred_doctor = None
    if patient_id and current_level != "EMERGENCY":
        try:
            enc_bundle = fhir_get("Encounter", {
                "subject": f"Patient/{patient_id}",
                "_sort": "-date",
                "_count": "10",
            })
            dept_count: dict[str, int] = {}
            for e in extract_entries(enc_bundle):
                st = (e.get("serviceType") or [{}])[0]
                coding = (st.get("concept") or {}).get("coding") or [{}]
                code = (coding[0] or {}).get("code")
                if code:
                    dept_count[code] = dept_count.get(code, 0) + 1
            if dept_count:
                most_visited = max(dept_count, key=lambda k: dept_count[k])
                if most_visited == dept:
                    preferred_doctor = f"Bệnh nhân đã từng khám {dept_count[most_visited]} lần tại khoa {dept} — ưu tiên bác sĩ quen."
        except Exception:
            pass

    return {
        "urgency_level": current_level,
        "action": action_key,
        "department": dept,
        "matched_symptoms": best_map["matched_symptoms"] if best_map else [],
        "risk_boosters_applied": applied_boosters,
        "preferred_doctor_note": preferred_doctor,
        "follow_up_questions": follow_up_questions[:2],
        "message": action_info.get("message_template", ""),
        "slot_preference": action_info.get("slot_preference", "user_choice"),
        "book_appointment": action_info.get("book_appointment", True),
        "disclaimer": kb["meta"]["disclaimer"],
    }
