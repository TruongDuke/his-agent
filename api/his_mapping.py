"""Ánh xạ bản tin HIS gửi sang thành tài nguyên FHIR trong Aidbox.

Đây là phần biến đầu chờ từ "nhận rồi để đó" thành "vào được bệnh án", nhờ vậy
agent đọc và suy luận trên dữ liệu bệnh viện khác đẩy sang bằng đúng các tool sẵn có
(fhir_search_patient, fhir_get_cbc, dengue_cbc_predict...).

Hiện ánh xạ 2 trong 5 loại bản tin:
  - patients     → Patient
  - lab-results  → Observation (CBC panel, LOINC 58410-2)
Ba loại còn lại (encounters, prescriptions, appointments) vẫn chỉ lưu kho tạm.

Định danh chéo: mọi tài nguyên tạo từ đây đều gắn identifier hệ thống
HIS_IDENTIFIER_SYSTEM, vừa để đẩy lại không tạo bản ghi trùng, vừa để lọc ra dọn dẹp.
"""
from __future__ import annotations

import httpx

from api.deps import _aidbox

HIS_IDENTIFIER_SYSTEM = "urn:his-agent:external-his"

# Đơn vị của từng chỉ số CBC theo UCUM — bên HIS gửi "10^9/L" hay "10*3/uL" đều quy về
# một dạng để tool đọc CBC không phải đoán. Hai đơn vị này cùng trị số nên không đổi value.
_UCUM = {
    "718-7":  ("g/dL",      "g/dL"),
    "4544-3": ("%",         "%"),
    "6690-2": ("10*3/uL",   "10*3/uL"),
    "777-3":  ("10*3/uL",   "10*3/uL"),
}

_DISPLAY = {
    "718-7":  "Hemoglobin",
    "4544-3": "Hematocrit",
    "6690-2": "WBC",
    "777-3":  "Platelets",
}


def _split_name(full_name: str) -> tuple[str, list[str]]:
    """'Trần Thị Hoa' → family 'Trần', given ['Thị', 'Hoa'] — theo đúng quy ước
    đang dùng ở /api/register-patient để tên hiển thị ra không bị đảo."""
    parts = (full_name or "").strip().split()
    if not parts:
        return "", []
    return parts[0], parts[1:]


async def _find_by_identifier(client: httpx.AsyncClient, url: str,
                              rtype: str, value: str) -> str | None:
    r = await client.get(f"{url}/fhir/{rtype}",
                         params={"identifier": f"{HIS_IDENTIFIER_SYSTEM}|{value}", "_count": "1"})
    if r.status_code != 200:
        return None
    entries = r.json().get("entry") or []
    return entries[0]["resource"]["id"] if entries else None


async def upsert_patient(payload: dict) -> dict:
    """Tạo Patient, hoặc trả về Patient đã tạo từ lần đẩy trước."""
    url, auth = _aidbox()
    if not url:
        return {"error": "AIDBOX_URL chưa cấu hình"}

    his_id = str(payload.get("his_patient_id") or "").strip()
    if not his_id:
        return {"error": "thiếu his_patient_id"}

    family, given = _split_name(payload.get("full_name", ""))
    telecom = []
    if payload.get("phone"):
        telecom.append({"system": "phone", "value": payload["phone"], "use": "mobile"})
    if payload.get("email"):
        telecom.append({"system": "email", "value": payload["email"]})

    identifiers = [{"system": HIS_IDENTIFIER_SYSTEM, "value": his_id}]
    # Số thẻ BHYT bên HIS gửi sang phải vào đúng hệ định danh mà cả hệ thống đang dùng,
    # không thì bác sĩ tra bằng số thẻ sẽ không ra bệnh nhân này.
    if payload.get("insurance_no"):
        identifiers.append({"system": "urn:vn:bhyt", "value": str(payload["insurance_no"]).strip()})

    resource: dict = {
        "resourceType": "Patient",
        "identifier": identifiers,
        "name": [{"use": "official", "family": family, "given": given}],
    }
    if payload.get("gender") in ("male", "female", "other", "unknown"):
        resource["gender"] = payload["gender"]
    if payload.get("birth_date"):
        resource["birthDate"] = payload["birth_date"][:10]
    if telecom:
        resource["telecom"] = telecom
    if payload.get("address"):
        resource["address"] = [{"use": "home", "text": payload["address"]}]

    async with httpx.AsyncClient(timeout=20, auth=auth) as client:
        existing = await _find_by_identifier(client, url, "Patient", his_id)
        if existing:
            # Đẩy lại cùng bệnh nhân → cập nhật, KHÔNG tạo hồ sơ thứ hai.
            r = await client.put(f"{url}/fhir/Patient/{existing}", json={**resource, "id": existing})
            if not (200 <= r.status_code < 300):
                return {"error": f"cập nhật Patient lỗi HTTP {r.status_code}"}
            return {"reference": f"Patient/{existing}", "created": False}

        r = await client.post(f"{url}/fhir/Patient", json=resource)
        if not (200 <= r.status_code < 300):
            return {"error": f"tạo Patient lỗi HTTP {r.status_code}: {r.text[:150]}"}
        return {"reference": f"Patient/{r.json().get('id')}", "created": True}


async def create_lab_observation(payload: dict) -> dict:
    """Dựng CBC panel Observation gắn vào Patient tương ứng.

    Bệnh nhân phải được đẩy sang trước — không tự bịa hồ sơ từ một phiếu xét nghiệm,
    vì không có đủ thông tin định danh và dễ tạo hồ sơ ma.
    """
    url, auth = _aidbox()
    if not url:
        return {"error": "AIDBOX_URL chưa cấu hình"}

    his_pid = str(payload.get("his_patient_id") or "").strip()
    order_id = str(payload.get("his_order_id") or "").strip()

    components = []
    for obs in payload.get("observations") or []:
        loinc = str(obs.get("code") or "").strip()
        value = obs.get("value")
        if loinc not in _UCUM or not isinstance(value, (int, float)):
            continue  # chỉ số ngoài bộ CBC hoặc giá trị không phải số → bỏ qua
        unit, ucum = _UCUM[loinc]
        components.append({
            "code": {"coding": [{"system": "http://loinc.org", "code": loinc,
                                 "display": _DISPLAY.get(loinc, obs.get("name", ""))}]},
            "valueQuantity": {"value": float(value), "unit": unit,
                              "system": "http://unitsofmeasure.org", "code": ucum},
        })

    if not components:
        return {"error": "không có chỉ số CBC nào nhận diện được"}

    async with httpx.AsyncClient(timeout=20, auth=auth) as client:
        pid = await _find_by_identifier(client, url, "Patient", his_pid)
        if not pid:
            return {"error": f"chưa có bệnh nhân {his_pid} — đẩy bản tin patients trước"}

        if order_id:
            existing = await _find_by_identifier(client, url, "Observation", order_id)
            if existing:
                return {"reference": f"Observation/{existing}", "created": False}

        observation = {
            "resourceType": "Observation",
            "status": "final",
            "identifier": ([{"system": HIS_IDENTIFIER_SYSTEM, "value": order_id}] if order_id else []),
            "category": [{"coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                "code": "laboratory"}]}],
            "code": {"coding": [{"system": "http://loinc.org", "code": "58410-2",
                                 "display": "CBC panel"}]},
            "subject": {"reference": f"Patient/{pid}"},
            "component": components,
        }
        if payload.get("resulted_at"):
            observation["effectiveDateTime"] = payload["resulted_at"]

        r = await client.post(f"{url}/fhir/Observation", json=observation)
        if not (200 <= r.status_code < 300):
            return {"error": f"tạo Observation lỗi HTTP {r.status_code}: {r.text[:150]}"}
        return {"reference": f"Observation/{r.json().get('id')}",
                "created": True, "patient": f"Patient/{pid}"}
