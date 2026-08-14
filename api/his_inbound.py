"""Kho lưu bản tin HIS đẩy sang — tầng dưới của các đầu chờ trong routes/his.py.

Mỗi loại bản tin ghi vào một file JSONL riêng trong data/his_inbound/. Chọn JSONL
thay vì DB vì giai đoạn này chỉ cần: (1) đội HIS gửi thử và tự xem lại được bản tin
mình vừa gửi, (2) khi viết phần ánh xạ sang FHIR thì có sẵn dữ liệu thật để đối chiếu.
Đổi sang DB sau cũng không phải sửa hợp đồng API.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

_DIR = Path(__file__).parent.parent / "data" / "his_inbound"
_DIR.mkdir(parents=True, exist_ok=True)

_TZ7 = timezone(timedelta(hours=7))  # Asia/Ho_Chi_Minh

# Các loại bản tin đang mở đầu chờ. Thêm loại mới thì khai báo ở đây trước.
KINDS = ("patients", "encounters", "lab-results", "prescriptions", "appointments")


def _path(kind: str) -> Path:
    return _DIR / f"{kind}.jsonl"


def _iter_records(kind: str):
    p = _path(kind)
    if not p.exists():
        return
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue  # bỏ qua dòng hỏng, không làm chết cả file


def find_receipt(kind: str, message_id: str) -> dict | None:
    """Bản tin đã nhận trước đó chưa? HIS thường gửi lại khi timeout mạng,
    nhận trùng mà cứ ghi tiếp thì sau này ánh xạ sang FHIR sẽ tạo bản ghi kép."""
    if not message_id:
        return None
    for rec in _iter_records(kind):
        if rec.get("message_id") == message_id:
            return rec.get("receipt") or None
    return None


def record(kind: str, message_id: str, payload: dict) -> dict:
    """Ghi bản tin và trả biên nhận."""
    receipt = {
        "receipt_id":        str(uuid.uuid4()),
        "kind":              kind,
        "message_id":        message_id,
        "received_at":       datetime.now(_TZ7).isoformat(timespec="seconds"),
        # Cờ này là điểm mấu chốt: đầu chờ mới nhận và lưu, CHƯA ghi vào Aidbox.
        # Bên HIS đọc cờ để biết dữ liệu chưa vào bệnh án chính thức.
        "persisted_to_fhir": False,
    }
    line = json.dumps(
        {"message_id": message_id, "receipt": receipt, "payload": payload},
        ensure_ascii=False,
    )
    with _path(kind).open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return receipt


def update_receipt(kind: str, message_id: str, receipt: dict) -> None:
    """Ghi đè biên nhận của một bản tin (dùng sau khi ánh xạ sang FHIR xong).

    JSONL không sửa tại chỗ được nên đọc hết rồi ghi lại cả file. Chấp nhận được ở
    quy mô này; đổi sang DB thì thay mỗi hàm này.
    """
    records = list(_iter_records(kind))
    changed = False
    for rec in records:
        if rec.get("message_id") == message_id:
            rec["receipt"] = receipt
            changed = True
    if not changed:
        return
    with _path(kind).open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def recent(kind: str, limit: int = 20) -> list[dict]:
    """N bản tin gần nhất — để đội HIS tự đối chiếu cái mình vừa gửi."""
    return list(_iter_records(kind))[-limit:][::-1]


def counts() -> dict[str, int]:
    return {k: sum(1 for _ in _iter_records(k)) for k in KINDS}
