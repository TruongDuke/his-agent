"""HIS Agent — Anthropic tool-calling loop."""

import importlib, os, sys, json
from pathlib import Path
from typing import Any

import anthropic
from system_prompt import SYSTEM_PROMPT

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


def _build_anthropic_tools(modules: dict) -> list[dict]:
    """Chuyển ARGS_SCHEMA của tool sang format Anthropic tool use."""
    result = []
    for name, mod in modules.items():
        schema = getattr(mod, "ARGS_SCHEMA", {})
        properties = {}
        for param, desc in schema.items():
            properties[param] = {"type": "string", "description": desc}
        result.append({
            "name": name,
            "description": getattr(mod, "DESCRIPTION", ""),
            "input_schema": {
                "type": "object",
                "properties": properties,
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
_TOOLS   = _build_anthropic_tools(_MODULES)
_CLIENT  = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
_MODEL   = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")


def chat(message: str, history: list[dict]) -> tuple[str, list[dict]]:
    """
    Xử lý 1 lượt hội thoại.
    history: list of {"role": "user"|"assistant", "content": ...}
    Trả về (reply_text, updated_history)
    """
    history = history + [{"role": "user", "content": message}]

    while True:
        response = _CLIENT.messages.create(
            model=_MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=_TOOLS,
            messages=history,
        )

        if response.stop_reason == "tool_use":
            # Append assistant message (có thể gồm text + tool_use blocks)
            history.append({"role": "assistant", "content": response.content})

            # Xử lý tất cả tool calls trong response này
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = _execute_tool(block.name, dict(block.input), _MODULES)
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     result,
                    })

            history.append({"role": "user", "content": tool_results})

        else:
            # stop_reason == "end_turn" — lấy text trả về
            reply = ""
            for block in response.content:
                if hasattr(block, "text"):
                    reply += block.text
            history.append({"role": "assistant", "content": reply})
            return reply, history
