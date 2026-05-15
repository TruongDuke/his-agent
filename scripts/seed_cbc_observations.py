"""Seed CBC Observation (panel + component) vào Aidbox FHIR R5.

Tạo 6 kịch bản lâm sàng:
  1. Nguyễn Văn A   (nam)  — SXHD cảnh báo: PLT 45, WBC 2.8, HCT tăng
  2. Trần Thị B     (nữ)   — SXHD điển hình: PLT 72, WBC 3.1
  3. Lê Văn C       (nam)  — Bình thường
  4. Đặng Quang Huy (nam)  — SXHD nặng: PLT 18, AST/ALT ≥ 1000
  5. Ngô Phương Thảo(nữ)   — Theo dõi: PLT 115, WBC 4.2 (borderline)
  6. Hoàng Hữu Phúc (nam)  — SXHD ngày 4: PLT 85, WBC 3.5, HCT tăng nhẹ
"""

import os, json, sys
from datetime import datetime, timezone, timedelta
import httpx

AIDBOX_URL  = os.getenv("AIDBOX_URL",           "https://azjfirhwbo.edge.aidbox.app")
AIDBOX_USER = os.getenv("AIDBOX_CLIENT_ID",     "sphinx-dev")
AIDBOX_PASS = os.getenv("AIDBOX_CLIENT_SECRET", "sphinx-secret-2026")

TZ7 = timezone(timedelta(hours=7))


def _dt(days_ago: int = 0) -> str:
    t = datetime.now(TZ7) - timedelta(days=days_ago)
    return t.strftime("%Y-%m-%dT%H:%M:%S+07:00")


def _component(loinc: str, display: str, value: float, unit: str, ucum: str) -> dict:
    return {
        "code": {"coding": [{"system": "http://loinc.org", "code": loinc, "display": display}]},
        "valueQuantity": {
            "value": value,
            "unit": unit,
            "system": "http://unitsofmeasure.org",
            "code": ucum,
        },
    }


def _cbc_observation(patient_id: str, dt: str, components: list) -> dict:
    return {
        "resourceType": "Observation",
        "status": "final",
        "category": [{
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                "code": "laboratory",
            }]
        }],
        "code": {"coding": [{
            "system": "http://loinc.org",
            "code": "58410-2",
            "display": "CBC panel",
        }]},
        "subject": {"reference": f"Patient/{patient_id}"},
        "effectiveDateTime": dt,
        "component": components,
    }


# ─── Kịch bản ───────────────────────────────────────────────────────

SCENARIOS = [
    {
        "label": "Nguyễn Văn A — SXHD cảnh báo",
        "patient_id": "18c3d962-a697-4ce5-8eac-de79c1516690",
        "dt": _dt(0),
        "components": [
            _component("777-3",  "Platelets",    45.0,  "10*3/uL", "10*3/uL"),
            _component("6690-2", "WBC",           2.8,  "10*3/uL", "10*3/uL"),
            _component("4544-3", "Hematocrit",   52.0,  "%",       "%"),
            _component("718-7",  "Hemoglobin",   15.8,  "g/dL",    "g/dL"),
            _component("1920-8", "AST",          520.0, "U/L",     "U/L"),
            _component("1742-6", "ALT",          480.0, "U/L",     "U/L"),
        ],
    },
    {
        "label": "Trần Thị B — SXHD điển hình",
        "patient_id": "01c3ca02-0e27-4f0d-9301-a080b6378bf5",
        "dt": _dt(1),
        "components": [
            _component("777-3",  "Platelets",    72.0, "10*3/uL", "10*3/uL"),
            _component("6690-2", "WBC",           3.1, "10*3/uL", "10*3/uL"),
            _component("4544-3", "Hematocrit",   40.0, "%",       "%"),
            _component("718-7",  "Hemoglobin",   12.5, "g/dL",    "g/dL"),
            _component("1920-8", "AST",           95.0, "U/L",    "U/L"),
            _component("1742-6", "ALT",           88.0, "U/L",    "U/L"),
        ],
    },
    {
        "label": "Lê Văn C — Bình thường",
        "patient_id": "20e90cb0-83b5-4170-a93e-680f9603148f",
        "dt": _dt(0),
        "components": [
            _component("777-3",  "Platelets",   210.0, "10*3/uL", "10*3/uL"),
            _component("6690-2", "WBC",           7.2, "10*3/uL", "10*3/uL"),
            _component("4544-3", "Hematocrit",   44.0, "%",       "%"),
            _component("718-7",  "Hemoglobin",   14.8, "g/dL",    "g/dL"),
            _component("1920-8", "AST",           28.0, "U/L",    "U/L"),
            _component("1742-6", "ALT",           22.0, "U/L",    "U/L"),
        ],
    },
    {
        "label": "Đặng Quang Huy — SXHD nặng (suy gan)",
        "patient_id": "eb786745-376b-4d90-a5cd-e587dd6a95e2",
        "dt": _dt(0),
        "components": [
            _component("777-3",  "Platelets",    18.0,  "10*3/uL", "10*3/uL"),
            _component("6690-2", "WBC",           2.0,  "10*3/uL", "10*3/uL"),
            _component("4544-3", "Hematocrit",   53.0,  "%",       "%"),
            _component("718-7",  "Hemoglobin",   16.1,  "g/dL",    "g/dL"),
            _component("1920-8", "AST",         1250.0, "U/L",     "U/L"),
            _component("1742-6", "ALT",         1480.0, "U/L",     "U/L"),
        ],
    },
    {
        "label": "Ngô Phương Thảo — Theo dõi (borderline)",
        "patient_id": "817c88d1-4c20-42e7-a289-4f7c28854e5d",
        "dt": _dt(0),
        "components": [
            _component("777-3",  "Platelets",   115.0, "10*3/uL", "10*3/uL"),
            _component("6690-2", "WBC",           4.2, "10*3/uL", "10*3/uL"),
            _component("4544-3", "Hematocrit",   38.5, "%",       "%"),
            _component("718-7",  "Hemoglobin",   12.1, "g/dL",    "g/dL"),
            _component("1920-8", "AST",          145.0, "U/L",    "U/L"),
            _component("1742-6", "ALT",          130.0, "U/L",    "U/L"),
        ],
    },
    {
        "label": "Hoàng Hữu Phúc — SXHD cổ điển ngày 4",
        "patient_id": "1d35dfc4-cf0d-4ded-aa98-568c60ae33b3",
        "dt": _dt(0),
        "components": [
            _component("777-3",  "Platelets",    85.0, "10*3/uL", "10*3/uL"),
            _component("6690-2", "WBC",           3.5, "10*3/uL", "10*3/uL"),
            _component("4544-3", "Hematocrit",   47.0, "%",       "%"),
            _component("718-7",  "Hemoglobin",   14.2, "g/dL",    "g/dL"),
            _component("1920-8", "AST",           62.0, "U/L",    "U/L"),
            _component("1742-6", "ALT",           55.0, "U/L",    "U/L"),
        ],
    },
]


def post_observation(obs: dict) -> tuple:
    resp = httpx.post(
        f"{AIDBOX_URL}/fhir/Observation",
        json=obs,
        auth=(AIDBOX_USER, AIDBOX_PASS),
        headers={"Accept": "application/json"},
    )
    return resp.status_code, resp.text


if __name__ == "__main__":
    print(f"Seeding {len(SCENARIOS)} CBC observations → {AIDBOX_URL}\n")
    for s in SCENARIOS:
        obs = _cbc_observation(s["patient_id"], s["dt"], s["components"])
        status, body = post_observation(obs)
        if status in (200, 201):
            obs_id = json.loads(body).get("id", "?")
            print(f"  ✅ {s['label']}")
            print(f"     → Observation/{obs_id}")
        else:
            print(f"  ❌ {s['label']} — HTTP {status}")
            print(f"     {body[:200]}")
    print("\nDone.")
