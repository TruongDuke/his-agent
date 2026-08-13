"""Cấu hình trình bày báo cáo CBC theo từng bác sĩ.

Mỗi bác sĩ có thể tùy chỉnh CÁCH TRÌNH BÀY báo cáo CBC/sàng lọc SXHD
(độ dài, đối tượng đọc, bật/tắt trích dẫn nguồn, khuyến nghị xét nghiệm,
cảnh báo aspirin, điểm số) + một ô "hướng dẫn riêng" tự do.

QUAN TRỌNG: config này CHỈ ảnh hưởng lớp TRÌNH BÀY. Logic lâm sàng và các
ngưỡng trong tools/dengue/dengue_cbc_predict.py KHÔNG đổi — tool vẫn tính
đúng, config chỉ chọn hiển thị phần nào. Vì vậy không có rủi ro làm sai
kết quả y khoa.

Lưu dạng JSON: data/doctor_configs/{doctor_id}.json
compile_cbc_prompt() biến config thành một block chỉ dẫn (tiếng Việt) để
tiêm vào system prompt qua tham số extra_system của agent.chat_stream.
"""
from __future__ import annotations

import json
from pathlib import Path

_CONFIG_DIR = Path(__file__).parent.parent / "data" / "doctor_configs"
_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# Giá trị mặc định = báo cáo đầy đủ cho bác sĩ (giữ nguyên hành vi hiện tại).
DEFAULT_CBC_CONFIG: dict = {
    "length":                 "full",    # "full" | "concise"
    "audience":               "doctor",  # "doctor" | "patient"
    "show_citations":         True,      # trích dẫn nguồn QĐ 2760
    "show_recommended_tests": True,      # khuyến nghị xét nghiệm tiếp theo
    "show_aspirin_warning":   True,      # cảnh báo aspirin/NSAID (an toàn)
    "show_scores":            False,     # cbc_score / warning_score
    "custom_note":            "",        # hướng dẫn riêng (free-text)
}

_BOOL_KEYS = ("show_citations", "show_recommended_tests", "show_aspirin_warning", "show_scores")


def _config_path(doctor_id: str) -> Path:
    # doctor_id là practitioner_id đã qua login; chặn path traversal cơ bản.
    safe = "".join(c for c in str(doctor_id) if c.isalnum() or c in "-_")
    return _CONFIG_DIR / f"{safe}.json"


def _merge_defaults(raw: dict) -> dict:
    """Trộn với default: thiếu key → dùng default, key lạ → bỏ."""
    cfg = dict(DEFAULT_CBC_CONFIG)
    if not isinstance(raw, dict):
        return cfg
    if raw.get("length") in ("full", "concise"):
        cfg["length"] = raw["length"]
    if raw.get("audience") in ("doctor", "patient"):
        cfg["audience"] = raw["audience"]
    for k in _BOOL_KEYS:
        if k in raw:
            cfg[k] = bool(raw[k])
    if isinstance(raw.get("custom_note"), str):
        cfg["custom_note"] = raw["custom_note"].strip()[:2000]
    return cfg


def load_cbc_config(doctor_id: str) -> dict:
    """Đọc config của bác sĩ; nếu chưa có → trả về default."""
    if not doctor_id:
        return dict(DEFAULT_CBC_CONFIG)
    p = _config_path(doctor_id)
    if not p.exists():
        return dict(DEFAULT_CBC_CONFIG)
    try:
        return _merge_defaults(json.loads(p.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_CBC_CONFIG)


def save_cbc_config(doctor_id: str, raw: dict) -> dict:
    """Ghi config (đã chuẩn hóa) cho bác sĩ, trả về config đã lưu."""
    if not doctor_id:
        raise ValueError("doctor_id là bắt buộc")
    cfg = _merge_defaults(raw)
    _config_path(doctor_id).write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return cfg


def compile_cbc_prompt(cfg: dict) -> str:
    """Biến config thành block chỉ dẫn cho system prompt.

    Trả về "" nếu config = mặc định và không có ghi chú riêng (không đổi
    hành vi cho bác sĩ chưa từng cấu hình).
    """
    cfg = _merge_defaults(cfg)
    is_default = all(cfg[k] == DEFAULT_CBC_CONFIG[k] for k in DEFAULT_CBC_CONFIG if k != "custom_note")
    if is_default and not cfg["custom_note"]:
        return ""

    lines: list[str] = []

    if cfg["length"] == "concise":
        lines.append(
            "- Trình bày NGẮN GỌN: chỉ nêu chỉ số CBC chính, kết luận sàng lọc "
            "(likelihood_label) và next_action. BỎ phần liệt kê findings chi tiết."
        )
    else:
        lines.append(
            "- Trình bày ĐẦY ĐỦ: nêu chỉ số CBC, kết luận sàng lọc, danh sách "
            "findings và khuyến nghị."
        )

    if cfg["audience"] == "patient":
        lines.append(
            "- Đối tượng đọc là BỆNH NHÂN: dùng ngôn ngữ đời thường dễ hiểu, "
            "hạn chế thuật ngữ chuyên môn, giải thích ngắn gọn ý nghĩa."
        )
    else:
        lines.append("- Đối tượng đọc là BÁC SĨ: dùng thuật ngữ y khoa chuyên ngành.")

    lines.append(
        "- CÓ hiển thị trích dẫn nguồn (citations, QĐ 2760) sau các phát hiện."
        if cfg["show_citations"]
        else "- KHÔNG hiển thị trích dẫn nguồn/citations trong báo cáo (bác sĩ đã nắm nguồn)."
    )
    lines.append(
        "- CÓ liệt kê khuyến nghị xét nghiệm tiếp theo (recommended_next_tests)."
        if cfg["show_recommended_tests"]
        else "- KHÔNG liệt kê phần khuyến nghị xét nghiệm tiếp theo."
    )
    lines.append(
        "- CÓ giữ dòng cảnh báo aspirin/NSAID (aspirin_warning)."
        if cfg["show_aspirin_warning"]
        else "- KHÔNG cần lặp lại cảnh báo aspirin/NSAID trừ khi liên quan trực tiếp."
    )
    lines.append(
        "- CÓ hiển thị điểm kỹ thuật cbc_score/warning_score."
        if cfg["show_scores"]
        else "- KHÔNG hiển thị điểm kỹ thuật cbc_score/warning_score."
    )

    if cfg["custom_note"]:
        lines.append(f"- Hướng dẫn riêng của bác sĩ: {cfg['custom_note']}")

    body = "\n".join(lines)
    return (
        "=== CẤU HÌNH TRÌNH BÀY BÁO CÁO CBC (ưu tiên khi trình bày kết quả CBC/SXHD) ===\n"
        f"{body}\n"
        "Chỉ áp dụng cho CÁCH TRÌNH BÀY. TUYỆT ĐỐI KHÔNG thay đổi kết quả sàng lọc, "
        "ngưỡng, hay likelihood do công cụ tính ra."
    )
