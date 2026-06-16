"""Scrape số liệu sốt xuất huyết (SXHD) từ bản tin tuần của HCDC TP.HCM.

HCDC đăng bản tin "Tình hình dịch bệnh sốt xuất huyết, tay chân miệng ..."
đều mỗi thứ 5/tuần. URL có shortcode random nên KHÔNG guess được —
phải quét category page tìm bản tin tuần mới nhất.

Stdlib + httpx (đã có sẵn), không cần beautifulsoup4.
"""

from __future__ import annotations
import html as _html
import json
import os
import re
from pathlib import Path

import httpx

_BASE = "https://hcdc.vn"
CATEGORY_URL = f"{_BASE}/category/van-de-suc-khoe/sot-xuat-huyet-chikungunya/"
SEARCH_URL = f"{_BASE}/timkiem/"
_UA = {"User-Agent": "Mozilla/5.0 (HISAgent/1.0)"}
_TIMEOUT = 20.0

_MOCK_PATH = Path(__file__).parent / "_mock_data.json"

# URL bản tin tuần: ...tinh-den-tuan-{week}{year}-{shortcode}.html
_LINK_RE = re.compile(r'href="([^"]*tinh-den-tuan-(\d{1,2})(\d{4})-[^"]*\.html)"')
# Tách week/year từ chính URL (không cần fetch)
_URL_WEEK_RE = re.compile(r"tinh-den-tuan-(\d{1,2})(\d{4})-")

# Các pattern ổn định giữa các tuần (chạy trên plain text, bỏ qua HTML markup)
_PATTERNS = {
    "week_year":    re.compile(r"tính đến tuần\s+(\d{1,2})\s*/\s*(\d{4})", re.I),
    "weekly_cases": re.compile(r"ghi nhận\s+([\d.,]+)\s+trường hợp mắc bệnh\s+sốt xuất huyết", re.I),
    "cumulative":   re.compile(r"[Tt]ổng số ca (?:mắc )?sốt xuất huyết tích lũy.*?là\s+([\d.,]+)\s+ca", re.I | re.S),
    "compare":      re.compile(r"sốt xuất huyết\s+(giảm|tăng|ổn định)\s+([\d.,]+)\s*%", re.I),
    "published":    re.compile(r"Cập nhật:\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2})/(\d{1,2})/(\d{4})"),
}


def _to_text(raw: str) -> str:
    """HTML thô → plain text đã normalize whitespace."""
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = _html.unescape(t)
    return re.sub(r"\s+", " ", t).strip()


def _to_int(s: str) -> int:
    """'18.136' (dấu '.' phân cách nghìn kiểu VN) → 18136."""
    return int(re.sub(r"[.\s,]", "", s))


def _to_float(s: str) -> float:
    """'5,9' (thập phân kiểu VN) → 5.9."""
    return float(s.replace(".", "").replace(",", "."))


def _abs_url(href: str) -> str:
    if href.startswith("http"):
        return href
    return f"{_BASE}/{href.lstrip('/')}"


def _extract_bulletins(html_text: str) -> dict[tuple[int, int], str]:
    """{(year, week): absolute_url} cho mọi link bản tin trong trang."""
    found: dict[tuple[int, int], str] = {}
    for m in _LINK_RE.finditer(html_text):
        found[(int(m.group(3)), int(m.group(2)))] = _abs_url(m.group(1))
    return found


def find_latest_bulletin_url() -> str | None:
    """Quét category page → URL bản tin tuần mới nhất (sort theo year, week)."""
    resp = httpx.get(CATEGORY_URL, headers=_UA, timeout=_TIMEOUT, follow_redirects=True)
    resp.raise_for_status()
    found = _extract_bulletins(resp.text)
    return found[max(found)] if found else None


def search_bulletin_url(week: int, year: int) -> str | None:
    """Tìm URL bản tin của ĐÚNG (week, year) qua ô tìm kiếm HCDC (/timkiem/).

    Search fuzzy (vd 'tuan 5' lẫn cả tuần 50/51) nên BẮT BUỘC lọc khớp chính xác
    week+year từ URL kết quả. Đây là cách tra động bất kỳ tuần nào, không cần seed.
    """
    try:
        resp = httpx.get(SEARCH_URL, params={"keyword": f"tuan {week}"},
                         headers=_UA, timeout=_TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
    except Exception:
        return None
    return _extract_bulletins(resp.text).get((year, week))


def fetch_bulletin(url: str) -> str:
    resp = httpx.get(url, headers=_UA, timeout=_TIMEOUT, follow_redirects=True)
    resp.raise_for_status()
    return resp.text


def parse_bulletin(raw_html: str, source_url: str = "") -> dict:
    """Parse HTML bản tin → dict số liệu SXHD."""
    text = _to_text(raw_html)
    data: dict = {"disease": "dengue", "location": "hcm", "source_url": source_url}

    m = _PATTERNS["week_year"].search(text)
    if m:
        data["week"] = int(m.group(1))
        data["year"] = int(m.group(2))

    m = _PATTERNS["weekly_cases"].search(text)
    if m:
        data["weekly_cases"] = _to_int(m.group(1))

    m = _PATTERNS["cumulative"].search(text)
    if m:
        data["cumulative_cases"] = _to_int(m.group(1))

    m = _PATTERNS["compare"].search(text)
    if m:
        data["direction"] = m.group(1).lower()        # giảm | tăng | ổn định
        data["percent_change"] = _to_float(m.group(2))

    m = _PATTERNS["published"].search(text)
    if m:
        hh, mm, dd, mo, yy = m.groups()
        data["published_at"] = f"{yy}-{int(mo):02d}-{int(dd):02d}"  # ISO date

    return data


def validate_parsed(data: dict) -> bool:
    """Sanity check để không báo data sai cho user."""
    weekly = data.get("weekly_cases")
    cumulative = data.get("cumulative_cases")
    if not data.get("week") or not data.get("year"):
        return False
    if not isinstance(weekly, int) or not (0 < weekly < 10000):
        return False
    if not isinstance(cumulative, int) or cumulative < weekly:
        return False
    return True


def week_year_from_url(url: str) -> tuple[int, int] | None:
    """(year, week) từ URL bản tin, không cần fetch. None nếu không khớp."""
    m = _URL_WEEK_RE.search(url)
    if not m:
        return None
    return int(m.group(2)), int(m.group(1))  # (year, week)


def scrape_url(url: str) -> dict | None:
    """Fetch + parse 1 URL bản tin. None nếu lỗi hoặc không hợp lệ."""
    try:
        data = parse_bulletin(fetch_bulletin(url), source_url=url)
        return data if validate_parsed(data) else None
    except Exception:
        return None


def scrape_latest() -> dict | None:
    """Network scrape: tìm bản tin mới nhất từ category → fetch → parse."""
    url = find_latest_bulletin_url()
    return scrape_url(url) if url else None


def is_mock() -> bool:
    return os.getenv("HCDC_MOCK") == "1"


def mock_records() -> list[dict]:
    """Đọc mock data (demo offline). Hỗ trợ cả list (nhiều tuần) lẫn 1 object."""
    raw = json.loads(_MOCK_PATH.read_text(encoding="utf-8"))
    return raw if isinstance(raw, list) else [raw]
