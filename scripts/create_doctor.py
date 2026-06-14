"""Tạo tài khoản bác sĩ: tự động tìm FHIR ID có sẵn trước khi tạo mới.

Usage:
    python scripts/create_doctor.py "Nguyễn Thị Hoa" 0900000003 123456
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import httpx
from dotenv import load_dotenv
load_dotenv()

from db import create_user, get_user

def find_fhir_practitioner(name: str) -> tuple[str, str] | None:
    """Tìm Practitioner trong FHIR theo tên. Trả về (fhir_id, full_name) hoặc None."""
    url  = os.getenv("AIDBOX_URL")
    cid  = os.getenv("AIDBOX_CLIENT_ID")
    csec = os.getenv("AIDBOX_CLIENT_SECRET")

    # Lấy toàn bộ danh sách (tối đa 200)
    r = httpx.get(f"{url}/fhir/Practitioner", params={"_count": 200}, auth=(cid, csec), timeout=15)
    if r.status_code != 200:
        return None

    # Chuẩn hóa tên tìm kiếm: lowercase, bỏ dấu cách thừa
    search = name.lower().replace("  ", " ")

    best_id, best_name = None, None
    for entry in r.json().get("entry", []):
        res  = entry["resource"]
        n    = res.get("name", [{}])[0]
        given = " ".join(n.get("given", []))
        family = n.get("family", "")
        full = f"{given} {family}".strip()
        # So sánh tên không phân biệt thứ tự (Vietnamese name order varies)
        given_parts = set(given.lower().split())
        family_parts = set(family.lower().split())
        search_parts = set(search.split())
        if search_parts == given_parts | family_parts or search_parts <= given_parts | family_parts:
            best_id, best_name = res["id"], full
            break

    return (best_id, best_name) if best_id else None


def create_doctor(full_name: str, phone: str, password: str = "123456"):
    if get_user(phone):
        print(f"[!] SĐT {phone} đã tồn tại trong DB")
        return

    match = find_fhir_practitioner(full_name)
    if match:
        fhir_id, fhir_name = match
        print(f"[✓] Tìm thấy FHIR: {fhir_id} ({fhir_name})")
    else:
        # Tạo Practitioner mới
        url  = os.getenv("AIDBOX_URL")
        cid  = os.getenv("AIDBOX_CLIENT_ID")
        csec = os.getenv("AIDBOX_CLIENT_SECRET")
        parts = full_name.strip().split()
        slug  = "prac-" + "-".join(p.lower() for p in parts[-2:])
        r = httpx.put(f"{url}/fhir/Practitioner/{slug}",
            auth=(cid, csec),
            json={"resourceType": "Practitioner", "id": slug,
                  "name": [{"text": full_name, "given": parts[:-1], "family": parts[-1]}]},
            timeout=15)
        fhir_id = r.json().get("id", slug)
        print(f"[+] Tạo FHIR mới: {fhir_id}")

    create_user(phone=phone, password=password, fhir_id=fhir_id, role="doctor", name=full_name)
    print(f"[✓] Account tạo xong: {full_name} | SĐT: {phone} | Pass: {password} | FHIR: {fhir_id}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python scripts/create_doctor.py <tên> <sđt> [password]")
        sys.exit(1)
    name  = sys.argv[1]
    phone = sys.argv[2]
    pwd   = sys.argv[3] if len(sys.argv) > 3 else "123456"
    create_doctor(name, phone, pwd)
