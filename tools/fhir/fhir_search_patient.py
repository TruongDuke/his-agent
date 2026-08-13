"""Search for patients in the hospital HIS (via Aidbox FHIR R5)."""

TOOL_NAME = "fhir_search_patient"
CATEGORY = "Healthcare"
DESCRIPTION = (
    "Tìm bệnh nhân trong hệ thống bệnh viện (FHIR R5). "
    "Input là tên (VD: 'Nguyễn Văn A'), số BHYT, hoặc CCCD. "
    "Trả về danh sách bệnh nhân khớp với ID + tên + tuổi + giới + BHYT. "
    "Sau khi có id, các tool khác như fhir_get_patient_history cần id này."
)
ARGS_SCHEMA = {
    "query": "string — tên bệnh nhân (họ hoặc họ+tên), hoặc số BHYT, hoặc số CCCD",
}


def run(args: dict) -> dict:
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from _aidbox_client import fhir_get, extract_entries, patient_summary

    query = str(args.get("query") or "").strip()
    if not query:
        return {"error": "query is required"}

    # Heuristic: digits-only → BHYT or CCCD; else → name
    if query.isdigit() or (len(query) >= 10 and query.replace(" ", "").isdigit()):
        # Try as identifier (BHYT first, then CCCD)
        for system in ["urn:vn:bhyt", "urn:vn:cccd"]:
            bundle = fhir_get("Patient", {"identifier": f"{system}|{query}"})
            entries = extract_entries(bundle)
            if entries:
                return {
                    "matched_by": "identifier",
                    "system": system,
                    "count": len(entries),
                    "patients": [patient_summary(p) for p in entries],
                }
        # Nothing by identifier — fallback to name
        bundle = fhir_get("Patient", {"_content": query})
    else:
        # Search by name — try family name, then given name
        tokens = query.split() #"Phan Hùng" → ["Phan", "Hùng"]
        if len(tokens) == 1: # nếu user chỉ nhập 1 từ, thử tìm family hoặc given
            bundle = fhir_get("Patient", {"family": tokens[0]}) 
            if not extract_entries(bundle): #nếu ko thấy
                bundle = fhir_get("Patient", {"given": tokens[0]}) #
        else:
            # "Nguyễn Văn A" → family=Nguyễn, given=Văn A
            family = tokens[0] #nếu nhập đầy đủ họ tên, family=token đầu, given=token còn lại
            given = " ".join(tokens[1:])
            bundle = fhir_get("Patient", {"family": family, "given": given})
            if not extract_entries(bundle):
                # Retry with just family
                bundle = fhir_get("Patient", {"family": family})

    if isinstance(bundle, dict) and "error" in bundle:
        return bundle

    entries = extract_entries(bundle)
    return {
        "matched_by": "name",
        "count": len(entries),
        "patients": [patient_summary(p) for p in entries],
        "_data_source": "FHIR R5 · Aidbox · Bệnh viện Đa khoa",
    }
