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


def _entries(bundle: dict, rtype: str) -> list[dict]:
    return [
        e["resource"] for e in (bundle.get("entry") or [])
        if e.get("resource", {}).get("resourceType") == rtype
    ]
