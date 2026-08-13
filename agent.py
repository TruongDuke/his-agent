"""HIS Agent — tool-calling loop (OpenAI-compatible SDK, works with OpenRouter)."""

from __future__ import annotations
import importlib, os, sys, json, re
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
    subpackages = {"fhir": "fhir_*.py", "dengue": "dengue_*.py", "outbreak": "outbreak_*.py",
                   "knowledge": "*_info.py"}
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


# ── SÀNG LỌC SXHD: phiếu tích cố định (frontend nhận diện 3 tiêu đề A/B/C để render form) ──
DENGUE_CHECKLIST = (
    "Mình sẽ giúp bạn sàng lọc sốt xuất huyết. Vui lòng trả lời các câu hỏi sau:\n\n"
    "**A. Dịch tễ:**\n"
    "1. Bạn đang sống hoặc vừa đến vùng có dịch sốt xuất huyết không?\n"
    "2. Bạn đang sốt mấy ngày rồi? (ghi số, ví dụ: 2 ngày)\n\n"
    "**B. Triệu chứng** (trả lời có/không cho từng mục):\n"
    "3. Buồn nôn hoặc nôn ói?\n"
    "4. Phát ban, nổi mẩn đỏ trên da?\n"
    "5. Đau cơ, đau khớp, nhức hai hố mắt?\n"
    "6. Chấm đỏ dưới da hoặc bầm tím không rõ nguyên nhân?\n\n"
    "**C. Dấu hiệu cảnh báo** (trả lời có/không):\n"
    "7. Đau bụng nhiều hoặc đau vùng gan?\n"
    "8. Nôn ói liên tục nhiều lần?\n"
    "9. Chảy máu chân răng, chảy máu mũi, phân đen?\n"
    "10. Đi tiểu ít hoặc nước tiểu sẫm màu?\n"
    "11. Vật vã, lờ đờ, mệt lả nhiều?"
)

# Dấu hiệu nguy hiểm → KHÔNG hiện phiếu, để LLM cảnh báo 115 (khớp EARLY-STOP FLOW D)
_DENGUE_DANGER = ("nôn ra máu", "ói máu", "ngất", "mất ý thức", "co giật",
                  "tay chân lạnh", "khó thở", "xuất huyết ồ ạt", "vàng da", "vàng mắt",
                  "rối loạn ý thức")
# Câu hỏi SỐ LIỆU dịch (FLOW G) — KHÔNG phải sàng lọc triệu chứng cá nhân
_OUTBREAK_KW = ("bao nhiêu ca", "số ca", "tình hình", "thống kê", "ca mắc",
                "bao nhiu ca", "mấy ca", "dịch đang", "số liệu")
_DENGUE_EXPLICIT = ("sốt xuất huyết", "sxh", "dengue")
_DENGUE_SYMPTOMS = ("đau người", "nhức mỏi", "đau khớp", "đau mỏi", "phát ban",
                    "mẩn đỏ", "nổi mẩn", "buồn nôn", "nôn ói", "chấm đỏ",
                    "xuất huyết dưới da", "nhức hố mắt", "đau hố mắt")


def _should_show_dengue_checklist(message: str, history: list[dict]) -> bool:
    """True nếu đây là lượt MỞ ĐẦU sàng lọc SXHD của bệnh nhân → hiện phiếu cố định.
    Xác định (deterministic), không phụ thuộc LLM có 'ngẫu hứng' gọi tool hay không."""
    m = (message or "").lower()
    if any(d in m for d in _DENGUE_DANGER):
        return False                      # nguy hiểm → để LLM xử lý cảnh báo 115
    if any(k in m for k in _OUTBREAK_KW):
        return False                      # hỏi số liệu dịch (FLOW G), không phải sàng lọc
    # đã hiện phiếu trước đó rồi (user đang trả lời) → không lặp lại
    for h in history:
        if h.get("role") == "assistant" and "A. Dịch tễ" in (h.get("content") or ""):
            return False
    explicit = any(k in m for k in _DENGUE_EXPLICIT)
    fever_plus = ("sốt" in m) and any(s in m for s in _DENGUE_SYMPTOMS)
    return explicit or fever_plus


def _booking_confirmation(result_json: str) -> str | None:
    """Nếu fhir_create_appointment trả success → dựng câu xác nhận xác định.
    Trả None nếu không phải đặt lịch thành công (để luồng chạy bình thường)."""
    try:
        d = json.loads(result_json)
    except Exception:
        return None
    if not (isinstance(d, dict) and d.get("success") and d.get("booking_code")):
        return None
    msg = d.get("message") or "Đã ghi nhận lịch khám, đang chờ bác sĩ xác nhận."
    if d.get("pending_confirmation"):
        email = d.get("patient_email", "")
        msg += (f"\n\n⏳ Lịch đang **chờ bác sĩ duyệt**. Sau khi bác sĩ xác nhận, "
                f"email xác nhận sẽ được gửi tới {email}." if email
                else "\n\n⏳ Lịch đang **chờ bác sĩ duyệt**.")
    return msg


# ── CHỐNG RÒ CHỮ HÁN/NHẬT/HÀN (AYT-2) ──────────────────────────────────────
# Model đang dùng (qwen3-vl-plus) đôi khi chèn chữ Trung vào giữa câu tiếng Việt,
# VD "Mất thị lực, nói不清, yếu một bên cơ thể". Prompt cấm được nhưng không tuyệt đối,
# nên chặn thêm ở tầng code: rà từng đoạn trước khi gửi ra UI.
_CJK_RE = re.compile(
    "[\u3040-\u30ff"   # hiragana + katakana
    "\u3400-\u4dbf"    # CJK ext A
    "\u4e00-\u9fff"    # CJK thong nhat (chu Han)
    "\uf900-\ufaff"    # CJK tuong thich
    "\uac00-\ud7af]"   # hangul
)

_REPAIR_SYSTEM = (
    "Viết lại văn bản của user thành 100% tiếng Việt. Giữ nguyên ý nghĩa, định dạng markdown, "
    "emoji, số liệu và cách xuống dòng. Thay mọi chữ Hán/Nhật/Hàn bằng từ tiếng Việt tương ứng "
    "(VD: 不清 → không rõ). CHỈ trả về văn bản đã sửa, không thêm lời giải thích."
)


def _sanitize_vi(text: str) -> str:
    """Nếu đoạn văn có chữ Hán/Nhật/Hàn → nhờ model dịch lại đúng chỗ đó.
    Sửa không xong thì xoá thẳng ký tự lạ — thà thiếu chữ hơn là hiện chữ Trung cho bệnh nhân."""
    if not text or not _CJK_RE.search(text):
        return text
    try:
        r = _CLIENT.chat.completions.create(
            model=_MODEL,
            max_tokens=1024,
            temperature=0,
            messages=[
                {"role": "system", "content": _REPAIR_SYSTEM},
                {"role": "user", "content": text},
            ],
        )
        fixed = (r.choices[0].message.content or "").strip()
        if fixed and not _CJK_RE.search(fixed):
            return fixed
    except Exception:
        pass
    return _CJK_RE.sub("", text)


def _split_safe(pending: str) -> tuple[str, str]:
    """Tách (phần gửi được, phần còn treo). Chỉ gửi khi đã hết câu — vì phải thấy trọn câu
    mới rà được chữ lạ; gửi từng token thì chữ Trung đã hiện lên màn hình rồi mới phát hiện."""
    idx = max(
        pending.rfind("\n"),
        pending.rfind(". "), pending.rfind(", "),
        pending.rfind("! "), pending.rfind("? "), pending.rfind(": "),
    )
    if idx == -1:
        return "", pending
    return pending[: idx + 1], pending[idx + 1 :]


# Cache modules + tools để không reload mỗi request
_MODULES = _load_tool_modules()
_TOOLS   = _build_openai_tools(_MODULES)

# Tool set cho từng role — None = dùng tất cả
_TOOLS_BY_ROLE: dict[str, list[str] | None] = {
    "patient": [
        "fhir_triage_assessment", "fhir_suggest_department",
        "fhir_register_new_patient", "fhir_get_next_available_slot",
        "fhir_create_appointment", "fhir_cancel_appointment", "fhir_get_patient_appointments",
        "fhir_get_patient_history", "fhir_get_observations",
        "fhir_get_clinical_impressions",
        "fhir_get_allergies", "fhir_get_prescriptions",
        "dengue_symptom_assessment", "dengue_cbc_predict",
        "outbreak_get_stats",
        "drug_info",
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

 # lọc quyền 2 lớp — (1) lúc build tools chỉ đưa tool được phép cho LLM thấy (_get_tools_for_role), (2) lúc chạy vẫn check lại _allowed_tool_names phòng LLM cố gọi tool không được đưa. Không tin LLM, verify 2 lần.

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
    _MODEL = os.getenv("ALIBABA_MODEL", "qwen3-vl-plus")
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
    "outbreak_get_stats":             "Đang tra cứu số liệu dịch bệnh từ HCDC...",
    "drug_info":                      "Đang tra cứu thông tin thuốc (NCBI)...",
}


def _find_last_slot_id(history: list) -> str | None:  # tiêm slot_id vào lệnh đặt lịch. Đây là 1 đường hỗ trợ; luồng chính của create_appointment vẫn tự tra slot từ dept+date+time.
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

    # cần cải thiện táhc 1 lớp session state để luu slot_id, tránh phải parse history. Lưu slot_id vào session state khi gọi fhir_get_next_available_slot, rồi fhir_create_appointment sẽ lấy từ session state thay vì parse history.


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


def _trim_history(history: list[dict], max_messages: int = 24) -> list[dict]: # cắt bớt history để tránh quá dài, max_messages=24 là mặc định
    """Giữ tối đa max_messages tin nhắn gần nhất, strip ảnh khỏi history cũ."""
    cleaned = _strip_images(history) # strip ảnh khỏi history cũ để tránh quá dài
    if len(cleaned) <= max_messages:
        trimmed = cleaned
    else:
        trimmed = cleaned[-max_messages:] # giữ max_messages = 24 tin nhắn gần nhất
    # First non-system message must be user role
    while trimmed and trimmed[0].get("role") != "user": # đảm bảo bắt đầu bằng user tránh căt giữa chừng
        trimmed = trimmed[1:]
    roles = [m.get("role") for m in trimmed]
    print(f"[TRIM] history={len(history)} trimmed={len(trimmed)} roles={roles}", flush=True)
    return trimmed


def _normalize_image(image_base64: str, image_mime: str = "image/jpeg") -> tuple[str, str]:
    """Convert any image or PDF (page 1) to PNG ≤512px for API compatibility."""
    try:
        from PIL import Image
        raw = base64.b64decode(image_base64) # decode base64 to bytes ảnh thật
        if image_mime == "application/pdf" or raw[:4] == b"%PDF": # nếu là PDF, convert page 1 sang ảnh
            import fitz
            doc = fitz.open(stream=raw, filetype="pdf")
            pix = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2))
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        else:
            img = Image.open(io.BytesIO(raw)).convert("RGB") # convert to RGB để tránh alpha channel
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

# Hàm 1 — _normalize_image = "chỉnh sửa ảnh cho gọn"
# Tưởng tượng bạn có cái máy photo thông minh. Ai đưa gì vào — ảnh chụp, file PDF — nó cũng biến thành 1 tấm ảnh chuẩn, nhỏ gọn, rõ nét để dễ đọc.

# Nó làm 3 việc:

# Nếu là PDF → chụp lại trang 1 thành ảnh (vì máy đọc chữ chỉ hiểu ảnh, không hiểu PDF).
# Nếu ảnh quá to → thu nhỏ lại (tối đa 512 chấm), nhưng giữ chữ nét để không đọc nhầm số.
# Đóng gói lại thành 1 tấm ảnh PNG sạch sẽ.
# → Kết quả: dù bạn đưa vào cái gì, ra là 1 tấm ảnh chuẩn.

# Nếu lỗi? (file hỏng) → nó đưa lại ảnh gốc, không làm sập chương trình.

def _ocr_image(image_base64: str, image_mime: str) -> str:
    """Extract text from image via direct httpx call (bypasses OpenAI SDK formatting)."""
    try:
        b64, mime = _normalize_image(image_base64, image_mime)
        api_key = os.getenv("ALIBABA_API_KEY", "")
        base_url = os.getenv("ALIBABA_BASE_URL", "").rstrip("/")
        r = httpx.post( # gửi rquest trực tiếp tới API OCR của Alibaba, bypass OpenAI SDK
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "qwen-vl-ocr-2025-11-20", # model chuyên đọc ảnh y tế
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

# Tưởng tượng bạn thuê 1 người chuyên đọc phiếu xét nghiệm. Bạn đưa tấm ảnh, họ chép lại y nguyên mọi con số, mọi dòng ra giấy.

# Nó làm:

# Nhờ hàm 1 chỉnh ảnh cho gọn trước.
# Gửi ảnh cho "người đọc chuyên nghiệp" (model qwen-vl-ocr) kèm lời dặn: "Đọc HẾT mọi chữ, mọi số, đừng bỏ sót dòng nào."
# Nhận về đoạn chữ (VD: "PLT 85, WBC 3.2, HCT 44...").
# Nếu lỗi? (mạng hỏng, đọc không được) → trả về rỗng → hệ thống chuyển sang cách khác (đưa thẳng ảnh cho AI chính tự nhìn).

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
                f"- Khi đặt lịch: gọi fhir_get_next_available_slot lấy slot → xác nhận giờ + bác sĩ với user → HỎI EMAIL 1 LẦN (nếu chưa có) → gọi fhir_create_appointment NGAY trong cùng lượt. KHÔNG hỏi email khi chưa chốt slot; KHÔNG hỏi lại email nếu user đã cung cấp.\n"
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

    history.append({"role": "user", "content": _build_user_content(message, image_base64, image_mime)}) # thêm tin nhắn người dùng vào lịch sử

    # GUARD (deterministic): lượt mở đầu sàng lọc SXHD của bệnh nhân → hiện PHIẾU cố định,
    # KHÔNG để LLM tự đoán rồi gọi thẳng dengue_symptom_assessment (làm mất phiếu + đoán sai dịch tễ).
    if role == "patient" and not image_base64 and _should_show_dengue_checklist(message, history):
        history.append({"role": "assistant", "content": DENGUE_CHECKLIST})
        yield sse({"type": "status", "text": ""})
        yield sse({"type": "text", "delta": DENGUE_CHECKLIST})
        yield sse({"type": "done"})
        return

    yield sse({"type": "status", "text": "Đang xử lý..."})

    # ═══ TRÁI TIM: vòng lặp tool-calling ═══
    # LLM KHÔNG có trí nhớ giữa các lần gọi -> mỗi vòng phải gửi LẠI toàn bộ history.
    # Lặp tới khi LLM NGỪNG đòi tool (finish_reason != "tool_calls") thì mới trả lời & thoát.
    # Code KHÔNG định trước thứ tự/số lượng tool — LLM tự suy luận. Đó chính là điểm "agent".
    while True:
        response = _CLIENT.chat.completions.create( # gọi API LLM để nhận phản hồi, có thể là tool call hoặc text
            model=_MODEL,
            max_tokens=1024,
            messages=[{"role": "system", "content": system}] + _trim_history(history), #mỗi vòng lặp gửi lại toàn bộ history (có tool result) để LLM đọc
            tools=role_tools or None,
        )
        choice = response.choices[0]
        msg    = choice.message

        if choice.finish_reason == "tool_calls" and msg.tool_calls:
            history.append({ # LLM đòi gọi tool → lưu tin nhắn này vào history, kèm tool_calls (có id)
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in msg.tool_calls
                ],
            })
            _allowed_tool_names = {t["function"]["name"] for t in (role_tools or _TOOLS)}
            _booked = None
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
                    # BẢO MẬT TẦNG 2 (code-enforced): ép patient_id = ID đã đăng nhập, ghi đè bất kỳ ID nào
                    # LLM truyền. Kể cả LLM bị "dụ" (jailbreak) cũng KHÔNG truy được hồ sơ bệnh nhân khác.
                    # (Tầng 1 là prompt cấm ở system prompt.)
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

                history.append({"role": "tool", "tool_call_id": tc.id, "content": result_str}) # Lưu kết quả tool vào history để LLM đọc ở vòng lặp tiếp theo

                if tc.function.name == "fhir_create_appointment":
                    _booked = _booking_confirmation(result_str)

                # Nếu tool trả về danh sách nguồn (vd drug_info) → đẩy lên UI để render thẻ
                try:
                    _parsed = json.loads(result_str)
                    if isinstance(_parsed, dict) and _parsed.get("sources"):
                        yield sse({"type": "sources", "items": _parsed["sources"]})
                except Exception:
                    pass
            # GUARD: đặt lịch thành công → trả confirmation xác định NGAY, chặn LLM
            # gọi thêm tool slot / narrate sai (xem _booking_confirmation).
            if _booked:
                history.append({"role": "assistant", "content": _booked})
                yield sse({"type": "status", "text": ""})
                yield sse({"type": "text", "delta": _booked})
                yield sse({"type": "done"})
                return
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
            pending    = ""   # đã bỏ <think>, chờ đủ câu mới rà chữ lạ rồi gửi (xem _split_safe)
            sent       = ""   # phần thật sự hiện trên UI (đã sửa) — đây mới là cái lưu vào history
            for chunk in stream:
                if not (chunk.choices and chunk.choices[0].delta.content):
                    continue
                full_reply += chunk.choices[0].delta.content
                buf        += chunk.choices[0].delta.content
                # Gom chunk sau khi strip thinking
                while buf:
                    if not in_think:
                        s = buf.find("<think>")
                        if s == -1:
                            pending += buf; buf = ""; break
                        if s > 0:
                            pending += buf[:s]
                        in_think = True; buf = buf[s+7:]
                    else:
                        e = buf.find("</think>")
                        if e == -1:
                            buf = ""; break
                        in_think = False; buf = buf[e+8:]

                ready, pending = _split_safe(pending)
                if ready:
                    ready = _sanitize_vi(ready)
                    sent += ready
                    yield sse({"type": "text", "delta": ready})

            if pending:  # phần đuôi không kết thúc bằng dấu câu
                tail = _sanitize_vi(pending)
                sent += tail
                yield sse({"type": "text", "delta": tail})

            clean = re.sub(r"<think>.*?</think>", "", full_reply, flags=re.DOTALL).strip()
            history.append({"role": "assistant", "content": sent.strip() or clean or full_reply})
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
                f"- Khi đặt lịch: gọi fhir_get_next_available_slot lấy slot → xác nhận giờ + bác sĩ với user → HỎI EMAIL 1 LẦN (nếu chưa có) → gọi fhir_create_appointment NGAY trong cùng lượt. KHÔNG hỏi email khi chưa chốt slot; KHÔNG hỏi lại email nếu user đã cung cấp.\n"
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

    # GUARD (deterministic): lượt mở đầu sàng lọc SXHD của bệnh nhân → hiện PHIẾU cố định.
    if role == "patient" and not image_base64 and _should_show_dengue_checklist(message, history):
        history = history + [{"role": "assistant", "content": DENGUE_CHECKLIST}]
        return DENGUE_CHECKLIST, history

    while True:
        response = _CLIENT.chat.completions.create(
            model=_MODEL,
            max_tokens=1024,
            messages=[{"role": "system", "content": system}] + history,
            tools=role_tools or None,
        )

        choice = response.choices[0]
        msg    = choice.message

        if choice.finish_reason == "tool_calls" and msg.tool_calls: # AI nói tôi muốn dùng tool
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
            _booked = None
            for tc in msg.tool_calls:
                args   = json.loads(tc.function.arguments)
                result = _execute_tool(tc.function.name, args, _MODULES)
                history.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      result,
                })
                if tc.function.name == "fhir_create_appointment":
                    _booked = _booking_confirmation(result)
            # GUARD: đặt lịch thành công → trả confirmation xác định NGAY, chặn LLM
            # gọi thêm tool slot / narrate sai (Qwen hay gọi song song get_next_available_slot
            # rồi báo "chưa đặt, xác nhận lại" dù lịch đã tạo).
            if _booked:
                history.append({"role": "assistant", "content": _booked})
                return _booked, history
        else:
            reply = _sanitize_vi(msg.content or "")
            history.append({"role": "assistant", "content": reply})
            return reply, history
