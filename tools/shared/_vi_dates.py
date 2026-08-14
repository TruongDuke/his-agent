"""Quy đổi cách nói ngày/giờ tiếng Việt sang ISO — chạy bằng code, không nhờ LLM.

Lý do tồn tại: bệnh nhân nói "thứ hai tuần sau lúc 10h sáng", LLM tự cộng trừ ra
18/08 (Thứ 3) thay vì 17/08 rồi vẫn báo "đúng yêu cầu". Cộng trừ ngày tháng là việc
máy làm đúng tuyệt đối còn LLM thì không — nên chuyển hẳn về code.

LLM chỉ cần chép nguyên cụm người dùng nói vào tham số, không phải tính gì.
Không quy đổi được thì trả None để agent hỏi lại, KHÔNG đoán bừa.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta

# thứ 2 = 0 ... chủ nhật = 6, khớp date.weekday()
_WEEKDAY_WORDS = {
    "thu 2": 0, "thu hai": 0, "t2": 0,
    "thu 3": 1, "thu ba": 1, "t3": 1,
    "thu 4": 2, "thu tu": 2, "t4": 2,
    "thu 5": 3, "thu nam": 3, "t5": 3,
    "thu 6": 4, "thu sau": 4, "t6": 4,
    "thu 7": 5, "thu bay": 5, "t7": 5,
    "chu nhat": 6, "cn": 6,
}

# Buổi trong ngày → giờ quy ước. Dùng khi user chỉ nói "chiều mai" mà không nêu giờ.
_PERIOD_HOURS = {"sang": 8, "trua": 11, "chieu": 13, "toi": 18}

_WEEKDAY_VI = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]


def _strip_accents(s: str) -> str:
    """'thứ hai' → 'thu hai'. So khớp không dấu để chịu được cả lối gõ tắt."""
    nfd = unicodedata.normalize("NFD", str(s or "").lower())
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn").replace("đ", "d")


def weekday_vi(d: date) -> str:
    return _WEEKDAY_VI[d.weekday()]


def resolve_date(text: str, today: date | None = None) -> date | None:
    """Cụm ngày tiếng Việt → date. None nếu không chắc (để agent hỏi lại)."""
    today = today or date.today()
    t = _strip_accents(text)
    if not t.strip():
        return None

    # 1. Ngày tường minh — ưu tiên cao nhất, không cần suy luận gì
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", t)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", t)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else today.year
        if year < 100:
            year += 2000
        try:
            d = date(year, month, day)
        except ValueError:
            return None
        # "20/08" khi đã qua 20/08 năm nay → hiểu là năm sau
        if not m.group(3) and d < today:
            try:
                d = date(year + 1, month, day)
            except ValueError:
                return None
        return d

    # 2. Nói tắt tương đối
    # "nay" đứng riêng = hôm nay, nhưng phải loại "tuần này" — bỏ dấu xong nó cũng
    # thành "tuan nay", trước đây khớp nhầm khiến "thứ 3 tuần này" ra hôm nay.
    if re.search(r"\bhom nay\b|\bhnay\b|(?<!tuan )\bnay\b(?! mai)", t):
        return today
    if re.search(r"\bngay kia\b|\bngay mot\b|\bmot\b", t):
        return today + timedelta(days=2)
    if re.search(r"\bngay mai\b|\bmai\b", t):
        return today + timedelta(days=1)

    # 3. Thứ trong tuần, kèm bổ ngữ tuần nào
    wd = None
    for word, idx in _WEEKDAY_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b", t):
            wd = idx
            break
    if wd is None:
        return None

    this_monday = today - timedelta(days=today.weekday())
    if re.search(r"tuan sau nua|tuan toi nua|2 tuan nua|hai tuan nua", t):
        return this_monday + timedelta(days=14 + wd)
    if re.search(r"tuan sau|tuan toi|tuan ke", t):
        return this_monday + timedelta(days=7 + wd)
    if re.search(r"tuan nay", t):
        d = this_monday + timedelta(days=wd)
        return d if d >= today else None  # đã qua → hỏi lại, không tự nhảy sang tuần sau
    # Không nói tuần nào → lần xuất hiện kế tiếp, tính từ ngày mai
    delta = (wd - today.weekday()) % 7
    return today + timedelta(days=delta or 7)


def resolve_time(text: str) -> str | None:
    """Cụm giờ tiếng Việt → 'HH:MM'. None nếu user không nêu giờ."""
    t = _strip_accents(text)
    if not t.strip():
        return None

    period = next((p for p in _PERIOD_HOURS if re.search(rf"\b{p}\b", t)), None)

    # "15h30", "15h", "15 gio", "15:00", "10 h"
    m = re.search(r"\b(\d{1,2})\s*(?:h|gio|:)\s*(\d{2})?\b", t)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2) or 0)
        # "3h chiều" → 15h. Chỉ cộng khi giờ nhỏ, tránh biến "15h chiều" thành 27h.
        if period in ("chieu", "toi") and hh < 12:
            hh += 12
        if period == "trua" and hh < 11:
            hh += 12
        if not (0 <= hh < 24 and 0 <= mm < 60):
            return None
        return f"{hh:02d}:{mm:02d}"

    # Chỉ nói buổi, không nói giờ cụ thể
    if period:
        return f"{_PERIOD_HOURS[period]:02d}:00"
    return None
