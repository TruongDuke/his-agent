"""Suggest which hospital department fits the patient's symptoms + history."""
from __future__ import annotations


TOOL_NAME = "fhir_suggest_department"
CATEGORY = "Healthcare"
DESCRIPTION = (
    "Gợi ý khoa khám phù hợp dựa trên triệu chứng của bệnh nhân. "
    "Dùng RAG (semantic search) để hiểu ngữ nghĩa triệu chứng — không cần gõ đúng từ khóa. "
    "Nếu có patient_id, tool sẽ đọc lịch sử và ưu tiên khoa mà bệnh nhân đã từng khám. "
    "Trả về top-3 khoa với lý do + thông tin GIÁO DỤC về các bệnh thường gặp ở khoa đó. "
    "KHÔNG phải chẩn đoán y khoa — chỉ gợi ý định tuyến + thông tin tham khảo."
)
ARGS_SCHEMA = {
    "symptoms": "string — mô tả triệu chứng (VD: 'tim đập loạn, mệt khi leo cầu thang')",
    "patient_id": "string (optional) — UUID bệnh nhân để boost ưu tiên theo lịch sử khám",
}

# Educational info per department — framing mềm, không chẩn đoán (Google Health style)
_COMMON_CONDITIONS = {
    "CARDIO":  "các bệnh tim mạch như tăng huyết áp, đau thắt ngực, nhồi máu cơ tim, rối loạn nhịp tim",
    "ENDO":    "các rối loạn nội tiết như tiểu đường, bệnh tuyến giáp, rối loạn chuyển hóa",
    "ENT":     "viêm xoang, viêm họng, viêm tai giữa, rối loạn tiền đình",
    "NEURO":   "đau đầu migraine, mất ngủ, tê yếu tay chân, rối loạn lo âu, trầm cảm",
    "GASTRO":  "viêm dạ dày, trào ngược thực quản, hội chứng ruột kích thích, viêm đại tràng",
    "RHEUMA":  "gout, thoái hóa khớp, viêm khớp dạng thấp, đau lưng cơ năng",
    "OBGYN":   "các vấn đề thai sản, phụ khoa, rối loạn kinh nguyệt",
    "PEDIAT":  "bệnh lý trẻ em: sốt siêu vi, viêm phổi, tiêu chảy, các bệnh lý phát triển",
    "DERMA":   "eczema, vảy nến, dị ứng da, nấm da, mụn trứng cá",
    "OPHTHAL": "tật khúc xạ (cận/viễn/loạn), đục thủy tinh thể, viêm kết mạc",
    "UROLOGY": "sỏi thận, nhiễm trùng đường tiết niệu, suy thận mãn",
    "GENERAL": "các bệnh lý nội khoa chung, chưa rõ nguyên nhân cần sàng lọc",
    "SURGERY": "các bệnh lý cần phẫu thuật: ruột thừa, thoát vị, khối u, chấn thương",
    "DENTAL":  "sâu răng, viêm nướu, răng khôn, các bệnh lý răng miệng",
    "PULMO":   "hen suyễn, COPD, viêm phổi, lao phổi, các bệnh hô hấp mãn tính",
    "ORTHO":   "gãy xương, chấn thương thể thao, thoát vị đĩa đệm, đau cột sống",
    "EMERG":   "các tình huống cấp cứu cần can thiệp ngay",
}


def run(args: dict) -> dict:
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from _aidbox_client import fhir_get, extract_entries
    from _rag_departments import retrieve_departments

    symptoms = str(args.get("symptoms") or "").strip()
    pid = str(args.get("patient_id") or "").strip()
    if not symptoms:
        return {"error": "symptoms is required"}

    symptoms_lower = symptoms.lower()

    # Emergency keywords — short-circuit before RAG
    emergency_triggers = [
        "đau ngực dữ dội", "khó thở nặng", "mất ý thức", "bất tỉnh",
        "chảy máu nhiều", "xuất huyết", "co giật liên tục", "đột quỵ",
        "ngộ độc", "tai nạn nặng", "chấn thương nặng", "sốc phản vệ",
    ]
    for trg in emergency_triggers:
        if trg in symptoms_lower:
            return {
                "emergency": True,
                "message": f"Triệu chứng '{trg}' có dấu hiệu cấp cứu. GỌI NGAY 115 hoặc đưa bệnh nhân đến Khoa Cấp cứu.",
                "department": {"code": "EMERG", "name": "Khoa Cấp cứu"},
            }

    # RAG retrieval
    rag_results = retrieve_departments(symptoms, top_k=3)

    # Fetch patient history for boost
    history_depts: list[str] = []
    history_conditions: list[str] = []
    if pid:
        try:
            enc_bundle = fhir_get("Encounter", {"subject": f"Patient/{pid}", "_sort": "-date", "_count": "5"})
            for e in extract_entries(enc_bundle):
                st = e.get("serviceType") or []
                if st and isinstance(st[0], dict):
                    concept = st[0].get("concept") or {}
                    coding = (concept.get("coding") or [{}])[0]
                    code = coding.get("code")
                    if code:
                        history_depts.append(code)
            cond_bundle = fhir_get("Condition", {"subject": f"Patient/{pid}"})
            for c in extract_entries(cond_bundle):
                text = (c.get("code") or {}).get("text")
                if text:
                    history_conditions.append(text)
        except Exception:
            pass

    # Fallback if RAG returned nothing
    if not rag_results:
        return {
            "emergency": False,
            "suggestions": [{
                "code": "GENERAL",
                "name": "Khoa Nội Tổng Quát",
                "reason": "Không xác định được khoa chuyên sâu từ triệu chứng → khám tổng quát để sàng lọc.",
                "common_conditions_info": _COMMON_CONDITIONS.get("GENERAL", ""),
            }],
            "patient_history_used": bool(pid),
            "history_conditions": history_conditions,
            "disclaimer": "Đây chỉ là gợi ý định tuyến khoa, không phải chẩn đoán. Bác sĩ sẽ khám và xác định bệnh chính xác.",
        }

    # Apply history boost and build response
    suggestions = []
    for dept in rag_results:
        boosted = dept["code"] in history_depts
        reason_parts = [f"Triệu chứng khớp với {dept['name']} (độ phù hợp: {dept['score']:.2f})"]
        if boosted:
            reason_parts.append("Bệnh nhân có lịch sử khám khoa này")
        suggestions.append({
            "code": dept["code"],
            "name": dept["name"],
            "score": round(dept["score"] + (0.5 if boosted else 0), 2), # cộng 0.5 nếu có lịch sử khám khoa này
            "history_boost": boosted,
            "reason": ". ".join(reason_parts),
            "common_conditions_info": (
                f"Triệu chứng này thường liên quan đến {_COMMON_CONDITIONS.get(dept['code'], 'các bệnh thuộc khoa này')}. "
                "Bác sĩ sẽ khám và đưa ra chẩn đoán chính xác."
            ),
        })

    suggestions.sort(key=lambda d: d["score"], reverse=True)

    return {
        "emergency": False,
        "suggestions": suggestions,
        "patient_history_used": bool(pid),
        "history_conditions": history_conditions if pid else [],
        "disclaimer": "Đây chỉ là gợi ý định tuyến khoa, không phải chẩn đoán. Bác sĩ sẽ khám và xác định bệnh chính xác.",
    }
