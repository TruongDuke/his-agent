#!/usr/bin/env python3
"""Giả lập HIS của một bệnh viện khác đẩy dữ liệu sang HIS Agent.

Dùng để demo cổng /api/his/* — vì lúc bảo vệ không có HIS thật nào để bấm, script
này đóng vai bên gửi, chạy đúng một ca bệnh từ đầu tới cuối:

    tiếp nhận bệnh nhân → mở lượt khám → trả kết quả CBC → kê đơn → hẹn tái khám

Chạy:
    python scripts/demo_his_push.py --url http://localhost:8000 --key <HIS_API_KEY>
    python scripts/demo_his_push.py --url https://his.svisor.vn --key <HIS_API_KEY>

Không có --key thì lấy từ biến môi trường HIS_API_KEY.

Mặc định dùng mã bản tin cố định, nên chạy lần hai sẽ ra "duplicate" toàn bộ — bản
thân điều đó đã minh hoạ cơ chế chống ghi trùng. Muốn diễn lại từ đầu với "accepted"
thì thêm --fresh (sinh mã bản tin mới), khỏi phải ssh vào server xoá dữ liệu.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

# Mã bản tin cố định để chạy lại nhiều lần vẫn nhận ra là trùng — chính điều này
# minh hoạ cơ chế chống ghi trùng ở bước cuối. --fresh sẽ thay bằng mã mới.
RUN = "DEMO-2026-08"


def journey(run: str) -> list[tuple[str, str, dict]]:
    """Một ca bệnh có thật về mặt lâm sàng: tiểu cầu 98 và bạch cầu 3.2 là hình ảnh
    máu nghi sốt xuất huyết — nối được sang phần sàng lọc dengue của hệ thống."""
    return [
        ("patients", "Tiếp nhận bệnh nhân", {
            "message_id": f"{run}-PT-001",
            "his_patient_id": "BV2-000451",
            "full_name": "Trần Thị Hoa",
            "birth_date": "1992-03-18",
            "gender": "female",
            "phone": "0912345678",
            "email": "tranthihoa.demo@gmail.com",
            "address": "Số 12, Phường Dịch Vọng, Cầu Giấy, Hà Nội",
            "insurance_no": "DN4013012345",
        }),
        ("encounters", "Mở lượt khám", {
            "message_id": f"{run}-EN-001",
            "his_encounter_id": "BV2-ENC-8842",
            "his_patient_id": "BV2-000451",
            "encounter_class": "outpatient",
            "department": "Nội tổng quát",
            "practitioner_name": "BS. Nguyễn Minh Hoàng",
            "started_at": "2026-08-13T08:15:00+07:00",
            "reason": "Sốt 3 ngày, đau mỏi người, nổi ban",
        }),
        ("lab-results", "Trả kết quả xét nghiệm CBC", {
            "message_id": f"{run}-LAB-001",
            "his_order_id": "BV2-LAB-55120",
            "his_patient_id": "BV2-000451",
            "panel": "CBC",
            "resulted_at": "2026-08-13T09:40:00+07:00",
            "observations": [
                {"code": "718-7",  "name": "Hemoglobin", "value": 12.8, "unit": "g/dL",    "ref_range": "12.0-15.5", "abnormal_flag": "N"},
                {"code": "4544-3", "name": "Hematocrit", "value": 44.1, "unit": "%",       "ref_range": "36-46",     "abnormal_flag": "N"},
                {"code": "6690-2", "name": "WBC",        "value": 3.2,  "unit": "10^9/L",  "ref_range": "4.0-10.0",  "abnormal_flag": "L"},
                {"code": "777-3",  "name": "Platelets",  "value": 98,   "unit": "10^9/L",  "ref_range": "150-400",   "abnormal_flag": "L"},
            ],
        }),
        ("prescriptions", "Gửi đơn thuốc", {
            "message_id": f"{run}-RX-001",
            "his_prescription_id": "BV2-RX-3301",
            "his_patient_id": "BV2-000451",
            "prescribed_at": "2026-08-13T10:05:00+07:00",
            "practitioner_name": "BS. Nguyễn Minh Hoàng",
            "medications": [
                {"drug_name": "Paracetamol 500mg", "dose_per_intake": 1, "frequency_per_day": 3,
                 "duration_days": 3, "instructions": "Uống sau ăn, cách nhau ít nhất 4 giờ"},
                {"drug_name": "Oresol", "dose_per_intake": 1, "frequency_per_day": 3,
                 "duration_days": 3, "instructions": "Pha 1 gói với 200ml nước"},
            ],
        }),
        ("appointments", "Hẹn tái khám", {
            "message_id": f"{run}-AP-001",
            "his_appointment_id": "BV2-APT-7710",
            "his_patient_id": "BV2-000451",
            "department": "Nội tổng quát",
            "practitioner_name": "BS. Nguyễn Minh Hoàng",
            "start": "2026-08-15T08:30:00+07:00",
            "status": "booked",
        }),
    ]


def call(url: str, key: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json", "X-HIS-API-Key": key},
        method="POST" if payload is not None else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body or b"{}")
        except json.JSONDecodeError:
            return e.code, {"detail": body.decode(errors="replace")[:200]}
    except urllib.error.URLError as e:
        return 0, {"detail": f"Không kết nối được: {e.reason}"}


def main() -> int:
    ap = argparse.ArgumentParser(description="Giả lập HIS bệnh viện đẩy dữ liệu sang HIS Agent")
    ap.add_argument("--url", default="http://localhost:8000", help="Địa chỉ HIS Agent")
    ap.add_argument("--key", default=os.getenv("HIS_API_KEY", ""), help="Giá trị HIS_API_KEY")
    ap.add_argument("--slow", type=float, default=0.8, help="Giãn cách giữa các bước (giây), để demo dễ theo dõi")
    ap.add_argument("--fresh", action="store_true",
                    help="Sinh mã bản tin mới để diễn lại từ đầu (tất cả ra 'accepted' thay vì 'duplicate')")
    args = ap.parse_args()

    run = f"DEMO-{int(time.time())}" if args.fresh else RUN
    steps = journey(run)

    print(f"\n  BỆNH VIỆN B — hệ thống HIS  →  HIS Agent ({args.url})")
    print("  " + "─" * 62)

    status, caps = call(args.url, args.key, "/api/his/capabilities")
    if status != 200:
        print(f"  ✗ Không đọc được capabilities: {caps.get('detail', status)}")
        return 1
    if not caps.get("auth", {}).get("configured"):
        print("  ✗ Cổng đang ĐÓNG — server chưa đặt HIS_API_KEY trong .env.")
        print("    Đặt key rồi deploy lại, hoặc chạy script này với server local.")
        return 1
    if not args.key:
        print("  ✗ Thiếu --key (hoặc biến môi trường HIS_API_KEY).")
        return 1
    print(f"  Hợp đồng tích hợp v{caps.get('contract_version')} · trạng thái: {caps.get('status')}\n")

    ok = True
    for kind, label, payload in steps:
        time.sleep(args.slow)
        status, body = call(args.url, args.key, f"/api/his/{kind}", payload)
        if status == 202:
            r = body.get("receipt", {})
            print(f"  ✓ {label:32s} → {status} {body.get('status'):9s} biên nhận {r.get('receipt_id','')[:8]}")
        else:
            ok = False
            print(f"  ✗ {label:32s} → {status} {body.get('detail', body)}")

    if not args.fresh:
        print("\n  (Chạy lại lần nữa sẽ ra 'duplicate' — thêm --fresh để diễn lại từ đầu)")

    # Gửi lại đúng bản tin đầu tiên — HIS thật hay retry khi timeout mạng.
    time.sleep(args.slow)
    print()
    _, first = call(args.url, args.key, "/api/his/patients", steps[0][2])
    print("  ↻ Gửi lại bản tin đầu (giả lập HIS retry vì timeout)")
    print(f"    → {first.get('status')} — nhận lại đúng biên nhận cũ, không tạo bản ghi thứ hai")

    # Chiếu luôn dữ liệu đã nhận. Trước đây chỉ in URL, nhưng endpoint đó đòi header
    # X-HIS-API-Key nên dán vào trình duyệt là 401 — giữa lúc demo thì vấp.
    time.sleep(args.slow)
    status, msgs = call(args.url, args.key, "/api/his/messages/lab-results")
    items = (msgs or {}).get("items") or []
    if status == 200 and items:
        p = items[0]["payload"]
        print(f"\n  Dữ liệu đã nhận — {p.get('panel')} của bệnh nhân {p.get('his_patient_id')}:")
        for o in p.get("observations") or []:
            flag = {"L": "↓ thấp", "H": "↑ cao"}.get(o.get("abnormal_flag"), "bình thường")
            print(f"    {o.get('name',''):12s} {str(o.get('value','')):>6s} {o.get('unit',''):9s}"
                  f" {flag:12s} (tham chiếu {o.get('ref_range','')})")
        print("    → tiểu cầu và bạch cầu đều thấp: hình ảnh máu nghi sốt xuất huyết")

    _, caps2 = call(args.url, args.key, "/api/his/capabilities")
    print(f"\n  Tổng bản tin đang giữ: {caps2.get('counts')}\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
