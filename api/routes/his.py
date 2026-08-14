"""Đầu chờ tích hợp HIS — cổng để HIS của bệnh viện đẩy dữ liệu VÀO hệ thống này.

TRẠNG THÁI: một phần đã vào bệnh án, phần còn lại mới nhận và lưu.
Hợp đồng đã chốt cho cả 5 loại bản tin: schema, xác thực, mã lỗi, chống gửi trùng.
Nhưng mới 2 loại được ánh xạ sang FHIR/Aidbox để agent đọc được:

  - patients     → Patient          (đã ánh xạ, xem api/his_mapping.py)
  - lab-results  → Observation CBC  (đã ánh xạ)
  - encounters / prescriptions / appointments → mới lưu kho tạm

Biên nhận nói rõ từng bản tin nằm ở đâu qua cờ persisted_to_fhir, thay vì để bên gửi
tự đoán. Ánh xạ hỏng cũng không làm hỏng việc tiếp nhận: bản tin vẫn nằm kho tạm và
biên nhận kèm fhir_error, xử lý lại sau được.

Xác thực: header X-HIS-API-Key, đối chiếu với biến môi trường HIS_API_KEY.
Chưa đặt HIS_API_KEY thì toàn bộ cổng đóng (503) — không mở trần cho ai gọi cũng được.
"""

import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from api import his_inbound as store
from api.his_mapping import create_lab_observation, upsert_patient

router = APIRouter(prefix="/api/his", tags=["HIS integration"])


# ─────────────────────── XÁC THỰC ───────────────────────

def require_api_key(x_his_api_key: str = Header(default="", alias="X-HIS-API-Key")) -> None:
    expected = os.getenv("HIS_API_KEY", "").strip()
    if not expected:
        raise HTTPException(503, "Chưa cấu hình HIS_API_KEY — cổng tích hợp HIS đang đóng.")
    # compare_digest: so sánh thời gian cố định, không để lộ key qua thời gian phản hồi
    if not secrets.compare_digest(x_his_api_key.strip(), expected):
        raise HTTPException(401, "X-HIS-API-Key không hợp lệ.")


# ─────────────────────── SCHEMA BẢN TIN ───────────────────────

class HisMessage(BaseModel):
    """Phần chung mọi bản tin. message_id do bên HIS sinh, phải duy nhất và giữ
    nguyên khi gửi lại — đó là căn cứ để chống ghi trùng."""
    message_id: str = Field(min_length=1, max_length=128)
    sent_at: str = ""


class HisPatient(HisMessage):
    his_patient_id: str = Field(min_length=1)
    full_name: str = ""
    birth_date: str = ""          # YYYY-MM-DD
    gender: str = ""              # male | female | other
    phone: str = ""
    email: str = ""
    address: str = ""
    insurance_no: str = ""        # số thẻ BHYT


class HisEncounter(HisMessage):
    his_encounter_id: str = Field(min_length=1)
    his_patient_id: str = Field(min_length=1)
    encounter_class: str = "outpatient"   # outpatient | inpatient | emergency
    department: str = ""
    practitioner_name: str = ""
    started_at: str = ""
    ended_at: str = ""
    reason: str = ""


class HisObservation(BaseModel):
    code: str = ""                # mã LOINC nếu HIS có
    name: str = Field(min_length=1)
    value: float | str | None = None
    unit: str = ""
    ref_range: str = ""
    abnormal_flag: str = ""       # H | L | N | ...


class HisLabResult(HisMessage):
    his_order_id: str = Field(min_length=1)
    his_patient_id: str = Field(min_length=1)
    panel: str = ""               # VD: CBC, sinh hoá máu
    resulted_at: str = ""
    observations: list[HisObservation] = []


class HisMedication(BaseModel):
    drug_name: str = Field(min_length=1)
    dose_per_intake: float = 1
    frequency_per_day: int = 1
    duration_days: int = 0
    instructions: str = ""


class HisPrescription(HisMessage):
    his_prescription_id: str = Field(min_length=1)
    his_patient_id: str = Field(min_length=1)
    prescribed_at: str = ""
    practitioner_name: str = ""
    medications: list[HisMedication] = []


class HisAppointment(HisMessage):
    his_appointment_id: str = Field(min_length=1)
    his_patient_id: str = Field(min_length=1)
    department: str = ""
    practitioner_name: str = ""
    start: str = ""               # ISO 8601
    status: str = "booked"        # booked | cancelled | fulfilled


# ─────────────────────── XỬ LÝ CHUNG ───────────────────────

async def _accept(kind: str, body: HisMessage, mapper=None) -> dict:
    """Nhận bản tin: trùng thì trả lại đúng biên nhận cũ, chưa có thì ghi mới.

    Gửi trùng KHÔNG bị coi là lỗi — vẫn trả 202 nhưng status="duplicate", để bên HIS
    biết bản tin đã vào rồi, thay vì tưởng thất bại rồi retry vô hạn.

    Loại bản tin nào đã có `mapper` thì ghi tiếp vào FHIR/Aidbox để agent đọc được;
    ánh xạ lỗi KHÔNG làm hỏng việc tiếp nhận — bản tin vẫn nằm kho tạm, biên nhận báo
    rõ persisted_to_fhir=false kèm lý do, xử lý lại sau được.
    """
    old = store.find_receipt(kind, body.message_id)
    if old:
        return {"status": "duplicate", "receipt": old}

    payload = body.model_dump()
    receipt = store.record(kind, body.message_id, payload)

    if mapper is not None:
        try:
            res = await mapper(payload)
        except Exception as e:  # noqa: BLE001 — lỗi ánh xạ không được làm hỏng tiếp nhận
            res = {"error": str(e)}
        if res.get("error"):
            receipt["fhir_error"] = res["error"]
        else:
            receipt["persisted_to_fhir"] = True
            receipt["fhir_ref"] = res.get("reference")
        store.update_receipt(kind, body.message_id, receipt)

    return {"status": "accepted", "receipt": receipt}


# ─────────────────────── ĐẦU CHỜ ───────────────────────

@router.get("/capabilities")
async def capabilities():
    """Bên HIS gọi đầu tiên để biết cổng mở những gì và đang ở trạng thái nào.
    Không cần API key — chỉ trả metadata, không có dữ liệu bệnh nhân."""
    return {
        "service": "HIS Agent — cổng tiếp nhận dữ liệu từ HIS",
        "contract_version": "1.0",
        "status": "partial",
        "note": ("Hợp đồng đã chốt cho cả 5 loại bản tin. Hiện 'patients' và 'lab-results' "
                 "được ghi thẳng vào bệnh án FHIR (agent đọc được); 3 loại còn lại mới lưu "
                 "kho tạm. Xem cờ persisted_to_fhir trong biên nhận của từng bản tin."),
        "mapped_to_fhir": ["patients", "lab-results"],
        "auth": {"type": "api_key", "header": "X-HIS-API-Key",
                 "configured": bool(os.getenv("HIS_API_KEY", "").strip())},
        "endpoints": [
            {"method": "POST", "path": "/api/his/patients",      "mô tả": "Đồng bộ hồ sơ bệnh nhân → FHIR Patient"},
            {"method": "POST", "path": "/api/his/encounters",    "mô tả": "Lượt khám / nhập viện"},
            {"method": "POST", "path": "/api/his/lab-results",   "mô tả": "Kết quả xét nghiệm → FHIR Observation"},
            {"method": "POST", "path": "/api/his/prescriptions", "mô tả": "Đơn thuốc"},
            {"method": "POST", "path": "/api/his/appointments",  "mô tả": "Lịch hẹn"},
            {"method": "GET",  "path": "/api/his/messages/{kind}", "mô tả": "Xem lại bản tin đã gửi"},
        ],
        "idempotency": "Gửi lại cùng message_id trả về đúng biên nhận cũ, không ghi thêm.",
        "counts": store.counts(),
    }


@router.post("/patients", status_code=202, dependencies=[Depends(require_api_key)])
async def receive_patient(body: HisPatient):
    return await _accept("patients", body, mapper=upsert_patient)


@router.post("/encounters", status_code=202, dependencies=[Depends(require_api_key)])
async def receive_encounter(body: HisEncounter):
    return await _accept("encounters", body)


@router.post("/lab-results", status_code=202, dependencies=[Depends(require_api_key)])
async def receive_lab_result(body: HisLabResult):
    return await _accept("lab-results", body, mapper=create_lab_observation)


@router.post("/prescriptions", status_code=202, dependencies=[Depends(require_api_key)])
async def receive_prescription(body: HisPrescription):
    return await _accept("prescriptions", body)


@router.post("/appointments", status_code=202, dependencies=[Depends(require_api_key)])
async def receive_appointment(body: HisAppointment):
    return await _accept("appointments", body)


@router.get("/messages/{kind}", dependencies=[Depends(require_api_key)])
async def list_messages(kind: str, limit: int = 20):
    """Đội HIS tự đối chiếu bản tin vừa gửi — đỡ phải hỏi qua lại lúc tích hợp."""
    if kind not in store.KINDS:
        raise HTTPException(404, f"Loại bản tin không hợp lệ. Hợp lệ: {', '.join(store.KINDS)}")
    return {"kind": kind, "items": store.recent(kind, max(1, min(limit, 100)))}
