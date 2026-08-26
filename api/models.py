"""Pydantic request/response models for HIS Agent API."""

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    role: str = "patient"
    doctor_name: str = ""
    doctor_id: str = ""
    patient_id: str = ""
    patient_name: str = ""
    image_base64: str = ""
    image_mime: str = "image/jpeg"
    # Đang nói chuyện bằng giọng nói: câu trả lời sẽ bị đọc thành tiếng nên phải ngắn.
    # Đo được TTS mất ~18ms/ký tự — trả lời 800 ký tự là đọc gần 15 giây, không ai chờ.
    voice_mode: bool = False


class ChatResponse(BaseModel):
    reply: str
    session_id: str
