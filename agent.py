"""HIS Agent — tool-calling loop (OpenAI-compatible SDK, works with OpenRouter)."""

from __future__ import annotations
import importlib, os, sys, json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from openai import OpenAI
from system_prompt import SYSTEM_PROMPT, SYSTEM_PROMPT_DOCTOR

# Thêm thư mục tools vào path để tools tự import được nhau
sys.path.insert(0, str(Path(__file__).parent / "tools"))

# Settings inject vào tools có SETTINGS_KEYS (gmail, v.v.)
def _get_settings() -> dict:
    return {
        "gmail_user":         os.getenv("GMAIL_USER", ""),
        "gmail_app_password": os.getenv("GMAIL_APP_PASSWORD", ""),
        "gmail_from_name":    os.getenv("GMAIL_FROM_NAME", "Bệnh viện Đa khoa Hà Nội"),
    }


def _load_tool_modules() -> dict[str, Any]:
    """Load tất cả fhir_* tools, trả về dict name → module."""
    modules = {}
    tools_dir = Path(__file__).parent / "tools"
    for path in sorted(tools_dir.glob("fhir_*.py")):
        mod_name = f"tools.{path.stem}"
        mod = importlib.import_module(mod_name)
        if hasattr(mod, "TOOL_NAME") and hasattr(mod, "run"):
            modules[mod.TOOL_NAME] = mod
    return modules


def _build_openai_tools(modules: dict) -> list[dict]:
    """Chuyển ARGS_SCHEMA của tool sang format OpenAI function calling."""
    result = []
    for name, mod in modules.items():
        schema = getattr(mod, "ARGS_SCHEMA", {})
        properties = {}
        for param, desc in schema.items():
            properties[param] = {"type": "string", "description": desc}
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
}


def chat_stream(message: str, history: list[dict], role: str = "patient", doctor_name: str = ""):
    """
    Generator yield SSE strings. Mutates `history` in-place so caller can persist it.
    Format: "data: {json}\\n\\n"
    Types: status | tool_call | text | done | error
    """
    def sse(payload: dict) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    if role == "doctor":
        system = SYSTEM_PROMPT_DOCTOR.replace("{doctor_name}", doctor_name or "Bác sĩ")
    else:
        system = SYSTEM_PROMPT

    history.append({"role": "user", "content": message})
    yield sse({"type": "status", "text": "Đang xử lý..."})

    # Tool-calling loop (non-streaming — cần full JSON để parse tool calls)
    while True:
        response = _CLIENT.chat.completions.create(
            model=_MODEL,
            max_tokens=4096,
            messages=[{"role": "system", "content": system}] + history,
            tools=_TOOLS or None,
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
                args   = json.loads(tc.function.arguments)
                result = _execute_tool(tc.function.name, args, _MODULES)
                history.append({"role": "tool", "tool_call_id": tc.id, "content": result})
            yield sse({"type": "status", "text": "Đang tổng hợp kết quả..."})
        else:
            # Phản hồi cuối — stream từng token
            yield sse({"type": "status", "text": ""})
            stream = _CLIENT.chat.completions.create(
                model=_MODEL,
                max_tokens=4096,
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


def chat(message: str, history: list[dict], role: str = "patient", doctor_name: str = "") -> tuple[str, list[dict]]:
    """
    Xử lý 1 lượt hội thoại.
    history: list of {"role": "user"|"assistant", "content": ...}
    Trả về (reply_text, updated_history)
    """
    if role == "doctor":
        system = SYSTEM_PROMPT_DOCTOR.replace("{doctor_name}", doctor_name or "Bác sĩ")
    else:
        system = SYSTEM_PROMPT

    history = history + [{"role": "user", "content": message}]

    while True:
        response = _CLIENT.chat.completions.create(
            model=_MODEL,
            max_tokens=4096,
            messages=[{"role": "system", "content": system}] + history,
            tools=_TOOLS or None,
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
