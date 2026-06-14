"""Lấy lịch sử đơn thuốc của bệnh nhân từ HIS (FHIR MedicationRequest).

Group các MedicationRequest có cùng groupIdentifier thành 1 đơn thuốc.
"""
from __future__ import annotations

TOOL_NAME = "fhir_get_prescriptions"
CATEGORY  = "Healthcare"
DESCRIPTION = (
    "Lấy lịch sử đơn thuốc của bệnh nhân (FHIR MedicationRequest R5). "
    "Group các thuốc cùng đơn lại thành 1 prescription. "
    "Sắp xếp theo ngày kê mới nhất → cũ nhất."
)
ARGS_SCHEMA = {
    "patient_id":   "string — ID bệnh nhân. BẮT BUỘC.",
    "active_only":  "boolean — chỉ lấy đơn đang active (mặc định False — lấy hết).",
}


def run(args: dict) -> dict:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
    from _aidbox_client import fhir_get, extract_entries

    pid = str(args.get("patient_id") or "").strip()
    if not pid:
        return {"error": "patient_id là bắt buộc"}

    active_only = bool(args.get("active_only", False))

    params = {
        "patient": f"Patient/{pid}",
        "_count":  "100",
        "_sort":   "-_lastUpdated",
    }
    if active_only:
        params["status"] = "active"

    bundle = fhir_get("MedicationRequest", params)
    if "error" in bundle:
        return bundle

    entries = extract_entries(bundle)

    # ── Group theo groupIdentifier ──
    groups: dict[str, dict] = {}
    for mr in entries:
        gi = mr.get("groupIdentifier") or {}
        group_id = gi.get("value") or mr.get("id")  # fallback: từng MR riêng nếu không có group

        if group_id not in groups:
            groups[group_id] = {
                "prescription_id":   group_id,
                "prescription_date": (mr.get("authoredOn") or "")[:10],
                "diagnosis":         "",
                "practitioner_ref":  (mr.get("requester") or {}).get("reference", ""),
                "medications":       [],
                "status":            mr.get("status"),
                "has_override":      False,
            }

        # Diagnosis lấy từ reason[0] (R5) hoặc reasonCode[0] (R4 fallback)
        if not groups[group_id]["diagnosis"]:
            reasons = mr.get("reason") or mr.get("reasonCode") or []
            if reasons:
                r0 = reasons[0]
                # R5: reason[].concept.text  |  R4: reasonCode[].text
                concept = r0.get("concept") or r0
                groups[group_id]["diagnosis"] = concept.get("text", "")

        # Drug info
        med_obj  = mr.get("medication") or {}
        concept  = med_obj.get("concept") or med_obj.get("medicationCodeableConcept") or {}
        coding   = (concept.get("coding") or [{}])[0]
        drug_id   = coding.get("code") or ""
        drug_name = concept.get("text") or coding.get("display") or "(không rõ)"

        # Dosage
        di_list  = mr.get("dosageInstruction") or [{}]
        di       = di_list[0] if di_list else {}
        instruction_text = di.get("text") or ""

        # Override note
        notes    = mr.get("note") or []
        override_note = ""
        for n in notes:
            t = n.get("text", "")
            if "Override" in t or "override" in t:
                override_note = t
                groups[group_id]["has_override"] = True
                break

        groups[group_id]["medications"].append({
            "id":           mr.get("id"),
            "drug_id":      drug_id,
            "drug_name":    drug_name,
            "instruction":  instruction_text,
            "status":       mr.get("status"),
            "override_note": override_note or None,
        })

    # Convert dict → sorted list (mới nhất trước)
    prescriptions = list(groups.values())
    prescriptions.sort(key=lambda g: g.get("prescription_date") or "", reverse=True)

    return {
        "patient_id":     pid,
        "count":          len(prescriptions),
        "prescriptions":  prescriptions,
        "summary":        (
            f"BN có {len(prescriptions)} đơn thuốc"
            if prescriptions else
            "BN chưa có đơn thuốc nào."
        ),
    }
