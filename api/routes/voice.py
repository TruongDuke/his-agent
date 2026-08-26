"""Giọng nói: chuyển tiếp sang 2 server ASR/TTS chạy cùng máy chủ.

Vì sao phải đi vòng qua backend thay vì gọi thẳng từ trình duyệt:
  - Hai server đó chạy HTTP thuần, còn trang web chạy HTTPS → trình duyệt chặn
    mixed-content.
  - Chúng không có xác thực, nên không nên để lộ địa chỉ ra phía người dùng.

Địa chỉ đọc từ biến môi trường vì trong Docker KHÔNG dùng được 127.0.0.1: nó trỏ
vào chính container. Từ container phải đi qua gateway 172.17.0.1 mới ra được host.
"""

import os

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile, Form
from fastapi.responses import Response
from pydantic import BaseModel, Field

from api.speakable import split_sentences, to_speech

router = APIRouter(prefix="/api/voice", tags=["voice"])

ASR_URL = os.getenv("ASR_URL", "http://172.17.0.1:8200").rstrip("/")
TTS_URL = os.getenv("TTS_URL", "http://172.17.0.1:8124").rstrip("/")

_MAX_AUDIO_BYTES = 10 * 1024 * 1024   # ~10 phút ghi âm 16kHz mono
_MAX_TTS_CHARS = 1000                 # câu trả lời dài hơn thì cắt, tránh chờ lâu


class TtsBody(BaseModel):
    text: str = Field(min_length=1)
    response_format: str = "mp3"       # mp3 phát thẳng được bằng thẻ <audio>
    # Câu trả lời lấy thẳng từ khung chat thì còn markdown/emoji, phải bóc trước khi
    # đọc. Đặt false khi text đã sạch (frontend gửi từng câu đã bóc sẵn).
    clean: bool = True


class SplitBody(BaseModel):
    text: str = Field(min_length=1)


@router.get("/health")
async def voice_health():
    """Cho biết hai server có sống không — đỡ phải đoán khi nút micro im lìm."""
    out = {"asr": False, "tts": False}
    async with httpx.AsyncClient(timeout=5) as client:
        for key, url in (("asr", ASR_URL), ("tts", TTS_URL)):
            try:
                r = await client.get(f"{url}/health")
                out[key] = r.status_code == 200
            except httpx.HTTPError:
                pass
    out["ready"] = out["asr"] and out["tts"]
    return out


@router.post("/stt")
async def speech_to_text(file: UploadFile = File(...), language: str = Form("vi")):
    """Ghi âm → chữ."""
    audio = await file.read()
    if not audio:
        raise HTTPException(400, "File ghi âm rỗng")
    if len(audio) > _MAX_AUDIO_BYTES:
        raise HTTPException(413, "File ghi âm quá lớn (tối đa 10MB)")

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{ASR_URL}/v1/audio/transcriptions",
                files={"file": (file.filename or "audio.wav",
                                audio, file.content_type or "audio/wav")},
                data={"language": language},
            )
    except httpx.HTTPError as e:
        raise HTTPException(503, f"Không gọi được server nhận dạng giọng nói: {e}")

    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text[:200])

    text = (r.json() or {}).get("text", "").strip()
    # ASR trả rỗng nghĩa là không nghe thấy tiếng, KHÔNG phải lỗi server — nói rõ
    # để giao diện hiện đúng thông báo thay vì báo hỏng.
    return {"text": text, "empty": not text}


@router.post("/tts")
async def text_to_speech(body: TtsBody):
    """Chữ → giọng nói."""
    text = (to_speech(body.text) if body.clean else body.text).strip()[:_MAX_TTS_CHARS]
    if not text:
        raise HTTPException(400, "Không còn chữ nào để đọc sau khi bóc định dạng")
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                f"{TTS_URL}/generate",
                json={"target_text": text, "response_format": body.response_format},
            )
    except httpx.HTTPError as e:
        raise HTTPException(503, f"Không gọi được server tổng hợp giọng nói: {e}")

    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text[:200])

    media = "audio/mpeg" if body.response_format == "mp3" else "application/octet-stream"
    # Giữ lại header mô tả audio để phía phát biết sample rate khi dùng pcm
    passthrough = {k: v for k, v in r.headers.items() if k.lower().startswith("x-audio")}
    return Response(content=r.content, media_type=media, headers=passthrough)


@router.post("/split")
async def split_for_speech(body: SplitBody):
    """Bóc markdown rồi cắt thành từng câu.

    Đọc cả câu trả lời một lần phải chờ rất lâu — đo được 306 ký tự mất 5.5 giây,
    trong khi một câu chỉ 0.6–1 giây. Frontend lấy danh sách này, đọc câu đầu ngay
    rồi vừa phát vừa sinh câu sau, nên người nghe thấy agent đáp gần như tức thì.
    """
    clean = to_speech(body.text)
    return {"clean": clean, "sentences": split_sentences(clean)}
