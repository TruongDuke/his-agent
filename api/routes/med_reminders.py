"""Route nhắc lịch uống thuốc qua email."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api import reminder_service as mr

router = APIRouter()


class ReminderItem(BaseModel):
    id: str = ""
    drug_name: str
    dose_text: str = ""
    instruction: str = ""
    times: list[str] = []
    start_date: str = ""
    end_date: str = ""
    enabled: bool = True
    sent_log: list[str] = []


class ReminderDoc(BaseModel):
    patient_name: str = ""
    email: str = ""
    items: list[ReminderItem] = []


class FromPrescriptionBody(BaseModel):
    medications: list[dict] = []
    email: str = ""
    patient_name: str = ""
    start_date: str = ""


class TestBody(BaseModel):
    item_id: str = ""


@router.get("/api/med-reminders/{patient_id}")
async def get_reminders(patient_id: str):
    return mr.load(patient_id)


@router.put("/api/med-reminders/{patient_id}")
async def put_reminders(patient_id: str, body: ReminderDoc):
    return mr.save(patient_id, body.model_dump())


@router.post("/api/med-reminders/{patient_id}/from-prescription")
async def from_prescription(patient_id: str, body: FromPrescriptionBody):
    if not body.medications:
        raise HTTPException(400, "Thiếu danh sách thuốc")
    return mr.merge_from_prescription(
        patient_id, body.medications, body.email, body.patient_name, body.start_date
    )


@router.post("/api/med-reminders/{patient_id}/test")
async def test_reminder(patient_id: str, body: TestBody):
    res = mr.send_test(patient_id, body.item_id)
    if not res.get("sent"):
        raise HTTPException(400, res.get("error") or "Gửi thử thất bại")
    return res
