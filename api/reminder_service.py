"""Nhắc lịch uống thuốc qua email cho bệnh nhân.

Luồng:
  - Bác sĩ kê đơn → derive_items_from_meds() suy ra lịch nhắc (giờ uống theo
    tần suất) → lưu data/med_reminders/{patient_id}.json.
  - Bệnh nhân xem/sửa/bật-tắt trong Hồ sơ của tôi.
  - Một luồng nền (start_scheduler) tick mỗi 60s: item nào tới giờ (theo giờ
    VN, UTC+7) và chưa gửi trong slot đó → gửi email nhắc, ghi sent_log để
    không gửi trùng.

Không phụ thuộc thư viện scheduler ngoài — dùng threading.Thread + vòng lặp.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

_DIR = Path(__file__).parent.parent / "data" / "med_reminders"
_DIR.mkdir(parents=True, exist_ok=True)

_TZ7 = timezone(timedelta(hours=7))  # Asia/Ho_Chi_Minh
_SENT_LOG_MAX = 80                   # giữ tối đa N key gần nhất mỗi item

# Giờ uống mặc định suy từ số lần/ngày (quy ước thực hành, có thể chỉnh trên UI).
_DEFAULT_TIMES = {
    1: ["08:00"],
    2: ["08:00", "20:00"],
    3: ["07:00", "12:00", "19:00"],
    4: ["06:00", "12:00", "18:00", "22:00"],
    5: ["06:00", "10:00", "14:00", "18:00", "22:00"],
}


# ─────────────────────── STORAGE ───────────────────────

def _path(patient_id: str) -> Path:
    safe = "".join(c for c in str(patient_id) if c.isalnum() or c in "-_")
    return _DIR / f"{safe}.json"


def _empty_doc(patient_id: str) -> dict:
    return {"patient_id": str(patient_id), "patient_name": "", "email": "", "items": []}


def _norm_time(t: str) -> str | None:
    """Chuẩn hóa 'HH:MM' hợp lệ, trả None nếu sai."""
    try:
        parts = str(t).strip().split(":")
        h, m = int(parts[0]), int(parts[1])
        if 0 <= h < 24 and 0 <= m < 60:
            return f"{h:02d}:{m:02d}"
    except (ValueError, IndexError):
        pass
    return None


def _norm_item(raw: dict) -> dict | None:
    if not isinstance(raw, dict) or not str(raw.get("drug_name") or "").strip():
        return None
    times = [nt for t in (raw.get("times") or []) if (nt := _norm_time(t))]
    times = sorted(set(times))
    return {
        "id":          str(raw.get("id") or uuid.uuid4()),
        "drug_name":   str(raw.get("drug_name")).strip()[:200],
        "dose_text":   str(raw.get("dose_text") or "").strip()[:300],
        "instruction": str(raw.get("instruction") or "").strip()[:300],
        "times":       times,
        "start_date":  str(raw.get("start_date") or date.today().isoformat())[:10],
        "end_date":    str(raw.get("end_date") or "")[:10],
        "enabled":     bool(raw.get("enabled", True)),
        "sent_log":    list(raw.get("sent_log") or [])[-_SENT_LOG_MAX:],
    }


def _norm_doc(patient_id: str, raw: dict) -> dict:
    doc = _empty_doc(patient_id)
    if isinstance(raw, dict):
        doc["patient_name"] = str(raw.get("patient_name") or "").strip()[:200]
        doc["email"] = str(raw.get("email") or "").strip()[:200]
        doc["items"] = [it for r in (raw.get("items") or []) if (it := _norm_item(r))]
    return doc


def load(patient_id: str) -> dict:
    p = _path(patient_id)
    if not p.exists():
        return _empty_doc(patient_id)
    try:
        return _norm_doc(patient_id, json.loads(p.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return _empty_doc(patient_id)


def save(patient_id: str, raw: dict) -> dict:
    doc = _norm_doc(patient_id, raw)
    _path(patient_id).write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return doc


# ─────────────────────── DERIVE FROM PRESCRIPTION ───────────────────────

def default_times(freq: int) -> list[str]:
    if freq in _DEFAULT_TIMES:
        return list(_DEFAULT_TIMES[freq])
    # Tần suất lạ → rải đều trong ngày từ 07:00 tới 21:00.
    freq = max(1, min(int(freq or 1), 8))
    if freq == 1:
        return ["08:00"]
    span = 14 * 60  # 07:00→21:00 theo phút
    step = span // (freq - 1)
    out = []
    for i in range(freq):
        mins = 7 * 60 + i * step
        out.append(f"{mins // 60:02d}:{mins % 60:02d}")
    return out


def _dose_text(med: dict) -> str:
    dose = med.get("dose_per_intake") or 1
    freq = med.get("frequency_per_day") or 1
    dur = med.get("duration_days")
    txt = f"{dose} viên/lần × {freq} lần/ngày"
    if dur:
        txt += f" × {dur} ngày"
    return txt


def derive_items_from_meds(meds: list[dict], start_date: str = "") -> list[dict]:
    """Suy lịch nhắc từ danh sách thuốc của một đơn."""
    start = start_date or date.today().isoformat()
    try:
        start_d = date.fromisoformat(start[:10])
    except ValueError:
        start_d = date.today()
        start = start_d.isoformat()

    items = []
    for med in meds or []:
        name = str(med.get("drug_name") or med.get("name") or "").strip()
        if not name:
            continue
        freq = int(med.get("frequency_per_day") or 1)
        dur = med.get("duration_days")
        end = ""
        if dur:
            try:
                end = (start_d + timedelta(days=int(dur) - 1)).isoformat()
            except (ValueError, TypeError):
                end = ""
        items.append(_norm_item({
            "drug_name":   name,
            "dose_text":   _dose_text(med),
            "instruction": med.get("instructions") or med.get("instruction") or "",
            "times":       default_times(freq),
            "start_date":  start,
            "end_date":    end,
            "enabled":     True,
        }))
    return items


def merge_from_prescription(patient_id: str, meds: list[dict], email: str = "",
                            patient_name: str = "", start_date: str = "") -> dict:
    """Thêm lịch nhắc từ một đơn thuốc mới vào doc hiện có của bệnh nhân."""
    doc = load(patient_id)
    if email:
        doc["email"] = email.strip()
    if patient_name:
        doc["patient_name"] = patient_name.strip()
    new_items = derive_items_from_meds(meds, start_date)
    doc["items"].extend(new_items)
    saved = save(patient_id, doc)
    saved["added"] = len(new_items)
    return saved


# ─────────────────────── EMAIL ───────────────────────

def _gmail_settings() -> tuple[str, str, str]:
    return (
        os.getenv("GMAIL_USER", "").strip(),
        os.getenv("GMAIL_APP_PASSWORD", "").strip(),
        os.getenv("GMAIL_FROM_NAME", "Bệnh viện Đa khoa Hà Nội").strip(),
    )


def _reminder_html(patient_name: str, item: dict, slot_time: str) -> str:
    instr = item.get("instruction") or ""
    instr_html = (
        f'<p style="margin:6px 0;color:#555">📋 Hướng dẫn: <b>{instr}</b></p>' if instr else ""
    )
    dose_html = (
        f'<p style="margin:6px 0;color:#555">Liều: {item.get("dose_text","")}</p>'
        if item.get("dose_text") else ""
    )
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;border:1px solid #e0e0e0;border-radius:10px;overflow:hidden">
      <div style="background:#005d5d;color:#fff;padding:16px 20px">
        <h2 style="margin:0;font-size:18px">⏰ Nhắc giờ uống thuốc — {slot_time}</h2>
      </div>
      <div style="padding:20px">
        <p style="margin:0 0 10px">Chào <b>{patient_name or 'bạn'}</b>,</p>
        <p style="margin:0 0 10px">Đã đến giờ uống thuốc:</p>
        <div style="background:#f0f7f7;border-left:4px solid #005d5d;padding:12px 16px;border-radius:6px">
          <p style="margin:0;font-size:16px;font-weight:700;color:#005d5d">{item.get('drug_name','')}</p>
          {dose_html}
          {instr_html}
        </div>
        <p style="margin:16px 0 0;color:#888;font-size:13px">
          Uống đúng giờ, đủ liều theo chỉ định của bác sĩ. Nếu có tác dụng phụ bất thường, liên hệ cơ sở y tế.
        </p>
      </div>
      <div style="background:#fafafa;padding:12px 20px;color:#aaa;font-size:12px;text-align:center">
        Email tự động từ hệ thống nhắc lịch uống thuốc — vui lòng không trả lời.
      </div>
    </div>
    """


def send_reminder_email(email: str, patient_name: str, item: dict, slot_time: str) -> dict:
    """Gửi 1 email nhắc. Trả {sent: bool, error?: str}."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    email = (email or "").strip()
    if not email:
        return {"sent": False, "error": "Thiếu email bệnh nhân"}

    user, pw, from_name = _gmail_settings()
    if not user or not pw:
        return {"sent": False, "error": "Gmail chưa cấu hình (GMAIL_USER/GMAIL_APP_PASSWORD)"}

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"⏰ Nhắc uống thuốc {item.get('drug_name','')} — {slot_time}"
    msg["From"] = f"{from_name} <{user}>"
    msg["To"] = email
    msg.attach(MIMEText(_reminder_html(patient_name, item, slot_time), "html", "utf-8"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.starttls()
            server.login(user, pw)
            server.sendmail(user, [email], msg.as_string())
        return {"sent": True}
    except Exception as e:  # noqa: BLE001 — báo lỗi ngược lên caller
        return {"sent": False, "error": str(e)}


def send_test(patient_id: str, item_id: str = "") -> dict:
    """Gửi email thử NGAY (không đụng sent_log)."""
    doc = load(patient_id)
    if not doc["email"]:
        return {"sent": False, "error": "Bệnh nhân chưa có email để nhắc"}
    item = None
    if item_id:
        item = next((it for it in doc["items"] if it["id"] == item_id), None)
    if item is None:
        item = doc["items"][0] if doc["items"] else None
    if item is None:
        return {"sent": False, "error": "Chưa có lịch nhắc nào để gửi thử"}
    now = datetime.now(_TZ7).strftime("%H:%M")
    return send_reminder_email(doc["email"], doc["patient_name"], item, now)


# ─────────────────────── SCHEDULER ───────────────────────

# Bù tối đa bao lâu cho slot bị lỡ. Quá mốc này thì thôi, nhắc uống thuốc lúc 8h
# mà 3 tiếng sau mới gửi thì vô nghĩa, còn gây hiểu nhầm là tới giờ uống liều mới.
_CATCHUP_MIN = 30


def _due_slots(item: dict, today: str, hhmm: str) -> list[str]:
    """Các slot của item đã tới giờ mà còn trong hạn bù.

    Trước đây so bằng đúng chuỗi HH:MM, nên chỉ cần app chết/deploy/tick chạy quá
    60s là phút đó trôi luôn, bệnh nhân mất nhắc mà không ai biết. Giờ quét cửa sổ
    lùi lại _CATCHUP_MIN phút; đã gửi rồi thì sent_log chặn, không lo gửi trùng.
    """
    if not item.get("enabled"):
        return []
    if item.get("start_date") and today < item["start_date"]:
        return []
    if item.get("end_date") and today > item["end_date"]:
        return []

    now_min = int(hhmm[:2]) * 60 + int(hhmm[3:5])
    due = []
    for t in item.get("times") or []:
        slot_min = int(t[:2]) * 60 + int(t[3:5])
        # Chỉ bù trong ngày, không kéo qua nửa đêm (slot_min <= now_min).
        if 0 <= now_min - slot_min <= _CATCHUP_MIN:
            due.append(t)
    return due


def tick(now: datetime | None = None, sender=send_reminder_email) -> int:
    """Quét tất cả bệnh nhân, gửi các slot tới giờ. Trả số email đã gửi.

    `sender` cho phép inject hàm giả khi test.
    """
    now = now or datetime.now(_TZ7)
    today = now.date().isoformat()
    hhmm = now.strftime("%H:%M")
    sent = 0

    for f in _DIR.glob("*.json"):
        try:
            doc = _norm_doc(f.stem, json.loads(f.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
        if not doc["email"]:
            continue
        changed = False
        for item in doc["items"]:
            for slot in _due_slots(item, today, hhmm):
                # Key theo GIỜ CỦA SLOT, không theo giờ hiện tại — có vậy slot gửi bù
                # lúc 08:05 mới nhận ra là slot 08:00 đã gửi rồi.
                key = f"{today}T{slot}"
                if key in item["sent_log"]:
                    continue
                res = sender(doc["email"], doc["patient_name"], item, slot)
                # Đánh dấu đã xử lý slot dù gửi lỗi, để không spam lại mỗi tick;
                # lỗi tạm thời sẽ được ghi nhận qua log.
                item["sent_log"] = (item["sent_log"] + [key])[-_SENT_LOG_MAX:]
                changed = True
                if res.get("sent"):
                    sent += 1
                else:
                    print(f"[med-reminder] gửi lỗi cho {doc['patient_id']}: {res.get('error')}", flush=True)
        if changed:
            f.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    return sent


_scheduler_started = False


def start_scheduler(interval_sec: int = 60) -> None:
    """Khởi động luồng nền tick định kỳ (idempotent)."""
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True

    def _loop():
        # Căn theo đầu phút để slot 'HH:MM' khớp đúng.
        while True:
            try:
                tick()
            except Exception as e:  # noqa: BLE001
                print(f"[med-reminder] tick lỗi: {e}", flush=True)
            # Ngủ tới ranh giới phút kế tiếp (tối đa interval_sec).
            now = datetime.now(_TZ7)
            sleep_s = min(interval_sec, 60 - now.second) or interval_sec
            time.sleep(sleep_s)

    threading.Thread(target=_loop, name="med-reminder-scheduler", daemon=True).start()
    print("[startup] med-reminder scheduler started ✓", flush=True)
