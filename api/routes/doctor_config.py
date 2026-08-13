"""Route cấu hình trình bày báo cáo CBC theo từng bác sĩ."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.doctor_config import load_cbc_config, save_cbc_config

router = APIRouter()


class CbcConfigBody(BaseModel):
    length: str = "full"
    audience: str = "doctor"
    show_citations: bool = True
    show_recommended_tests: bool = True
    show_aspirin_warning: bool = True
    show_scores: bool = False
    custom_note: str = ""


@router.get("/api/doctor/{doctor_id}/cbc-config")
async def get_cbc_config(doctor_id: str):
    return load_cbc_config(doctor_id)


@router.put("/api/doctor/{doctor_id}/cbc-config")
async def put_cbc_config(doctor_id: str, body: CbcConfigBody):
    try:
        return save_cbc_config(doctor_id, body.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e))
