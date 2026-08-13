"""Generate Practitioner + Schedule + Slot for all 17 departments on Aidbox.

For each practitioner:
  - 1 Practitioner resource (upsert)
  - 1 Schedule (with serviceType = department code)
  - Slots 30-min, 30 working days ahead
  - Morning: 8:00 - 11:00 (6 slots), Afternoon: 13:30 - 15:30 (4 slots)
  - ~30% randomly marked 'busy' to simulate real load

Usage:
    python generate_slots.py --dry-run
    AIDBOX_URL=... AIDBOX_CLIENT_ID=... AIDBOX_CLIENT_SECRET=... python generate_slots.py
"""
from __future__ import annotations
import os, sys, argparse, random
from datetime import date, datetime, timedelta

try:
    import httpx
except ImportError:
    sys.exit("Missing httpx. Run: pip install httpx")

# Đọc .env ở gốc dự án để khỏi phải export tay 3 biến AIDBOX_*
try:
    from pathlib import Path
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

random.seed(42)

DAYS_AHEAD = 30
START_DAY = 1      # ngày bắt đầu tạo slot, tính từ hôm nay (dùng --start để tạo bù khoảng còn thiếu)
CHUNK = 2000       # số entry mỗi transaction — Aidbox edge nghẹn nếu đẩy một cục hàng chục nghìn
BUSY_RATIO = 0.3
MORNING_TIMES   = ["08:00", "08:30", "09:00", "09:30", "10:00", "10:30"]
AFTERNOON_TIMES = ["13:30", "14:00", "14:30", "15:00"]

# 3 practitioners per department — IDs are stable so re-running is idempotent
PRACTITIONERS = [
    # ── CARDIO ──────────────────────────────────────────────────────
    {"id": "fdf43bd5-432b-4110-a522-e22e0da3e15b", "name": "Trần Văn B",    "dept": "CARDIO",  "dept_name": "Khoa Tim Mạch"},
    {"id": "a1b2c3d4-0001-4000-8000-000000000001", "name": "Nguyễn Thị Hoa", "dept": "CARDIO",  "dept_name": "Khoa Tim Mạch"},
    {"id": "a1b2c3d4-0001-4000-8000-000000000002", "name": "Lê Minh Đức",    "dept": "CARDIO",  "dept_name": "Khoa Tim Mạch"},
    # ── ENDO ────────────────────────────────────────────────────────
    {"id": "09a107cb-58c0-4435-b547-069b85d9d3dd", "name": "Lê Thị C",       "dept": "ENDO",    "dept_name": "Khoa Nội Tiết"},
    {"id": "a1b2c3d4-0002-4000-8000-000000000001", "name": "Phạm Thị Lan",   "dept": "ENDO",    "dept_name": "Khoa Nội Tiết"},
    {"id": "a1b2c3d4-0002-4000-8000-000000000002", "name": "Hoàng Văn Nam",  "dept": "ENDO",    "dept_name": "Khoa Nội Tiết"},
    # ── ENT ─────────────────────────────────────────────────────────
    {"id": "e70c7428-ae1b-478a-8cb0-778d1c9d8864", "name": "Phạm Văn D",     "dept": "ENT",     "dept_name": "Khoa Tai Mũi Họng"},
    {"id": "a1b2c3d4-0003-4000-8000-000000000001", "name": "Trần Thị Mai",   "dept": "ENT",     "dept_name": "Khoa Tai Mũi Họng"},
    {"id": "a1b2c3d4-0003-4000-8000-000000000002", "name": "Vũ Quốc Hùng",  "dept": "ENT",     "dept_name": "Khoa Tai Mũi Họng"},
    # ── NEURO ───────────────────────────────────────────────────────
    {"id": "a1b2c3d4-0004-4000-8000-000000000001", "name": "Nguyễn Đức Anh", "dept": "NEURO",   "dept_name": "Khoa Thần Kinh"},
    {"id": "a1b2c3d4-0004-4000-8000-000000000002", "name": "Bùi Thị Thu",    "dept": "NEURO",   "dept_name": "Khoa Thần Kinh"},
    {"id": "a1b2c3d4-0004-4000-8000-000000000003", "name": "Đỗ Văn Hải",     "dept": "NEURO",   "dept_name": "Khoa Thần Kinh"},
    # ── GASTRO ──────────────────────────────────────────────────────
    {"id": "a1b2c3d4-0005-4000-8000-000000000001", "name": "Lý Thị Bích",    "dept": "GASTRO",  "dept_name": "Khoa Tiêu Hóa"},
    {"id": "a1b2c3d4-0005-4000-8000-000000000002", "name": "Trịnh Văn Long", "dept": "GASTRO",  "dept_name": "Khoa Tiêu Hóa"},
    {"id": "a1b2c3d4-0005-4000-8000-000000000003", "name": "Đinh Thị Nga",   "dept": "GASTRO",  "dept_name": "Khoa Tiêu Hóa"},
    # ── RHEUMA ──────────────────────────────────────────────────────
    {"id": "a1b2c3d4-0006-4000-8000-000000000001", "name": "Phan Văn Tú",    "dept": "RHEUMA",  "dept_name": "Khoa Cơ Xương Khớp"},
    {"id": "a1b2c3d4-0006-4000-8000-000000000002", "name": "Cao Thị Yến",    "dept": "RHEUMA",  "dept_name": "Khoa Cơ Xương Khớp"},
    {"id": "a1b2c3d4-0006-4000-8000-000000000003", "name": "Lưu Minh Khoa",  "dept": "RHEUMA",  "dept_name": "Khoa Cơ Xương Khớp"},
    # ── DERMA ───────────────────────────────────────────────────────
    {"id": "a1b2c3d4-0007-4000-8000-000000000001", "name": "Hà Thị Linh",    "dept": "DERMA",   "dept_name": "Khoa Da Liễu"},
    {"id": "a1b2c3d4-0007-4000-8000-000000000002", "name": "Ngô Văn Phúc",   "dept": "DERMA",   "dept_name": "Khoa Da Liễu"},
    {"id": "a1b2c3d4-0007-4000-8000-000000000003", "name": "Tô Thị Hằng",    "dept": "DERMA",   "dept_name": "Khoa Da Liễu"},
    # ── OBGYN ───────────────────────────────────────────────────────
    {"id": "a1b2c3d4-0008-4000-8000-000000000001", "name": "Võ Thị Phương",  "dept": "OBGYN",   "dept_name": "Khoa Sản Phụ Khoa"},
    {"id": "a1b2c3d4-0008-4000-8000-000000000002", "name": "Dương Thị Hoa",  "dept": "OBGYN",   "dept_name": "Khoa Sản Phụ Khoa"},
    {"id": "a1b2c3d4-0008-4000-8000-000000000003", "name": "Bùi Thị Thảo",   "dept": "OBGYN",   "dept_name": "Khoa Sản Phụ Khoa"},
    # ── PEDIAT ──────────────────────────────────────────────────────
    {"id": "a1b2c3d4-0009-4000-8000-000000000001", "name": "Phùng Văn Khải", "dept": "PEDIAT",  "dept_name": "Khoa Nhi"},
    {"id": "a1b2c3d4-0009-4000-8000-000000000002", "name": "Lê Thị Ngọc",    "dept": "PEDIAT",  "dept_name": "Khoa Nhi"},
    {"id": "a1b2c3d4-0009-4000-8000-000000000003", "name": "Trần Văn Tùng",  "dept": "PEDIAT",  "dept_name": "Khoa Nhi"},
    # ── OPHTHAL ─────────────────────────────────────────────────────
    {"id": "a1b2c3d4-0010-4000-8000-000000000001", "name": "Nguyễn Thị Dung","dept": "OPHTHAL", "dept_name": "Khoa Mắt"},
    {"id": "a1b2c3d4-0010-4000-8000-000000000002", "name": "Hoàng Minh Tuấn","dept": "OPHTHAL", "dept_name": "Khoa Mắt"},
    {"id": "a1b2c3d4-0010-4000-8000-000000000003", "name": "Vũ Thị Thanh",   "dept": "OPHTHAL", "dept_name": "Khoa Mắt"},
    # ── UROLOGY ─────────────────────────────────────────────────────
    {"id": "a1b2c3d4-0011-4000-8000-000000000001", "name": "Đặng Văn Bình",  "dept": "UROLOGY", "dept_name": "Khoa Thận Tiết Niệu"},
    {"id": "a1b2c3d4-0011-4000-8000-000000000002", "name": "Ngô Thị Hương",  "dept": "UROLOGY", "dept_name": "Khoa Thận Tiết Niệu"},
    {"id": "a1b2c3d4-0011-4000-8000-000000000003", "name": "Chu Văn Minh",   "dept": "UROLOGY", "dept_name": "Khoa Thận Tiết Niệu"},
    # ── GENERAL ─────────────────────────────────────────────────────
    {"id": "a1b2c3d4-0012-4000-8000-000000000001", "name": "Lê Văn Quân",    "dept": "GENERAL", "dept_name": "Khoa Nội Tổng Quát"},
    {"id": "a1b2c3d4-0012-4000-8000-000000000002", "name": "Phạm Thị Hà",    "dept": "GENERAL", "dept_name": "Khoa Nội Tổng Quát"},
    {"id": "a1b2c3d4-0012-4000-8000-000000000003", "name": "Trần Thị Kim",   "dept": "GENERAL", "dept_name": "Khoa Nội Tổng Quát"},
    # ── SURGERY ─────────────────────────────────────────────────────
    {"id": "a1b2c3d4-0013-4000-8000-000000000001", "name": "Đinh Văn Sơn",   "dept": "SURGERY", "dept_name": "Khoa Ngoại"},
    {"id": "a1b2c3d4-0013-4000-8000-000000000002", "name": "Lý Thị Xuân",    "dept": "SURGERY", "dept_name": "Khoa Ngoại"},
    {"id": "a1b2c3d4-0013-4000-8000-000000000003", "name": "Phan Văn Đại",   "dept": "SURGERY", "dept_name": "Khoa Ngoại"},
    # ── DENTAL ──────────────────────────────────────────────────────
    {"id": "a1b2c3d4-0014-4000-8000-000000000001", "name": "Vương Thị Lan",  "dept": "DENTAL",  "dept_name": "Khoa Răng Hàm Mặt"},
    {"id": "a1b2c3d4-0014-4000-8000-000000000002", "name": "Hoàng Văn Dũng", "dept": "DENTAL",  "dept_name": "Khoa Răng Hàm Mặt"},
    {"id": "a1b2c3d4-0014-4000-8000-000000000003", "name": "Trịnh Thị Hòa",  "dept": "DENTAL",  "dept_name": "Khoa Răng Hàm Mặt"},
    # ── PULMO ───────────────────────────────────────────────────────
    {"id": "a1b2c3d4-0015-4000-8000-000000000001", "name": "Bùi Văn Thắng",  "dept": "PULMO",   "dept_name": "Khoa Hô Hấp"},
    {"id": "a1b2c3d4-0015-4000-8000-000000000002", "name": "Đào Thị Liên",   "dept": "PULMO",   "dept_name": "Khoa Hô Hấp"},
    {"id": "a1b2c3d4-0015-4000-8000-000000000003", "name": "Nguyễn Văn Khánh","dept": "PULMO",  "dept_name": "Khoa Hô Hấp"},
    # ── ORTHO ───────────────────────────────────────────────────────
    {"id": "a1b2c3d4-0016-4000-8000-000000000001", "name": "Cao Văn Lâm",    "dept": "ORTHO",   "dept_name": "Khoa Chấn Thương Chỉnh Hình"},
    {"id": "a1b2c3d4-0016-4000-8000-000000000002", "name": "Lê Thị Phượng",  "dept": "ORTHO",   "dept_name": "Khoa Chấn Thương Chỉnh Hình"},
    {"id": "a1b2c3d4-0016-4000-8000-000000000003", "name": "Trần Quốc Việt", "dept": "ORTHO",   "dept_name": "Khoa Chấn Thương Chỉnh Hình"},
]


def mk_practitioner(pr: dict) -> dict:
    family, *given = pr["name"].split()
    return {
        "resourceType": "Practitioner",
        "id": pr["id"],
        "active": True,
        "name": [{"use": "official", "family": family, "given": given}],
        "qualification": [{"code": {"text": f"Bác sĩ {pr['dept_name']}"}}],
    }


def mk_schedule(pr: dict, index: int) -> dict:
    start_d = date.today()
    end_d = start_d + timedelta(days=DAYS_AHEAD + 1)
    sched_id = f"sched-{pr['dept'].lower()}-{index}"
    return {
        "resourceType": "Schedule",
        "id": sched_id,
        "active": True,
        "actor": [{"reference": f"Practitioner/{pr['id']}"}],
        "serviceType": [{"concept": {"coding": [{
            "system": "urn:vn:department",
            "code": pr["dept"],
            "display": pr["dept_name"],
        }]}}],
        "planningHorizon": {"start": start_d.isoformat(), "end": end_d.isoformat()},
        "comment": f"Lịch khám {pr['dept_name']} — BS. {pr['name']}",
    }


def mk_slot(schedule_id: str, day: date, time_str: str, status: str = "free") -> dict:
    hh, mm = map(int, time_str.split(":"))
    start_dt = datetime(day.year, day.month, day.day, hh, mm)
    end_dt = start_dt + timedelta(minutes=30)
    return {
        "resourceType": "Slot",
        "schedule": {"reference": f"Schedule/{schedule_id}"},
        "status": status,
        "start": start_dt.strftime("%Y-%m-%dT%H:%M:%S+07:00"),
        "end":   end_dt.strftime("%Y-%m-%dT%H:%M:%S+07:00"),
    }


def build_bundle() -> tuple[dict, int, int, int]:
    entries = []
    pract_count = schedule_count = slot_count = 0

    # Track index per dept for schedule ID
    dept_index: dict[str, int] = {}

    for pr in PRACTITIONERS:
        dept = pr["dept"]
        dept_index[dept] = dept_index.get(dept, 0) + 1
        idx = dept_index[dept]

        # Practitioner resource
        entries.append({
            "fullUrl": f"Practitioner/{pr['id']}",
            "resource": mk_practitioner(pr),
            "request": {"method": "PUT", "url": f"Practitioner/{pr['id']}"},
        })
        pract_count += 1

        # Schedule
        sched = mk_schedule(pr, idx)
        sched_id = sched["id"]
        entries.append({
            "fullUrl": f"Schedule/{sched_id}",
            "resource": sched,
            "request": {"method": "PUT", "url": f"Schedule/{sched_id}"},
        })
        schedule_count += 1

        # Slots for each working day
        for day_offset in range(START_DAY, DAYS_AHEAD + 1):
            d = date.today() + timedelta(days=day_offset)
            if d.weekday() == 6:  # skip Sunday
                continue
            for time_str in MORNING_TIMES + AFTERNOON_TIMES:
                status = "busy" if random.random() < BUSY_RATIO else "free"
                entries.append({
                    "resource": mk_slot(sched_id, d, time_str, status),
                    "request": {"method": "POST", "url": "Slot"},
                })
                slot_count += 1

    return (
        {"resourceType": "Bundle", "type": "transaction", "entry": entries},
        pract_count, schedule_count, slot_count,
    )


def main():
    global DAYS_AHEAD, START_DAY, CHUNK
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--days", type=int, default=DAYS_AHEAD, help="Tạo slot đến ngày thứ N kể từ hôm nay (mặc định 30)")
    parser.add_argument("--start", type=int, default=START_DAY, help="Bắt đầu từ ngày thứ N kể từ hôm nay (mặc định 1). Slot tạo bằng POST nên KHÔNG idempotent — dùng --start để tránh tạo trùng lên khoảng đã có.")
    parser.add_argument("--chunk", type=int, default=CHUNK, help=f"Số entry mỗi transaction (mặc định {CHUNK})")
    args = parser.parse_args()
    DAYS_AHEAD = args.days
    START_DAY = args.start
    CHUNK = args.chunk

    bundle, n_pract, n_sched, n_slot = build_bundle()
    total = len(bundle["entry"])

    print(f"Generated: {n_pract} Practitioner | {n_sched} Schedule | {n_slot} Slot")
    print(f"  Total bundle entries: {total}")

    if args.dry_run:
        print("(Dry run — nothing pushed)")
        return

    url = os.environ.get("AIDBOX_URL", "").rstrip("/")
    cid = os.environ.get("AIDBOX_CLIENT_ID", "")
    sec = os.environ.get("AIDBOX_CLIENT_SECRET", "")
    if not url or not cid or not sec:
        sys.exit("Missing AIDBOX_URL / AIDBOX_CLIENT_ID / AIDBOX_CLIENT_SECRET env")

    # Đẩy theo lô. Thứ tự entry được giữ nguyên (Practitioner → Schedule → Slot của nó)
    # nên lô sau tham chiếu Schedule đã tạo ở lô trước vẫn hợp lệ.
    entries = bundle["entry"]
    accepted = 0
    n_chunks = (total + CHUNK - 1) // CHUNK
    print(f"Pushing {total} entries to Aidbox in {n_chunks} chunk(s) of {CHUNK}...")

    for i in range(0, total, CHUNK):
        part = entries[i:i + CHUNK]
        sub = {"resourceType": "Bundle", "type": "transaction", "entry": part}
        r = httpx.post(f"{url}/fhir", json=sub, auth=(cid, sec), timeout=300)
        if not (200 <= r.status_code < 300):
            print(f"  [FAIL] chunk {i // CHUNK + 1}/{n_chunks} — HTTP {r.status_code}: {r.text[:300]}")
            sys.exit(1)
        ok = sum(1 for e in r.json().get("entry", []) if e.get("response", {}).get("status", "").startswith(("200", "201")))
        accepted += ok
        print(f"  chunk {i // CHUNK + 1}/{n_chunks}: {ok}/{len(part)} ok")

    print(f"  [OK] Accepted entries: {accepted}/{total}")


if __name__ == "__main__":
    main()
