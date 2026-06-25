"""Shared Aidbox FHIR HTTP client for fhir_* tools.

Reads AIDBOX_URL / AIDBOX_CLIENT_ID / AIDBOX_CLIENT_SECRET from env.
Leading underscore in filename prevents Sphinx from loading this as a tool.
"""
from __future__ import annotations
import os
import httpx


def _config() -> tuple[str, str, str]:
    url = os.environ.get("AIDBOX_URL", "").rstrip("/")
    cid = os.environ.get("AIDBOX_CLIENT_ID", "")
    sec = os.environ.get("AIDBOX_CLIENT_SECRET", "")
    return url, cid, sec


def fhir_get(path: str, params: dict | None = None, timeout: float = 15.0) -> dict:
    url, cid, sec = _config()
    if not url:
        return {"error": "AIDBOX_URL not configured"}

    full = f"{url}/fhir/{path.lstrip('/')}"
    auth = (cid, sec) if cid and sec else None
    try:
        with httpx.Client(timeout=timeout, auth=auth) as client:
            resp = client.get(full, params=params or {}) # ← GỬI yêu cầu qua mạng tới bệnh viện
        if resp.status_code >= 400:
            return {"error": f"FHIR {resp.status_code}: {resp.text[:300]}"}
        return resp.json()
    except httpx.TimeoutException:
        return {"error": f"Timeout calling {full}"}
    except Exception as e:
        return {"error": f"Request failed: {e}"}


def fhir_post(path: str, body: dict, timeout: float = 15.0) -> dict:
    url, cid, sec = _config()
    if not url:
        return {"error": "AIDBOX_URL not configured"}

    full = f"{url}/fhir/{path.lstrip('/')}"
    auth = (cid, sec) if cid and sec else None
    try:
        with httpx.Client(timeout=timeout, auth=auth) as client:
            resp = client.post(full, json=body, headers={"Content-Type": "application/json"})
        if resp.status_code >= 400:
            return {"error": f"FHIR {resp.status_code}: {resp.text[:300]}"}
        return resp.json()
    except httpx.TimeoutException:
        return {"error": f"Timeout calling {full}"}
    except Exception as e:
        return {"error": f"Request failed: {e}"}


def extract_entries(bundle: dict) -> list[dict]:
    """Extract resource list from a FHIR Bundle."""
    if not isinstance(bundle, dict):
        return []
    return [e.get("resource", {}) for e in bundle.get("entry", []) if isinstance(e, dict)]


def calc_age(birth_date: str | None) -> int | None:
    if not birth_date:
        return None
    try:
        from datetime import date
        y, m, d = map(int, birth_date.split("-")[:3])
        today = date.today()
        return today.year - y - ((today.month, today.day) < (m, d))
    except Exception:
        return None


def patient_summary(p: dict) -> dict:
    """Compact Patient -> tiny dict for LLM context."""
    name = (p.get("name") or [{}])[0]
    given = " ".join(name.get("given") or [])
    full_name = f"{name.get('family','')} {given}".strip()
    identifiers = p.get("identifier") or []
    bhyt = next((i.get("value") for i in identifiers if "bhyt" in (i.get("system") or "")), None)
    cccd = next((i.get("value") for i in identifiers if "cccd" in (i.get("system") or "")), None)
    meta = p.get("meta") or {}
    last_updated = (meta.get("lastUpdated") or "")[:16].replace("T", " ")
    return {
        "id": p.get("id"),
        "name": full_name,
        "gender": p.get("gender"),
        "birth_date": p.get("birthDate"),
        "age": calc_age(p.get("birthDate")),
        "bhyt": bhyt,
        "cccd": cccd,
        "phone": next((t.get("value") for t in (p.get("telecom") or []) if t.get("system") == "phone"), None),
        "_source": f"FHIR R5 · Aidbox · Patient/{p.get('id')} · cập nhật {last_updated}" if last_updated else f"FHIR R5 · Aidbox · Patient/{p.get('id')}",
    }
