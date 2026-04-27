"""Verify patient identity before booking — match name with year_of_birth or BHYT.

Use this BEFORE fhir_create_appointment to ensure the right patient is being booked.

Logic:
  - Search by name → get candidates
  - 0 candidates → patient_not_found, suggest registration
  - 1 candidate → verify match with year_of_birth or BHYT → return verified
  - Multiple candidates → need year_of_birth or BHYT to disambiguate
"""

TOOL_NAME = "fhir_verify_patient"
CATEGORY = "Healthcare"
DESCRIPTION = (
    "Xác thực danh tính bệnh nhân trước khi đặt lịch. "
    "Input: name (họ tên đầy đủ), year_of_birth (năm sinh, 4 chữ số) HOẶC bhyt (số BHYT). "
    "Cần ít nhất 1 trong 2 thông tin để xác thực. "
    "Trả về status: 'verified' (đã match), 'not_found' (không có BN, cần đăng ký), "
    "'multiple_candidates' (cần thêm thông tin), 'mismatch' (tên đúng nhưng DOB/BHYT sai)."
)
ARGS_SCHEMA = {
    "name":           "string — họ tên đầy đủ bệnh nhân (VD: 'Nguyễn Văn A')",
    "year_of_birth":  "string (tùy chọn) — năm sinh 4 chữ số (VD: '1967'). Bắt buộc NẾU không có bhyt",
    "bhyt":           "string (tùy chọn) — số BHYT (VD: 'HS4010234567890'). Bắt buộc NẾU không có year_of_birth",
}


def run(args: dict) -> dict:
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from _aidbox_client import fhir_get, extract_entries, patient_summary

    name = str(args.get("name") or "").strip()
    yob = str(args.get("year_of_birth") or "").strip()
    bhyt = str(args.get("bhyt") or "").strip()

    if not name:
        return {"status": "error", "error": "name is required"}
    if not yob and not bhyt:
        return {"status": "error", "error": "Cần ít nhất 1 trong 2: year_of_birth hoặc bhyt"}

    # Search by name (family + given heuristic)
    tokens = name.split()
    if len(tokens) == 1:
        search_params = {"family": tokens[0]}
    else:
        search_params = {"family": tokens[0], "given": " ".join(tokens[1:])}

    bundle = fhir_get("Patient", search_params)
    if isinstance(bundle, dict) and "error" in bundle:
        return {"status": "error", **bundle}

    candidates = extract_entries(bundle)

    if not candidates:
        return {
            "status": "not_found",
            "message": (
                f"Không tìm thấy bệnh nhân tên '{name}' trong hệ thống. "
                "Có thể đây là bệnh nhân mới chưa có hồ sơ."
            ),
            "instruction_for_agent": "BN chưa có hồ sơ. Gọi fhir_direct_to_registration để hướng dẫn BN đến quầy đăng ký.",
        }

    # Filter candidates by year_of_birth / bhyt
    matched = []
    for p in candidates:
        match_score = 0
        reasons = []

        if yob:
            birth = (p.get("birthDate") or "")[:4]
            if birth == yob:
                match_score += 1
                reasons.append(f"năm sinh khớp ({yob})")

        if bhyt:
            identifiers = p.get("identifier", []) or []
            p_bhyt = next((i.get("value") for i in identifiers if "bhyt" in (i.get("system") or "")), "")
            if p_bhyt == bhyt:
                match_score += 2  # BHYT is unique, highest confidence
                reasons.append(f"BHYT khớp ({bhyt})")

        if match_score > 0:
            matched.append((match_score, p, reasons))

    # Decision
    if not matched:
        # Name found but DOB/BHYT doesn't match any candidate
        return {
            "status": "mismatch",
            "candidates_count": len(candidates),
            "message": (
                f"Có {len(candidates)} bệnh nhân tên '{name}' nhưng không ai khớp với "
                f"{'năm sinh ' + yob if yob else ''}"
                f"{' và ' if yob and bhyt else ''}"
                f"{'BHYT ' + bhyt if bhyt else ''}. "
                "Kiểm tra lại thông tin hoặc hỏi BN xác nhận lại."
            ),
            "instruction_for_agent": "Thông tin không khớp. Hỏi BN kiểm tra lại năm sinh hoặc BHYT. KHÔNG gọi create_appointment.",
        }

    if len(matched) == 1:
        score, patient, reasons = matched[0]
        summary = patient_summary(patient)
        return {
            "status": "verified",
            "confidence": "high" if score >= 2 else "medium",
            "match_reasons": reasons,
            "patient": summary,
            "message": f"Đã xác thực: {summary['name']} ({', '.join(reasons)})",
            "instruction_for_agent": (
                f"XÁC THỰC THÀNH CÔNG. Bệnh nhân là {summary['name']}, "
                f"sinh {summary.get('birth_date','?')}, BHYT {summary.get('bhyt','?')}. "
                "KHÔNG được hỏi thêm BHYT hay thông tin khác — đã verified. "
                "Bước tiếp: hỏi BN muốn khám giờ nào, rồi gọi fhir_get_available_slots + fhir_create_appointment."
            ),
        }

    # Multiple candidates match (rare — e.g., same name + year_of_birth)
    return {
        "status": "multiple_candidates",
        "candidates_count": len(matched),
        "candidates": [patient_summary(p) for _, p, _ in matched[:5]],
        "message": (
            f"Có {len(matched)} bệnh nhân khớp. "
            "Cần thêm BHYT hoặc thông tin khác để xác định chính xác."
        ),
        "instruction_for_agent": "Có nhiều BN khớp. Hỏi BN cung cấp BHYT hoặc ngày sinh đầy đủ để phân biệt.",
    }
