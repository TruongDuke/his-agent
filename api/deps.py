"""Shared FHIR helper functions used across multiple route modules."""

import os


def _aidbox():
    url = os.getenv("AIDBOX_URL", "").rstrip("/")
    cid = os.getenv("AIDBOX_CLIENT_ID", "")
    sec = os.getenv("AIDBOX_CLIENT_SECRET", "")
    return url, (cid, sec) if cid and sec else None


def _patient_name(p: dict) -> str:
    nm = (p.get("name") or [{}])[0]
    return f"{nm.get('family', '')} {' '.join(nm.get('given') or [])}".strip()


def _pract_name(p: dict) -> str:
    nm = (p.get("name") or [{}])[0]
    name = f"{nm.get('family', '')} {' '.join(nm.get('given') or [])}".strip()
    return f"BS. {name}" if name else ""


def _external_his_id(p: dict) -> str:
    """Mã bệnh nhân bên HIS ngoài, rỗng nếu là bệnh nhân của viện mình.

    Hồ sơ do bệnh viện khác đẩy sang được gắn identifier này lúc ánh xạ
    (api/his_mapping.py). Bác sĩ cần thấy được nguồn gốc: dữ liệu ngoài viện nên
    đối chiếu lại trước khi ra quyết định, không mặc nhiên tin như dữ liệu tự làm.
    """
    for i in p.get("identifier") or []:
        if (i.get("system") or "") == "urn:his-agent:external-his":
            return i.get("value") or ""
    return ""


def _entries(bundle: dict, rtype: str) -> list[dict]:
    return [
        e["resource"] for e in (bundle.get("entry") or [])
        if e.get("resource", {}).get("resourceType") == rtype
    ]
