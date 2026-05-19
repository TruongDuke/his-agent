"""FHIR data routes — practitioners, patients, appointments, observations, patient detail, register."""

import asyncio as _asyncio
import httpx
from datetime import date as _date
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Query

from api.deps import _aidbox, _entries, _patient_name, _pract_name

router = APIRouter()


# ── /api/practitioners ────────────────────────────────────────
@router.get("/api/practitioners")
async def api_practitioners():
    url, auth = _aidbox()
    if not url:
        raise HTTPException(503, "AIDBOX_URL not configured")

    async with httpx.AsyncClient(timeout=15, auth=auth) as client:
        r = await client.get(f"{url}/fhir/Practitioner",
                             params={"_count": "50", "_sort": "family"})
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text[:300])
        bundle = r.json()

    rows = []
    for p in _entries(bundle, "Practitioner"):
        qual = (p.get("qualification") or [{}])[0]
        specialty = (
            (qual.get("code") or {}).get("text")
            or ((qual.get("code") or {}).get("coding") or [{}])[0].get("display", "")
        )
        rows.append({
            "id":        p.get("id", ""),
            "name":      _pract_name(p),
            "specialty": specialty,
        })
    return {"total": len(rows), "practitioners": rows}


# ── /api/patients ─────────────────────────────────────────────
@router.get("/api/patients")
async def api_patients(q: str = "", count: int = Query(default=30, alias="_count")):
    url, auth = _aidbox()
    if not url:
        raise HTTPException(503, "AIDBOX_URL not configured")

    params: dict = {"_count": str(count), "_sort": "-_lastUpdated"}
    if q:
        q = q.strip()
        if q.lstrip("+").isdigit() or (q.startswith("0") and len(q) >= 9):
            params["telecom"] = q
        else:
            tokens = q.split()
            if len(tokens) == 1:
                params["family"] = tokens[0]
            else:
                params["family"] = tokens[0]
                params["given"]  = " ".join(tokens[1:])

    async with httpx.AsyncClient(timeout=15, auth=auth) as client:
        r = await client.get(f"{url}/fhir/Patient", params=params)
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text[:300])
        bundle = r.json()

    patients = _entries(bundle, "Patient")
    rows = []
    for p in patients:
        phone = next(
            (t.get("value") for t in (p.get("telecom") or []) if t.get("system") == "phone"),
            ""
        )
        rows.append({
            "id":         p.get("id", ""),
            "name":       _patient_name(p),
            "gender":     "Nam" if p.get("gender") == "male" else "Nữ" if p.get("gender") == "female" else "",
            "birth_date": p.get("birthDate", ""),
            "phone":      phone,
        })
    return {"total": bundle.get("total", len(rows)), "patients": rows}


# ── /api/appointments ─────────────────────────────────────────
@router.get("/api/appointments")
async def api_appointments(date_str: str = "", practitioner_id: str = "",
                           date_from: str = "", date_to: str = ""):
    url, auth = _aidbox()
    if not url:
        raise HTTPException(503, "AIDBOX_URL not configured")

    if date_from or date_to:
        d_from = date_from or str(_date.today())
        d_to   = date_to   or str(_date.today())
        params = [
            ("date",   f"ge{d_from}T00:00:00"),
            ("date",   f"le{d_to}T23:59:59"),
            ("_count", "200"),
        ]
    else:
        target = date_str or str(_date.today())
        params = [
            ("date", f"ge{target}T00:00:00"),
            ("date", f"le{target}T23:59:59"),
            ("_count", "100"),
        ]
    if practitioner_id:
        params.append(("actor", f"Practitioner/{practitioner_id}"))

    async with httpx.AsyncClient(timeout=20, auth=auth) as client:
        r = await client.get(f"{url}/fhir/Appointment", params=params)
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text[:300])
        bundle = r.json()
        appointments = _entries(bundle, "Appointment")

        # Collect patient + practitioner IDs
        patient_ids = set()
        pract_ids   = set()
        for appt in appointments:
            for part in appt.get("participant") or []:
                ref = (part.get("actor") or {}).get("reference", "")
                if ref.startswith("Patient/"):
                    patient_ids.add(ref.split("/")[1])
                elif ref.startswith("Practitioner/"):
                    pract_ids.add(ref.split("/")[1])

        # Batch-fetch patients
        p_names: dict[str, str] = {}
        if patient_ids:
            r2 = await client.get(f"{url}/fhir/Patient",
                                  params={"_id": ",".join(patient_ids), "_count": "100"})
            for p in _entries(r2.json(), "Patient"):
                p_names[p["id"]] = _patient_name(p)

        # Batch-fetch practitioners
        pr_names: dict[str, str] = {}
        if pract_ids:
            r3 = await client.get(f"{url}/fhir/Practitioner",
                                  params={"_id": ",".join(pract_ids), "_count": "100"})
            for p in _entries(r3.json(), "Practitioner"):
                pr_names[p["id"]] = _pract_name(p)

    rows = []
    for appt in appointments:
        patient_name = ""
        pract_name   = ""
        for part in appt.get("participant") or []:
            ref = (part.get("actor") or {}).get("reference", "")
            if ref.startswith("Patient/"):
                patient_name = p_names.get(ref.split("/")[1], "")
            elif ref.startswith("Practitioner/"):
                pract_name = pr_names.get(ref.split("/")[1], "")

        st = (appt.get("serviceType") or [{}])[0]
        coding = ((st.get("concept") or {}).get("coding") or [{}])[0]
        dept = coding.get("display", coding.get("code", ""))

        reason_list = appt.get("reason") or []
        reason = (reason_list[0].get("concept") or {}).get("text", "") if reason_list else ""

        rows.append({
            "id":           appt.get("id", ""),
            "patient_name": patient_name,
            "practitioner": pract_name,
            "department":   dept,
            "start":        (appt.get("start") or "")[:16].replace("T", " "),
            "status":       appt.get("status", ""),
            "reason":       reason,
        })

    rows.sort(key=lambda a: a["start"])
    date_label = locals().get("d_from") or locals().get("target", "")
    return {"date": date_label, "total": len(rows), "appointments": rows}


# ── /api/observations ─────────────────────────────────────────
@router.get("/api/observations")
async def api_observations(patient_id: str = "", category: str = "all",
                           count: int = Query(default=30, alias="_count")):
    url, auth = _aidbox()
    if not url:
        raise HTTPException(503, "AIDBOX_URL not configured")

    params: list = [("_count", str(count)), ("_sort", "-date")]
    if patient_id:
        params.append(("subject", f"Patient/{patient_id}"))
    if category == "vital-signs":
        params.append(("category", "vital-signs"))
    elif category == "laboratory":
        params.append(("category", "laboratory"))

    async with httpx.AsyncClient(timeout=15, auth=auth) as client:
        r = await client.get(f"{url}/fhir/Observation", params=params)
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text[:300])
        bundle = r.json()
        observations = _entries(bundle, "Observation")

        # Collect patient IDs
        patient_ids = set()
        for obs in observations:
            ref = (obs.get("subject") or {}).get("reference", "")
            if ref.startswith("Patient/"):
                patient_ids.add(ref.split("/")[1])

        p_names: dict[str, str] = {}
        if patient_ids:
            r2 = await client.get(f"{url}/fhir/Patient",
                                  params={"_id": ",".join(patient_ids), "_count": "100"})
            for p in _entries(r2.json(), "Patient"):
                p_names[p["id"]] = _patient_name(p)

    _LOINC_VI = {
        # Sinh hiệu
        "8480-6": "HA tâm thu",      "8462-4": "HA tâm trương",
        "29463-7": "Cân nặng",        "8302-2": "Chiều cao",
        "39156-5": "BMI",             "8867-4": "Nhịp tim",
        "9279-1":  "Nhịp thở",        "8310-5": "Nhiệt độ",
        "59408-5": "SpO2",
        # Sinh hóa
        "2339-0": "Glucose máu",      "4548-4": "HbA1c",
        "2093-3": "Cholesterol TP",   "2160-0": "Creatinine",
        "3094-0": "Ure",
        # CBC
        "6690-2": "Bạch cầu (WBC)",   "789-8":  "Hồng cầu (RBC)",
        "718-7":  "Hemoglobin",        "4544-3": "Hematocrit",
        "777-3":  "Tiểu cầu (PLT)",    "787-2":  "MCV",
        "785-6":  "MCH",               "786-4":  "MCHC",
        "736-9":  "Lymphocyte %",      "4650-8": "Neutrophil %",
    }

    def _node_val(node):
        if "valueQuantity" in node:
            vq = node["valueQuantity"]
            return str(vq.get("value", "")), vq.get("unit", vq.get("code", ""))
        if "valueString" in node:
            return node["valueString"], ""
        if "valueCodeableConcept" in node:
            return (node["valueCodeableConcept"].get("text") or
                    ((node["valueCodeableConcept"].get("coding") or [{}])[0]).get("display", "")), ""
        return "", ""

    rows = []
    for obs in observations:
        ref   = (obs.get("subject") or {}).get("reference", "")
        pid   = ref.split("/")[1] if ref.startswith("Patient/") else ""
        date  = (obs.get("effectiveDateTime") or obs.get("issued") or "")[:10]
        pname = p_names.get(pid, "")
        status = obs.get("status", "")

        # CBC panel lưu từng chỉ số trong component → bung ra
        if obs.get("component"):
            for comp in obs["component"]:
                c_coding = ((comp.get("code") or {}).get("coding") or [{}])[0]
                c_name   = _LOINC_VI.get(c_coding.get("code","")) or c_coding.get("display","")
                if not c_name:
                    continue
                val, unit = _node_val(comp)
                rows.append({"patient_name": pname, "name": c_name,
                             "value": val, "unit": unit, "status": status, "date": date})
            continue

        coding = ((obs.get("code") or {}).get("coding") or [{}])[0]
        name   = _LOINC_VI.get(coding.get("code","")) or coding.get("display") or \
                 (obs.get("code") or {}).get("text", "")
        value, unit = _node_val(obs)

        rows.append({"patient_name": pname, "name": name,
                     "value": value, "unit": unit, "status": status, "date": date})

    return {"total": bundle.get("total", len(rows)), "observations": rows}


# ── /api/patient/{id} — detail panel ──────────────────────────
@router.get("/api/patient/{patient_id}")
async def api_patient_detail(patient_id: str):
    url, auth = _aidbox()
    if not url:
        raise HTTPException(503, "AIDBOX_URL not configured")

    today = str(_date.today())

    async with httpx.AsyncClient(timeout=15, auth=auth) as client:
        pt_r, obs_r, appt_r = await _asyncio.gather(
            client.get(f"{url}/fhir/Patient/{patient_id}"),
            client.get(f"{url}/fhir/Observation",
                       params={"subject": f"Patient/{patient_id}",
                               "_sort": "-date", "_count": "20"}),
            client.get(f"{url}/fhir/Appointment",
                       params=[("patient", f"Patient/{patient_id}"),
                                ("date", f"ge{today}T00:00:00"),
                                ("_sort", "date"), ("_count", "10")]),
        )

    # ── Patient demographics ──
    if pt_r.status_code >= 400:
        raise HTTPException(pt_r.status_code, "Patient not found")
    pt = pt_r.json()
    nm   = (pt.get("name") or [{}])[0]
    name = f"{nm.get('family', '')} {' '.join(nm.get('given') or [])}".strip()
    phone = next((t.get("value") for t in (pt.get("telecom") or [])
                  if t.get("system") == "phone"), "")
    birth = pt.get("birthDate", "")
    age   = ""
    if birth:
        try:
            age = str(_date.today().year - int(birth[:4]))
        except Exception:
            pass

    # ── Observations → split vital-signs / laboratory ──
    _LOINC_VI = {
        # Sinh hiệu
        "8480-6":  ("HA tâm thu",     "vital"), "8462-4":  ("HA tâm trương", "vital"),
        "29463-7": ("Cân nặng",       "vital"), "8302-2":  ("Chiều cao",     "vital"),
        "39156-5": ("BMI",            "vital"), "8867-4":  ("Nhịp tim",      "vital"),
        "9279-1":  ("Nhịp thở",       "vital"), "8310-5":  ("Nhiệt độ",      "vital"),
        "59408-5": ("SpO2",           "vital"),
        # Sinh hóa
        "2339-0":  ("Glucose máu",    "lab"),   "4548-4":  ("HbA1c",         "lab"),
        "2093-3":  ("Cholesterol TP", "lab"),   "2160-0":  ("Creatinine",    "lab"),
        "3094-0":  ("Ure",            "lab"),
        # CBC
        "6690-2":  ("Bạch cầu (WBC)", "lab"),   "789-8":   ("Hồng cầu (RBC)","lab"),
        "718-7":   ("Hemoglobin",     "lab"),   "4544-3":  ("Hematocrit",    "lab"),
        "777-3":   ("Tiểu cầu (PLT)", "lab"),   "787-2":   ("MCV",           "lab"),
        "785-6":   ("MCH",            "lab"),   "786-4":   ("MCHC",          "lab"),
        "736-9":   ("Lymphocyte %",   "lab"),   "4650-8":  ("Neutrophil %",  "lab"),
    }
    vitals, labs = [], []
    seen = set()

    def _extract_val(obs_node):
        """Trả về (value_str, unit) từ một node observation hoặc component."""
        if "valueQuantity" in obs_node:
            vq = obs_node["valueQuantity"]
            return str(vq.get("value", "")), vq.get("unit", vq.get("code", ""))
        if "valueString" in obs_node:
            return obs_node["valueString"], ""
        return "", ""

    for obs in _entries(obs_r.json(), "Observation"):
        coding = ((obs.get("code") or {}).get("coding") or [{}])[0]
        loinc  = coding.get("code", "")
        date   = (obs.get("effectiveDateTime") or obs.get("issued") or "")[:10]
        cat_raw = ((obs.get("category") or [{}])[0].get("coding") or [{}])[0].get("code", "lab")

        # CBC panel lưu từng chỉ số trong component → bung ra
        if obs.get("component"):
            for comp in obs["component"]:
                c_coding = ((comp.get("code") or {}).get("coding") or [{}])[0]
                c_loinc  = c_coding.get("code", "")
                c_meta   = _LOINC_VI.get(c_loinc)
                c_label  = (c_meta[0] if c_meta else None) or c_coding.get("display", "")
                if not c_label or c_label in seen:
                    continue
                seen.add(c_label)
                val, unit = _extract_val(comp)
                labs.append({"name": c_label, "value": val, "unit": unit, "date": date})
            continue

        meta  = _LOINC_VI.get(loinc)
        label = (meta[0] if meta else None) or coding.get("display") or (obs.get("code") or {}).get("text", "")
        if not label or label in seen:
            continue
        seen.add(label)
        cat = (meta[1] if meta else None) or cat_raw

        val, unit = _extract_val(obs)
        row = {"name": label, "value": val, "unit": unit, "date": date}
        (vitals if cat == "vital" else labs).append(row)

    # ── Upcoming appointments ──
    appts = []
    for appt in _entries(appt_r.json(), "Appointment"):
        pract_name = ""
        for part in appt.get("participant") or []:
            ref = (part.get("actor") or {}).get("reference", "")
            if ref.startswith("Practitioner/"):
                pract_name = ref  # resolved below if needed

        st     = (appt.get("serviceType") or [{}])[0]
        coding = ((st.get("concept") or {}).get("coding") or [{}])[0]
        dept   = coding.get("display", coding.get("code", ""))
        start  = (appt.get("start") or "")[:16].replace("T", " ")
        appts.append({"start": start, "department": dept, "status": appt.get("status", "")})

    return {
        "id":         patient_id,
        "name":       name,
        "gender":     "Nam" if pt.get("gender") == "male" else "Nữ" if pt.get("gender") == "female" else "",
        "age":        age,
        "birth_date": birth,
        "phone":      phone,
        "vitals":     vitals[:6],
        "labs":       labs[:8],
        "appointments": appts,
    }


# ── /api/dengue/{patient_id} — GET: sàng lọc SXHD từ CBC mới nhất ──
@router.get("/api/dengue/{patient_id}")
async def api_dengue_screening(patient_id: str):
    url, auth = _aidbox()
    if not url:
        raise HTTPException(503, "AIDBOX_URL not configured")

    async with httpx.AsyncClient(timeout=15, auth=auth) as client:
        pt_r, obs_r = await _asyncio.gather(
            client.get(f"{url}/fhir/Patient/{patient_id}"),
            client.get(f"{url}/fhir/Observation", params={
                "subject": f"Patient/{patient_id}",
                "code":    "http://loinc.org|58410-2",
                "_sort":   "-date",
                "_count":  "2",
            }),
        )

    gender = ""
    if pt_r.status_code < 400:
        gender_fhir = (pt_r.json().get("gender") or "").lower()
        gender = "male" if gender_fhir == "male" else ("female" if gender_fhir == "female" else "")

    if obs_r.status_code >= 400:
        raise HTTPException(obs_r.status_code, "Không tải được Observation")

    obs_list = _entries(obs_r.json(), "Observation")
    if not obs_list:
        return {"available": False, "reason": "Chưa có kết quả CBC"}

    latest   = obs_list[0]
    obs_date = (latest.get("effectiveDateTime") or latest.get("issued") or "")[:10]

    _COMP_MAP = {
        "777-3": "plt", "6690-2": "wbc", "4544-3": "hct",
        "718-7": "hgb", "1920-8": "ast", "1742-6": "alt",
    }
    values: dict = {}
    for comp in (latest.get("component") or []):
        c_code = ((comp.get("code") or {}).get("coding") or [{}])[0].get("code", "")
        key = _COMP_MAP.get(c_code)
        if key:
            vq  = comp.get("valueQuantity") or {}
            val = vq.get("value")
            if val is not None:
                values[key] = float(val)

    if "plt" not in values:
        return {"available": False, "reason": "CBC không có chỉ số PLT"}

    # PLT trước để tính xu hướng
    if len(obs_list) > 1:
        for comp in (obs_list[1].get("component") or []):
            c_code = ((comp.get("code") or {}).get("coding") or [{}])[0].get("code", "")
            if c_code == "777-3":
                vq  = comp.get("valueQuantity") or {}
                val = vq.get("value")
                if val is not None:
                    values["plt_previous"] = float(val)
                break

    import sys as _sys
    from pathlib import Path as _Path
    _dengue_dir = str(_Path(__file__).parent.parent.parent / "tools" / "dengue")
    if _dengue_dir not in _sys.path:
        _sys.path.insert(0, _dengue_dir)
    from dengue_cbc_predict import run as _dengue_run  # type: ignore

    result = _dengue_run({**values, "gender": gender})
    cbc_used = {k: values[k] for k in ("plt", "wbc", "hct", "hgb") if k in values}
    return {"available": True, "obs_date": obs_date, "cbc_used": cbc_used, "screening": result}


# ── /api/register-patient ─────────────────────────────────────
# ── /api/cbc — POST: lưu kết quả CBC thủ công từ UI ─────────────
class CbcRequest(BaseModel):
    patient_id:   str
    plt:          float
    wbc:          float | None = None
    hct:          float | None = None
    hgb:          float | None = None
    ast:          float | None = None
    alt:          float | None = None
    fever_day:    float | None = None
    collected_at: str   | None = None

@router.post("/api/cbc")
async def api_create_cbc(body: CbcRequest):
    import sys as _sys
    from pathlib import Path as _Path
    _tool = str(_Path(__file__).parent.parent.parent / "tools" / "fhir")
    if _tool not in _sys.path:
        _sys.path.insert(0, _tool)
    from fhir_create_cbc import run  # type: ignore
    args = {k: v for k, v in body.dict().items() if v is not None}
    result = run(args)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


class RegisterPatientRequest(BaseModel):
    name: str
    gender: str
    birth_date: str
    phone: str = ""
    address: str = ""


@router.post("/api/register-patient")
async def api_register_patient(body: RegisterPatientRequest):
    url, auth = _aidbox()
    if not url:
        raise HTTPException(503, "AIDBOX_URL not configured")

    parts = body.name.strip().split()
    family = parts[0] if parts else body.name
    given  = parts[1:] if len(parts) > 1 else []

    fhir_patient: dict = {
        "resourceType": "Patient",
        "name": [{"use": "official", "family": family, "given": given}],
        "gender": body.gender,
        "birthDate": body.birth_date,
    }
    if body.phone:
        fhir_patient["telecom"] = [{"system": "phone", "value": body.phone, "use": "mobile"}]
    if body.address:
        fhir_patient["address"] = [{"use": "home", "text": body.address}]

    async with httpx.AsyncClient(timeout=15, auth=auth) as client:
        r = await client.post(f"{url}/fhir/Patient", json=fhir_patient)

    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text[:300])

    created = r.json()
    return {"patient_id": created.get("id", ""), "name": body.name}
