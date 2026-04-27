"""Register a new patient (create Patient resource) when they don't exist yet.

Called after fhir_verify_patient returns status='not_found' AND the patient
wants to self-register via the AI instead of going to the front desk.

Creates Patient with extension `registration_status: pending_verification` —
staff at the hospital will verify CCCD + BHYT when patient physically arrives.
"""

TOOL_NAME = "fhir_register_new_patient"
CATEGORY = "Healthcare"
DESCRIPTION = (
    "Tạo hồ sơ bệnh nhân mới trong hệ thống khi BN chưa có. "
    "Chỉ dùng khi fhir_verify_patient trả 'not_found' VÀ BN đồng ý tự đăng ký. "
    "Cần 4 field bắt buộc: full_name, date_of_birth (YYYY-MM-DD), gender (male/female), phone. "
    "Optional: bhyt, cccd, address_city. "
    "Sau khi tạo xong, agent tiếp tục flow đặt lịch với patient_id mới."
)
ARGS_SCHEMA = {
    "full_name":     "string — họ tên đầy đủ (VD: 'Nguyễn Văn An')",
    "date_of_birth": "string — ngày sinh YYYY-MM-DD (VD: '1985-03-15')",
    "gender":        "string — 'male' hoặc 'female'",
    "phone":         "string — số điện thoại (10-11 chữ số, bắt đầu bằng 0)",
    "bhyt":          "string (tùy chọn) — số BHYT (format HS4xxx, 15 ký tự)",
    "cccd":          "string (tùy chọn) — số CCCD 12 chữ số",
    "address_city":  "string (tùy chọn) — thành phố (VD: 'Hà Nội')",
}


def _validate(args: dict) -> str | None:
    """Return error message if invalid, None if OK."""
    import re
    from datetime import date

    full_name = str(args.get("full_name") or "").strip()
    dob = str(args.get("date_of_birth") or "").strip()
    _gender_raw = str(args.get("gender") or "").strip().lower()
    _gender_alias = {"nữ": "female", "nu": "female", "f": "female", "woman": "female",
                     "nam": "male", "m": "male", "man": "male"}
    gender = _gender_alias.get(_gender_raw, _gender_raw)
    phone = str(args.get("phone") or "").strip()
    bhyt = str(args.get("bhyt") or "").strip()
    cccd = str(args.get("cccd") or "").strip()

    # Required fields
    if not full_name or len(full_name.split()) < 2:
        return "full_name phải có ít nhất 2 từ (họ + tên), VD: 'Nguyễn Văn A'"

    if not dob:
        return "date_of_birth bắt buộc (YYYY-MM-DD)"
    try:
        d = date.fromisoformat(dob)
        if d > date.today():
            return f"date_of_birth không được ở tương lai (nhập {dob})"
        if d.year < 1900:
            return f"date_of_birth không hợp lệ ({dob})"
    except ValueError:
        return f"date_of_birth sai format, cần YYYY-MM-DD (VD: 1985-03-15). Nhận: '{dob}'"

    if gender not in ("male", "female"):
        return f"gender phải là 'male' hoặc 'female' (hoặc 'nam'/'nữ'), nhận '{_gender_raw}'"

    if not phone or not re.fullmatch(r"0\d{9,10}", phone):
        return f"phone phải là 10-11 chữ số bắt đầu bằng 0 (VD: 0912345678). Nhận: '{phone}'"

    # Optional validation
    if bhyt and not re.fullmatch(r"HS4\d{12}", bhyt):
        return f"bhyt sai format, cần HS4 + 12 chữ số (VD: HS4010234567890). Nhận: '{bhyt}'"

    if cccd and not re.fullmatch(r"\d{12}", cccd):
        return f"cccd phải là 12 chữ số. Nhận: '{cccd}'"

    return None


def run(args: dict) -> dict:
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from _aidbox_client import _config, patient_summary
    import httpx

    err = _validate(args)
    if err:
        return {
            "status": "invalid_input",
            "error": err,
            "instruction_for_agent": f"Input không hợp lệ: {err}. Hỏi lại BN thông tin đúng format.",
        }

    full_name = str(args["full_name"]).strip()
    name_parts = full_name.split()
    family = name_parts[0]
    given = " ".join(name_parts[1:])

    dob = str(args["date_of_birth"]).strip()
    gender = str(args["gender"]).strip().lower()
    phone = str(args["phone"]).strip()
    bhyt = str(args.get("bhyt") or "").strip()
    cccd = str(args.get("cccd") or "").strip()
    city = str(args.get("address_city") or "").strip()

    # Build Patient resource
    identifiers = []
    if bhyt:
        identifiers.append({"system": "urn:vn:bhyt", "value": bhyt})
    if cccd:
        identifiers.append({"system": "urn:vn:cccd", "value": cccd})

    patient = {
        "resourceType": "Patient",
        "name": [{"use": "official", "family": family, "given": [given]}],
        "gender": gender,
        "birthDate": dob,
        "telecom": [{"system": "phone", "value": phone}],
        "extension": [{
            "url": "urn:vn:registration-status",
            "valueString": "pending_verification",
        }],
    }
    if identifiers:
        patient["identifier"] = identifiers
    if city:
        patient["address"] = [{"use": "home", "city": city, "country": "VN"}]

    url, cid, sec = _config()
    if not url:
        return {"status": "error", "error": "AIDBOX_URL not configured"}
    auth = (cid, sec) if cid and sec else None

    try:
        with httpx.Client(timeout=15, auth=auth) as client:
            r = client.post(f"{url}/fhir/Patient", json=patient)
            if not (200 <= r.status_code < 300):
                return {
                    "status": "error",
                    "error": f"Tạo hồ sơ thất bại HTTP {r.status_code}: {r.text[:200]}",
                }
            created = r.json()
    except Exception as e:
        return {"status": "error", "error": f"Request failed: {e}"}

    summary = patient_summary(created)

    return {
        "status": "registered",
        "patient_id": created.get("id"),
        "patient": summary,
        "message": (
            f"Đã tạo hồ sơ mới cho {summary['name']}. "
            f"BN mang theo CCCD + BHYT đến quầy lễ tân khi đến khám để xác minh giấy tờ."
        ),
        "instruction_for_agent": (
            f"ĐÃ TẠO HỒ SƠ MỚI. Bệnh nhân: {summary['name']}, patient_id={created.get('id')}. "
            "KHÔNG hỏi lại thông tin cá nhân. "
            "Bước tiếp: hỏi BN muốn khám giờ nào (khoa + ngày), rồi gọi fhir_get_available_slots + fhir_create_appointment. "
            "Cuối cùng nhắc BN mang CCCD+BHYT khi đến khám để xác minh giấy tờ."
        ),
        "verification_note": "Hồ sơ có status 'pending_verification' — cần xác minh giấy tờ tại quầy khi đến khám.",
    }
