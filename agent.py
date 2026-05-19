"""HIS Agent — tool-calling loop (OpenAI-compatible SDK, works with OpenRouter)."""

from __future__ import annotations
import importlib, os, sys, json
from pathlib import Path
from typing import Any, Dict, List, Tuple

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
        "fhir_triage_assessment", "fhir_suggest_department", "fhir_search_patient",
        "fhir_register_new_patient", "fhir_get_next_available_slot", "fhir_get_available_slots",
        "fhir_create_appointment", "fhir_cancel_appointment", "fhir_get_patient_appointments",
        "dengue_symptom_assessment", "dengue_cbc_predict",
    ],
    "doctor": None,
    "doctor_records": [
        "fhir_search_patient", "fhir_get_patient_history", "fhir_get_observations",
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
if _OPENROUTER_KEY:
    _CLIENT = OpenAI(
        api_key=_OPENROUTER_KEY,
        base_url="https://openrouter.ai/api/v1",
    )
    _MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-haiku-4-5")
else:
    _CLIENT = OpenAI(
        api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        base_url="https://api.anthropic.com/v1/",
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
    "fhir_get_observations":       "Đang lấy kết quả xét nghiệm...",
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


def _build_user_content(message: str, image_base64: str = "", image_mime: str = "image/jpeg"):
    """Tạo user content: text-only hoặc multipart [text + image] cho vision."""
    if not image_base64:
        return message
    return [
        {"type": "text", "text": message or "Đây là kết quả xét nghiệm CBC của tôi."},
        {"type": "image_url", "image_url": {
            "url": f"data:{image_mime};base64,{image_base64}"
        }},
    ]


def chat_stream(message: str, history: list[dict], role: str = "patient",
                doctor_name: str = "", doctor_id: str = "",
                image_base64: str = "", image_mime: str = "image/jpeg"):
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

    role_tools = _get_tools_for_role(role)

    history.append({"role": "user", "content": _build_user_content(message, image_base64, image_mime)})
    yield sse({"type": "status", "text": "Đang xử lý..."})

    # Tool-calling loop (non-streaming — cần full JSON để parse tool calls)
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
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in msg.tool_calls
                ],
            })
            for tc in msg.tool_calls:
                label = _TOOL_LABELS.get(tc.function.name, f"Gọi {tc.function.name}...")
                yield sse({"type": "tool_call", "name": tc.function.name, "label": label})
                args = json.loads(tc.function.arguments)

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
                messages=[{"role": "system", "content": system}] + history,
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
         image_base64: str = "", image_mime: str = "image/jpeg") -> tuple[str, list[dict]]:
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
