"""Get full patient medical history from the hospital HIS (FHIR R5)."""

TOOL_NAME = "fhir_get_patient_history"
CATEGORY = "Healthcare"
DESCRIPTION = (
    "Lấy toàn bộ hồ sơ bệnh án của 1 bệnh nhân từ HIS (FHIR R5). "
    "Gồm: thông tin cơ bản, các lần khám (Encounter), chẩn đoán (Condition), "
    "đơn thuốc (MedicationRequest), và các chỉ số/xét nghiệm (Observation). "
    "Input là patient_id dạng UUID (lấy từ fhir_search_patient)."
)
ARGS_SCHEMA = {
    "patient_id": "string — UUID của bệnh nhân (lấy từ fhir_search_patient)",
}


def run(args: dict) -> dict:
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from _aidbox_client import fhir_get, extract_entries, patient_summary

    pid = str(args.get("patient_id") or "").strip()
    if not pid:
        return {"error": "patient_id is required"}

    # Get patient
    patient = fhir_get(f"Patient/{pid}")
    if isinstance(patient, dict) and "error" in patient:
        return patient
    if patient.get("resourceType") != "Patient":
        return {"error": f"Patient not found: {pid}"}

    subject_ref = f"Patient/{pid}"

    # Parallel fetches
    enc_bundle = fhir_get("Encounter", {"subject": subject_ref, "_sort": "-date"})
    cond_bundle = fhir_get("Condition", {"subject": subject_ref})
    med_bundle = fhir_get("MedicationRequest", {"subject": subject_ref})
    obs_bundle = fhir_get("Observation", {"subject": subject_ref})

    # Normalize
    encounters = []
    for e in extract_entries(enc_bundle):
        st = e.get("serviceType") or []
        dept = None
        if st and isinstance(st, list):
            concept = st[0].get("concept") if isinstance(st[0], dict) else None
            if concept:
                coding = (concept.get("coding") or [{}])[0]
                dept = coding.get("display") or coding.get("code")
        reason = None
        r = e.get("reason") or []
        if r and isinstance(r[0], dict):
            val = (r[0].get("value") or [{}])[0]
            if isinstance(val, dict):
                concept = val.get("concept") or {}
                coding = (concept.get("coding") or [{}])[0]
                reason = concept.get("text") or coding.get("display")
        period = e.get("actualPeriod") or {}
        encounters.append({
            "id": e.get("id"),
            "date": (period.get("start") or "")[:10],
            "department": dept,
            "reason": reason,
            "status": e.get("status"),
        })

    conditions = []
    for c in extract_entries(cond_bundle):
        code = c.get("code") or {}
        coding = (code.get("coding") or [{}])[0]
        status = ((c.get("clinicalStatus") or {}).get("coding") or [{}])[0].get("code")
        conditions.append({
            "date": c.get("recordedDate"),
            "icd10": coding.get("code"),
            "name": code.get("text") or coding.get("display"),
            "status": status,
        })

    medications = []
    for m in extract_entries(med_bundle):
        med_concept = (m.get("medication") or {}).get("concept") or {}
        med_coding = (med_concept.get("coding") or [{}])[0]
        dosage = (m.get("dosageInstruction") or [{}])[0].get("text")
        medications.append({
            "date": m.get("authoredOn"),
            "name": med_concept.get("text") or med_coding.get("display"),
            "dosage": dosage,
            "status": m.get("status"),
        })

    observations = []
    for o in extract_entries(obs_bundle):
        code = (o.get("code") or {}).get("coding") or [{}]
        name = code[0].get("display") or code[0].get("code") if code else None
        val = o.get("valueQuantity")
        value_str = None
        if val:
            value_str = f"{val.get('value')} {val.get('unit') or ''}".strip()
        elif o.get("component"):
            parts = []
            for comp in o["component"]:
                c_code = (comp.get("code") or {}).get("coding") or [{}]
                c_val = comp.get("valueQuantity") or {}
                parts.append(f"{c_code[0].get('display', 'value')}: {c_val.get('value')} {c_val.get('unit', '')}")
            value_str = "; ".join(parts)
        observations.append({
            "date": (o.get("effectiveDateTime") or "")[:10],
            "measure": name,
            "value": value_str,
        })

    return {
        "patient": patient_summary(patient),
        "summary": {
            "visits_count": len(encounters),
            "active_conditions": [c["name"] for c in conditions if c.get("status") == "active"],
            "current_medications": [m["name"] for m in medications if m.get("status") == "active"],
        },
        "encounters": encounters,
        "conditions": conditions,
        "medications": medications,
        "observations": observations,
    }
