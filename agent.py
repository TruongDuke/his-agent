"""HIS Agent — tool-calling loop (OpenAI-compatible SDK, works with OpenRouter)."""

from __future__ import annotations
import importlib, os, sys, json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import base64, io
import httpx
from openai import OpenAI
from system_prompt import (
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_DOCTOR,
    SYSTEM_PROMPT_DOCTOR_RECORDS,
    SYSTEM_PROMPT_DOCTOR_CBC,
    SYSTEM_PROMPT_DOCTOR_APPOINTMENTS,
)

# Thêm shared/ vào path để các tool import _aidbox_client, _rag_departments
sys.path.insert(0, str(Path(__file__).parent / "tools" / "shared"))

# Settings inject vào tools có SETTINGS_KEYS (gmail, v.v.)
def _get_settings() -> dict:
    return {
        "gmail_user":         os.getenv("GMAIL_USER", ""),
        "gmail_app_password": os.getenv("GMAIL_APP_PASSWORD", ""),
        "gmail_from_name":    os.getenv("GMAIL_FROM_NAME", "Bệnh viện Đa khoa Hà Nội"),
    }


def _load_tool_modules() -> dict[str, Any]:
    """Load tất cả fhir_* và dengue_* tools, trả về dict name → module."""
    modules = {}
    tools_dir = Path(__file__).parent / "tools"
    subpackages = {"fhir": "fhir_*.py", "dengue": "dengue_*.py"}
    seen = set()
    for pkg, pattern in subpackages.items():
        for path in sorted((tools_dir / pkg).glob(pattern)):
            if path.stem in seen:
                continue
            seen.add(path.stem)
            mod_name = f"tools.{pkg}.{path.stem}"
            mod = importlib.import_module(mod_name)
            if hasattr(mod, "TOOL_NAME") and hasattr(mod, "run"):
                modules[mod.TOOL_NAME] = mod
    return modules


def _infer_param_schema(desc: str) -> dict:
    """Suy ra JSON Schema từ prefix của description."""
    low = desc.lower().lstrip()
    if low.startswith("array"):
        return {"type": "array", "items": {"type": "string"}, "description": desc}
    if low.startswith("boolean"):
        return {"type": "boolean", "description": desc}
    if low.startswith("number") or low.startswith("integer"):
        return {"type": "number", "description": desc}
    return {"type": "string", "description": desc}


def _build_openai_tools(modules: dict) -> list[dict]:
    """Chuyển ARGS_SCHEMA của tool sang format OpenAI function calling."""
    result = []
    for name, mod in modules.items():
        schema = getattr(mod, "ARGS_SCHEMA", {})
        properties = {}
        for param, desc in schema.items():
            properties[param] = _infer_param_schema(desc)
        result.append({
            "type": "function",
            "function": {
                "name": name,
                "description": getattr(mod, "DESCRIPTION", ""),
                "parameters": {
                    "type": "object",
                    "properties": properties,
                },
            },
        })
    return result


def _execute_tool(name: str, args: dict, modules: dict) -> str:
    """Gọi tool và trả về kết quả dạng string."""
    mod = modules.get(name)
    if not mod:
        return json.dumps({"error": f"Tool '{name}' không tồn tại"})

    # Inject settings nếu tool cần
    settings_keys = getattr(mod, "SETTINGS_KEYS", [])
    if settings_keys:
        all_settings = _get_settings()
        args["_settings"] = {k: all_settings.get(k) for k in settings_keys}

    try:
        result = mod.run(args)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


# Cache modules + tools để không reload mỗi request
_MODULES = _load_tool_modules()
_TOOLS   = _build_openai_tools(_MODULES)

# Tool set cho từng role — None = dùng tất cả
_TOOLS_BY_ROLE: dict[str, list[str] | None] = {
    "patient": [
        "fhir_triage_assessment", "fhir_suggest_department",
        "fhir_register_new_patient", "fhir_get_next_available_slot", "fhir_get_available_slots",
        "fhir_create_appointment", "fhir_cancel_appointment", "fhir_get_patient_appointments",
        "fhir_get_patient_history", "fhir_get_observations",
        "fhir_get_clinical_impressions",
        "fhir_get_allergies", "fhir_get_prescriptions",
        "dengue_symptom_assessment", "dengue_cbc_predict",
    ],
    "doctor": None,
    "doctor_records": [
        "fhir_search_patient", "fhir_get_patient_history", "fhir_get_observations",
        "fhir_get_clinical_impressions",
        "fhir_get_doctor_schedule", "fhir_suggest_doctor", "fhir_get_available_slots",
        "fhir_get_patient_appointments",
    ],
    "doctor_cbc": [
        "fhir_search_patient", "fhir_create_cbc", "fhir_get_cbc",
        "fhir_get_next_available_slot", "fhir_create_appointment",
    ],
    "doctor_appointments": [
        "fhir_get_pending_appointments", "fhir_confirm_appointment",
        "fhir_reject_appointment", "fhir_get_doctor_schedule",
    ],
}


def _get_tools_for_role(role: str) -> list[dict]:
    allowed = _TOOLS_BY_ROLE.get(role)
    if allowed is None:
        return _TOOLS
    return [t for t in _TOOLS if t["function"]["name"] in allowed]

_OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
_ALIBABA_KEY    = os.getenv("ALIBABA_API_KEY", "")
_LLM_TIMEOUT = httpx.Timeout(60.0, connect=10.0)  # 60s read, 10s connect

if _ALIBABA_KEY:
    _CLIENT = OpenAI(
        api_key=_ALIBABA_KEY,
        base_url=os.getenv("ALIBABA_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
        timeout=_LLM_TIMEOUT,
    )
    _MODEL = os.getenv("ALIBABA_MODEL", "qwen-plus")
elif _OPENROUTER_KEY:
    _CLIENT = OpenAI(
        api_key=_OPENROUTER_KEY,
        base_url="https://openrouter.ai/api/v1",
        timeout=_LLM_TIMEOUT,
    )
    _MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-haiku-4-5")
else:
    _CLIENT = OpenAI(
        api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        base_url="https://api.anthropic.com/v1/",
        timeout=_LLM_TIMEOUT,
    )
    _MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")


_TOOL_LABELS = {
    "fhir_triage_assessment":      "Đang đánh giá triệu chứng...",
    "fhir_suggest_department":     "Đang gợi ý khoa khám...",
    "fhir_search_patient":         "Đang tìm hồ sơ bệnh nhân...",
    "fhir_get_available_slots":    "Đang kiểm tra lịch trống...",
    "fhir_get_next_available_slot":"Đang tìm slot sớm nhất...",
    "fhir_create_appointment":     "Đang đặt lịch hẹn...",
    "fhir_register_new_patient":   "Đang đăng ký bệnh nhân mới...",
    "fhir_get_patient_history":    "Đang tra cứu lịch sử khám...",
    "fhir_get_observations":           "Đang lấy kết quả xét nghiệm...",
    "fhir_get_clinical_impressions":   "Đang lấy ghi chú lâm sàng...",
    "fhir_get_doctor_schedule":    "Đang xem lịch khám...",
    "fhir_cancel_appointment":     "Đang hủy lịch hẹn...",
    "fhir_get_patient_appointments":  "Đang kiểm tra lịch hẹn...",
    "dengue_symptom_assessment":      "Đang phân loại mức độ sốt xuất huyết...",
    "dengue_cbc_predict":             "Đang phân tích chỉ số CBC...",
}


def _find_last_slot_id(history: list) -> str | None:
    """Tìm slot_id từ kết quả fhir_get_next_available_slot gần nhất trong history."""
    for msg in reversed(history):
        if msg.get("role") != "tool":
            continue
        try:
            r = json.loads(msg["content"])
            if r.get("found") and r.get("slot_id"):
                return r["slot_id"]
        except Exception:
            pass
    return None


def _strip_images(history: list[dict]) -> list[dict]:
    """Replace multipart messages containing image_url with text-only version."""
    result = []
    for msg in history:
        content = msg.get("content")
        if isinstance(content, list):
            texts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
            clean = dict(msg)
            clean["content"] = " ".join(texts) if texts else "[ảnh]"
            result.append(clean)
        else:
            result.append(msg)
    return result


def _trim_history(history: list[dict], max_messages: int = 24) -> list[dict]:
    """Giữ tối đa max_messages tin nhắn gần nhất, strip ảnh khỏi history cũ."""
    cleaned = _strip_images(history)
    if len(cleaned) <= max_messages:
        trimmed = cleaned
    else:
        trimmed = cleaned[-max_messages:]
    # First non-system message must be user role
    while trimmed and trimmed[0].get("role") != "user":
        trimmed = trimmed[1:]
    roles = [m.get("role") for m in trimmed]
    print(f"[TRIM] history={len(history)} trimmed={len(trimmed)} roles={roles}", flush=True)
    return trimmed


def _normalize_image(image_base64: str, image_mime: str = "image/jpeg") -> tuple[str, str]:
    """Convert any image or PDF (page 1) to PNG ≤512px for API compatibility."""
    try:
        from PIL import Image
        raw = base64.b64decode(image_base64)
        if image_mime == "application/pdf" or raw[:4] == b"%PDF":
            import fitz
            doc = fitz.open(stream=raw, filetype="pdf")
            pix = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2))
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        else:
            img = Image.open(io.BytesIO(raw)).convert("RGB")
        max_px = 512
        w, h = img.size
        if w > max_px or h > max_px:
            ratio = min(max_px / w, max_px / h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        result = base64.b64encode(buf.getvalue()).decode()
        print(f"[IMG] OK size={img.size} b64_len={len(result)}", flush=True)
        return result, "image/png"
    except Exception as e:
        print(f"[IMG] normalize failed: {e}", flush=True)
        return image_base64, image_mime


def _ocr_image(image_base64: str, image_mime: str) -> str:
    """Extract text from image via direct httpx call (bypasses OpenAI SDK formatting)."""
    try:
        b64, mime = _normalize_image(image_base64, image_mime)
        api_key = os.getenv("ALIBABA_API_KEY", "")
        base_url = os.getenv("ALIBABA_BASE_URL", "").rstrip("/")
        r = httpx.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "qwen-vl-ocr-2025-11-20",
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": "Read ALL text and numbers from this medical report image exactly as shown. Include every row and value."},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ]}],
                "max_tokens": 800,
            },
            timeout=30,
        )
        if r.status_code == 200:
            text = r.json()["choices"][0]["message"]["content"]
            print(f"[OCR] extracted {len(text)} chars", flush=True)
            return text
        print(f"[OCR] HTTP {r.status_code}: {r.text[:200]}", flush=True)
    except Exception as e:
        print(f"[OCR] failed: {e}", flush=True)
    return ""


def _build_user_content(message: str, image_base64: str = "", image_mime: str = "image/jpeg"):
    """Tạo user content. Nếu có ảnh, OCR trước rồi gửi text."""
    if not image_base64:
        return message
    ocr_text = _ocr_image(image_base64, image_mime)
    if ocr_text:
        combined = (message or "Đây là kết quả xét nghiệm CBC.") + f"\n\n[Nội dung ảnh xét nghiệm]\n{ocr_text}"
        return combined
    # Fallback: gửi ảnh trực tiếp
    b64, mime = _normalize_image(image_base64, image_mime)
    return [
        {"type": "text", "text": message or "Đây là kết quả xét nghiệm CBC của tôi."},
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
    ]


def chat_stream(message: str, history: list[dict], role: str = "patient",
                doctor_name: str = "", doctor_id: str = "",
                patient_id: str = "", patient_name: str = "",
                image_base64: str = "", image_mime: str = "image/jpeg",
                extra_system: str = ""):
    """
    Generator yield SSE strings. Mutates `history` in-place so caller can persist it.
    Format: "data: {json}\\n\\n"
    Types: status | tool_call | text | done | error
    """
    def sse(payload: dict) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    _DOCTOR_PROMPTS = {
        "doctor":              SYSTEM_PROMPT_DOCTOR,
        "doctor_records":      SYSTEM_PROMPT_DOCTOR_RECORDS,
        "doctor_cbc":          SYSTEM_PROMPT_DOCTOR_CBC,
        "doctor_appointments": SYSTEM_PROMPT_DOCTOR_APPOINTMENTS,
    }
    if role in _DOCTOR_PROMPTS:
        system = (_DOCTOR_PROMPTS[role]
                  .replace("{doctor_name}", doctor_name or "Bác sĩ")
                  .replace("{doctor_id}",   doctor_id or ""))
    else:
        system = SYSTEM_PROMPT
        if patient_id:
            # CRITICAL: prepend ở ĐẦU prompt để override các flow nói "HỎI tên"
            login_block = (
                f"=== ⚠ BỆNH NHÂN ĐÃ ĐĂNG NHẬP — ƯU TIÊN TUYỆT ĐỐI ===\n"
                f"Bệnh nhân đang chat: **{patient_name or 'Bệnh nhân'}** (FHIR Patient ID: {patient_id}).\n"
                f"\n"
                f"⚠ KHI ĐÃ ĐĂNG NHẬP, OVERRIDE TẤT CẢ CÁC FLOW BÊN DƯỚI:\n"
                f"- TUYỆT ĐỐI KHÔNG HỎI 'Tên đầy đủ của bạn' — đã biết tên là {patient_name or 'BN'}.\n"
                f"- TUYỆT ĐỐI KHÔNG gọi fhir_search_patient — đã có patient_id='{patient_id}' sẵn, dùng trực tiếp.\n"
                f"- Khi đặt lịch: chỉ cần HỎI EMAIL (nếu chưa có), rồi gọi fhir_get_next_available_slot → fhir_create_appointment NGAY.\n"
                f"- Khi hủy/xem lịch: dùng patient_id trực tiếp, KHÔNG hỏi xác minh tên.\n"
                f"- TUYỆT ĐỐI KHÔNG tra cứu, hiển thị hoặc thao tác trên hồ sơ / lịch hẹn / kết quả xét nghiệm của bất kỳ bệnh nhân NÀO KHÁC ngoài patient_id='{patient_id}'.\n"
                f"- Nếu user yêu cầu thông tin của người khác, từ chối lịch sự: 'Bạn chỉ có thể xem thông tin của chính mình.'\n"
                f"\n"
                f"=== KẾT THÚC ƯU TIÊN ĐĂNG NHẬP ===\n\n"
            )
            system = login_block + system

    if extra_system:
        system += f"\n\n{extra_system}"

    _now = datetime.now()
    system += (
        f"\n\n=== THỜI GIAN HIỆN TẠI ==="
        f"\nHôm nay: {_now.strftime('%A, %d/%m/%Y')} — Giờ: {_now.strftime('%H:%M')}."
        f"\nDùng thông tin này khi người dùng hỏi về ngày/giờ, ngày mai, tuần tới, v.v."
    )

    role_tools = _get_tools_for_role(role)

    history.append({"role": "user", "content": _build_user_content(message, image_base64, image_mime)})
    yield sse({"type": "status", "text": "Đang xử lý..."})

    # Tool-calling loop (non-streaming — cần full JSON để parse tool calls)
    while True:
        response = _CLIENT.chat.completions.create(
            model=_MODEL,
            max_tokens=1024,
            messages=[{"role": "system", "content": system}] + _trim_history(history),
            tools=role_tools or None,
        )
        choice = response.choices[0]
        msg    = choice.message

        if choice.finish_reason == "tool_calls" and msg.tool_calls:
            history.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in msg.tool_calls
                ],
            })
            _allowed_tool_names = {t["function"]["name"] for t in (role_tools or _TOOLS)}
            for tc in msg.tool_calls:
                # Block tool nếu không có trong allowed list (model đôi khi gọi tool không được phép)
                if tc.function.name not in _allowed_tool_names:
                    history.append({"role": "tool", "tool_call_id": tc.id,
                                    "content": json.dumps({"error": f"Tool '{tc.function.name}' không được phép cho vai trò này."})})
                    continue

                label = _TOOL_LABELS.get(tc.function.name, f"Gọi {tc.function.name}...")
                yield sse({"type": "tool_call", "name": tc.function.name, "label": label})
                args = json.loads(tc.function.arguments)

                # Patient portal: chỉ BN đã đăng nhập mới dùng được tools xem hồ sơ
                _PATIENT_SCOPED_TOOLS = {
                    "fhir_get_patient_history", "fhir_get_observations",
                    "fhir_get_patient_appointments", "fhir_cancel_appointment",
                    "fhir_get_allergies", "fhir_get_prescriptions",
                }
                if role == "patient" and tc.function.name in _PATIENT_SCOPED_TOOLS:
                    if not patient_id:
                        # Guest → block, trả lỗi thay vì gọi tool
                        history.append({"role": "tool", "tool_call_id": tc.id,
                                        "content": json.dumps({"error": "Bạn cần đăng nhập để xem thông tin này.", "authenticated": False})})
                        continue
                    args["patient_id"] = patient_id  # force ID của BN đang đăng nhập

                # Doctor portal: inject practitioner_id vào slot lookup
                if role == "doctor" and doctor_id:
                    if tc.function.name == "fhir_get_next_available_slot":
                        args.setdefault("practitioner_id", doctor_id)
                    # Inject slot_id từ history (turn trước) vào fhir_create_appointment
                    if tc.function.name == "fhir_create_appointment":
                        slot_id_from_history = _find_last_slot_id(history)
                        if slot_id_from_history:
                            args.setdefault("slot_id", slot_id_from_history)

                result_str = _execute_tool(tc.function.name, args, _MODULES)

                history.append({"role": "tool", "tool_call_id": tc.id, "content": result_str})
            yield sse({"type": "status", "text": "Đang tổng hợp kết quả..."})
        else:
            # Phản hồi cuối — stream từng token
            yield sse({"type": "status", "text": ""})
            stream = _CLIENT.chat.completions.create(
                model=_MODEL,
                max_tokens=1024,
                messages=[{"role": "system", "content": system}] + _trim_history(history),
                tools=None,
                stream=True,
            )
            full_reply = ""
            in_think   = False
            buf        = ""
            for chunk in stream:
                if not (chunk.choices and chunk.choices[0].delta.content):
                    continue
                full_reply += chunk.choices[0].delta.content
                buf        += chunk.choices[0].delta.content
                # Stream từng chunk sau khi strip thinking
                while buf:
                    if not in_think:
                        s = buf.find("<think>")
                        if s == -1:
                            yield sse({"type": "text", "delta": buf}); buf = ""; break
                        if s > 0:
                            yield sse({"type": "text", "delta": buf[:s]})
                        in_think = True; buf = buf[s+7:]
                    else:
                        e = buf.find("</think>")
                        if e == -1:
                            buf = ""; break
                        in_think = False; buf = buf[e+8:]

            import re
            clean = re.sub(r"<think>.*?</think>", "", full_reply, flags=re.DOTALL).strip()
            history.append({"role": "assistant", "content": clean or full_reply})
            yield sse({"type": "done"})
            return


def chat(message: str, history: list[dict], role: str = "patient",
         doctor_name: str = "", doctor_id: str = "",
         patient_id: str = "", patient_name: str = "",
         image_base64: str = "", image_mime: str = "image/jpeg",
         extra_system: str = "") -> tuple[str, list[dict]]:
    """
    Xử lý 1 lượt hội thoại.
    history: list of {"role": "user"|"assistant", "content": ...}
    Trả về (reply_text, updated_history)
    """
    _DOCTOR_PROMPTS = {
        "doctor":              SYSTEM_PROMPT_DOCTOR,
        "doctor_records":      SYSTEM_PROMPT_DOCTOR_RECORDS,
        "doctor_cbc":          SYSTEM_PROMPT_DOCTOR_CBC,
        "doctor_appointments": SYSTEM_PROMPT_DOCTOR_APPOINTMENTS,
    }
    if role in _DOCTOR_PROMPTS:
        system = (_DOCTOR_PROMPTS[role]
                  .replace("{doctor_name}", doctor_name or "Bác sĩ")
                  .replace("{doctor_id}",   doctor_id or ""))
    else:
        system = SYSTEM_PROMPT
        if patient_id:
            # CRITICAL: prepend ở ĐẦU prompt để override các flow nói "HỎI tên"
            login_block = (
                f"=== ⚠ BỆNH NHÂN ĐÃ ĐĂNG NHẬP — ƯU TIÊN TUYỆT ĐỐI ===\n"
                f"Bệnh nhân đang chat: **{patient_name or 'Bệnh nhân'}** (FHIR Patient ID: {patient_id}).\n"
                f"\n"
                f"⚠ KHI ĐÃ ĐĂNG NHẬP, OVERRIDE TẤT CẢ CÁC FLOW BÊN DƯỚI:\n"
                f"- TUYỆT ĐỐI KHÔNG HỎI 'Tên đầy đủ của bạn' — đã biết tên là {patient_name or 'BN'}.\n"
                f"- TUYỆT ĐỐI KHÔNG gọi fhir_search_patient — đã có patient_id='{patient_id}' sẵn, dùng trực tiếp.\n"
                f"- Khi đặt lịch: chỉ cần HỎI EMAIL (nếu chưa có), rồi gọi fhir_get_next_available_slot → fhir_create_appointment NGAY.\n"
                f"- Khi hủy/xem lịch: dùng patient_id trực tiếp, KHÔNG hỏi xác minh tên.\n"
                f"- TUYỆT ĐỐI KHÔNG tra cứu, hiển thị hoặc thao tác trên hồ sơ / lịch hẹn / kết quả xét nghiệm của bất kỳ bệnh nhân NÀO KHÁC ngoài patient_id='{patient_id}'.\n"
                f"- Nếu user yêu cầu thông tin của người khác, từ chối lịch sự: 'Bạn chỉ có thể xem thông tin của chính mình.'\n"
                f"\n"
                f"=== KẾT THÚC ƯU TIÊN ĐĂNG NHẬP ===\n\n"
            )
            system = login_block + system

    if extra_system:
        system += f"\n\n{extra_system}"

    _now = datetime.now()
    system += (
        f"\n\n=== THỜI GIAN HIỆN TẠI ==="
        f"\nHôm nay: {_now.strftime('%A, %d/%m/%Y')} — Giờ: {_now.strftime('%H:%M')}."
        f"\nDùng thông tin này khi người dùng hỏi về ngày/giờ, ngày mai, tuần tới, v.v."
    )

    role_tools = _get_tools_for_role(role)
    history = history + [{"role": "user", "content": _build_user_content(message, image_base64, image_mime)}]

    while True:
        response = _CLIENT.chat.completions.create(
            model=_MODEL,
            max_tokens=1024,
            messages=[{"role": "system", "content": system}] + history,
            tools=role_tools or None,
        )

        choice = response.choices[0]
        msg    = choice.message

        if choice.finish_reason == "tool_calls" and msg.tool_calls:
            history.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            })
            for tc in msg.tool_calls:
                args   = json.loads(tc.function.arguments)
                result = _execute_tool(tc.function.name, args, _MODULES)
                history.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      result,
                })
        else:
            reply = msg.content or ""
            history.append({"role": "assistant", "content": reply})
            return reply, history
