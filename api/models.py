"""Pydantic request/response models for HIS Agent API."""

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    role: str = "patient"
    doctor_name: str = ""
    doctor_id: str = ""
    image_base64: str = ""
    image_mime: str = "image/jpeg"


class ChatResponse(BaseModel):
    reply: str
    session_id: str
