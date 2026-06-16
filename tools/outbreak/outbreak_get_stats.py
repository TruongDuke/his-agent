"""Số liệu dịch bệnh thật từ HCDC TP.HCM — lịch sử nhiều tuần + lazy refresh.

- Lazy: chỉ scrape khi user hỏi. Các tuần đã có trong cache không fetch lại.
- Registry (_bulletin_urls.json) seed các tuần đã biết (category HCDC bỏ sót vài tuần).
- Tuần mới tự bổ sung qua category page (gate 24h). Scrape lỗi → vẫn dùng cache cũ.
- Hỗ trợ tra TUẦN cụ thể + so sánh tuần-trên-tuần (week-over-week) thật.
"""

from __future__ import annotations
from datetime import date, datetime, timedelta

from . import _cache, _hcdc_scraper

TOOL_NAME = "outbreak_get_stats"
CATEGORY = "Healthcare"
DESCRIPTION = (
    "Lấy số liệu dịch bệnh THẬT từ HCDC TP.HCM (nguồn chính thức, theo tuần). "
    "Hiện hỗ trợ: sốt xuất huyết (SXHD) tại TP.HCM, có LỊCH SỬ nhiều tuần. "
    "Mặc định trả tuần mới nhất; truyền 'week' (và 'year') để tra một tuần cụ thể. "
    "Trả về: số ca tuần, lũy kế từ đầu năm, xu hướng so với TB 4 tuần trước (trend_text), "
    "SO SÁNH VỚI TUẦN LIỀN TRƯỚC (week_over_week) nếu có, danh sách tuần đang có (available_weeks), "
    "ngày cập nhật, độ trễ, và source_url để trích dẫn. "
    "Dùng khi user hỏi 'bao nhiêu ca SXHD', 'tình hình dịch', 'tuần này so với tuần trước', 'số ca tuần 22'... "
    "BẮT BUỘC trích source_url và nói rõ TUẦN cụ thể (không nói 'hôm nay'). "
    "Lưu ý: chỉ data TP.HCM; không có tử vong/chia quận/cả nước."
)
ARGS_SCHEMA = {
    "disease": "Tên bệnh. Hiện chỉ hỗ trợ 'dengue' (sốt xuất huyết). Mặc định 'dengue'.",
    "location": "Khu vực. Hiện chỉ hỗ trợ 'hcm' (TP.HCM). Mặc định 'hcm'.",
    "week": "number (tùy chọn) — Số tuần cần tra (vd 22). Bỏ trống = tuần mới nhất.",
    "year": "number (tùy chọn) — Năm của tuần cần tra. Mặc định 2026 nếu có 'week'.",
}

_CACHE_TTL_HOURS = 24
_STALE_DAYS = 9


def _populate_mock(disease: str) -> None:
    for rec in _hcdc_scraper.mock_records():
        if not _cache.has_week(disease, rec.get("year"), rec.get("week")):
            _cache.save_record(disease, rec)


def _resolve_week(disease: str, year: int, week: int) -> bool:
    """Đảm bảo (year, week) có trong cache; nếu chưa thì TRA ĐỘNG qua search HCDC."""
    if week < 1:
        return False
    if _cache.has_week(disease, year, week):
        return True
    url = _hcdc_scraper.search_bulletin_url(week, year)
    if not url:
        return False
    rec = _hcdc_scraper.scrape_url(url)
    if rec:
        _cache.save_record(disease, rec)
        return True
    return False


def _ensure_latest(disease: str) -> None:
    """Bổ sung tuần mới nhất từ category — gate 24h để khỏi hit mạng mỗi lần."""
    if _cache.get_latest(disease) is not None and _cache.latest_age_hours(disease) <= _CACHE_TTL_HOURS:
        return
    try:
        rec = _hcdc_scraper.scrape_latest()
        if rec:
            _cache.save_record(disease, rec)  # reset fetched_at -> gate 24h
    except Exception:
        pass  # giữ cache cũ


def _vn_num(x: float) -> str:
    return f"{x:g}".replace(".", ",")


def _build_trend_text(data: dict) -> str | None:
    """Xu hướng theo metric HCDC (so với TB 4 tuần trước) — render sẵn, LLM khỏi suy diễn."""
    direction, pct = data.get("direction"), data.get("percent_change")
    if not direction or pct is None:
        return None
    baseline = "trung bình 4 tuần trước"
    if direction == "ổn định":
        return f"ổn định (dao động {_vn_num(pct)}% so với {baseline})"
    return f"{direction} {_vn_num(pct)}% so với {baseline}"


def run(args: dict) -> dict:
    disease = (args.get("disease") or "dengue").strip().lower()
    location = (args.get("location") or "hcm").strip().lower()

    if disease not in ("dengue", "sxhd", "sốt xuất huyết"):
        return {"error": f"Hiện chỉ hỗ trợ số liệu sốt xuất huyết (dengue), chưa có '{disease}'."}
    if location not in ("hcm", "tphcm", "hồ chí minh", "ho chi minh"):
        return {"error": f"Hiện chỉ có số liệu TP.HCM, chưa có '{location}'."}
    disease = "dengue"

    mock = _hcdc_scraper.is_mock()
    if mock:
        _populate_mock(disease)

    # Chọn tuần mục tiêu: theo yêu cầu (tra động qua search) hoặc mới nhất (qua category)
    req_week = args.get("week")
    if req_week not in (None, "", "null"):
        try:
            req_week = int(req_week)
            req_year = int(args.get("year") or date.today().year)
        except (ValueError, TypeError):
            return {"error": f"Tham số week/year không hợp lệ: week={args.get('week')}."}
        if not mock:
            _resolve_week(disease, req_year, req_week)
        rec = _cache.get_record(disease, req_year, req_week)
        if not rec:
            return {
                "error": f"Không tìm được số liệu SXHD tuần {req_week}/{req_year} trên HCDC.",
                "available_weeks": [f"{w}/{y}" for (y, w) in _cache.list_weeks(disease)],
            }
    else:
        if not mock:
            _ensure_latest(disease)
        rec = _cache.get_latest(disease)
        if not rec:
            return {"error": "Chưa lấy được số liệu SXHD từ HCDC (mạng lỗi và chưa có cache). "
                             "Thử lại sau hoặc bật demo mode HCDC_MOCK=1."}

    data = rec["data"]
    week, year = data.get("week"), data.get("year")
    published_at = data.get("published_at")

    # Đảm bảo có tuần liền trước để so sánh week-over-week (tra động nếu thiếu)
    if not mock:
        _resolve_week(disease, year, week - 1)
    available = _cache.list_weeks(disease)

    # Freshness
    freshness_days = next_update_estimate = None
    if published_at:
        try:
            pub = datetime.strptime(published_at, "%Y-%m-%d").date()
            freshness_days = (date.today() - pub).days
            next_update_estimate = (pub + timedelta(days=7)).isoformat()
        except ValueError:
            pass

    # So sánh tuần-trên-tuần (chỉ khi có đúng tuần LIỀN TRƯỚC)
    wow = {"has_week_over_week": False, "wow_text": None,
           "prev_week": None, "prev_weekly_cases": None,
           "wow_delta": None, "wow_percent": None}
    prev = _cache.get_previous(disease, year, week)
    if prev and prev["data"].get("week") == week - 1 and prev["data"].get("year") == year:
        pw = prev["data"]
        cur_c, prev_c = data.get("weekly_cases"), pw.get("weekly_cases")
        if isinstance(cur_c, int) and isinstance(prev_c, int) and prev_c > 0:
            delta = cur_c - prev_c
            pct = round(delta / prev_c * 100, 1)
            verb = "tăng" if delta > 0 else ("giảm" if delta < 0 else "không đổi")
            sign = "+" if delta > 0 else ""
            wow = {
                "has_week_over_week": True,
                "prev_week": pw.get("week"),
                "prev_weekly_cases": prev_c,
                "wow_delta": delta,
                "wow_percent": pct,
                "wow_text": (f"{verb} {abs(delta)} ca ({sign}{_vn_num(pct)}%) "
                             f"so với tuần {pw.get('week')} ({prev_c} ca)"),
            }

    return {
        "disease": "dengue",
        "disease_label": "Sốt xuất huyết Dengue",
        "location": "TP. Hồ Chí Minh",
        "week": week,
        "year": year,
        "weekly_cases": data.get("weekly_cases"),
        "cumulative_cases": data.get("cumulative_cases"),
        "direction": data.get("direction"),
        "percent_change": data.get("percent_change"),
        "comparison_baseline": "trung bình 4 tuần trước",
        "trend_text": _build_trend_text(data),
        **wow,
        "available_weeks": [f"{w}/{y}" for (y, w) in available],
        "published_at": published_at,
        "freshness_days": freshness_days,
        "is_likely_outdated": (freshness_days is not None and freshness_days > _STALE_DAYS),
        "next_update_estimate": next_update_estimate,
        "scope_note": "Chỉ có số liệu TP.HCM theo tuần; không có data cả nước, tử vong hay chia theo quận.",
        "source_url": data.get("source_url"),
        "_citation": f"HCDC TP.HCM · Bản tin tuần {week}/{year} · {data.get('source_url', '')}",
    }
