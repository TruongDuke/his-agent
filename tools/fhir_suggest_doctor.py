"""Suggest available doctors for a department, ranked by availability.

Helps agent recommend a specific doctor for booking — part of the 5-step flow:
  symptoms → dept → DOCTOR (this tool) → verify patient → book
"""

TOOL_NAME = "fhir_suggest_doctor"
CATEGORY = "Healthcare"
DESCRIPTION = (
    "Gợi ý bác sĩ đang có lịch trống ở 1 khoa, sắp xếp theo số slot free. "
    "Input: department (mã khoa). Trả về list bác sĩ kèm số slot trống 7 ngày tới + "
    "chuyên khoa của họ. Dùng trước fhir_get_available_slots để BN chọn bác sĩ."
)
ARGS_SCHEMA = {
    "department": "string — mã khoa (VD: CARDIO, ENDO, ENT, NEURO, DERMA, ...)",
}


def run(args: dict) -> dict:
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from _aidbox_client import fhir_get, extract_entries

    dept = str(args.get("department") or "").strip().upper()
    if not dept:
        return {"error": "department is required"}

    # Step 1: Find schedules matching dept
    sched_bundle = fhir_get("Schedule", {"service-type": f"urn:vn:department|{dept}"})
    if "error" in sched_bundle:
        return sched_bundle
    schedules = extract_entries(sched_bundle)

    if not schedules:
        return {
            "department": dept,
            "count": 0,
            "doctors": [],
            "message": f"Khoa '{dept}' chưa có bác sĩ nào có lịch khám.",
        }

    # Step 2: For each schedule, get practitioner info + count free slots
    doctors = []
    for sched in schedules:
        sched_id = sched.get("id", "")
        actor_ref = ((sched.get("actor") or [{}])[0] or {}).get("reference", "")
        if not actor_ref.startswith("Practitioner/"):
            continue

        pr = fhir_get(actor_ref)
        if not isinstance(pr, dict) or pr.get("resourceType") != "Practitioner":
            continue

        name = (pr.get("name") or [{}])[0]
        given = " ".join(name.get("given") or [])
        doctor_name = f"BS. {name.get('family','')} {given}".strip()
        specialty = (pr.get("qualification") or [{}])[0].get("code", {}).get("text", "")
        phone = next((t.get("value") for t in (pr.get("telecom") or []) if t.get("system") == "phone"), "")

        # Count free slots in next 7 days
        slots_bundle = fhir_get("Slot", {
            "schedule": f"Schedule/{sched_id}",
            "status": "free",
            "_summary": "count",
        })
        slots_count = slots_bundle.get("total", 0) if isinstance(slots_bundle, dict) else 0

        doctors.append({
            "practitioner_id": pr.get("id"),
            "name": doctor_name,
            "specialty": specialty,
            "phone": phone,
            "available_slots_7days": slots_count,
        })

    # Sort by availability (most free slots first)
    doctors.sort(key=lambda d: d["available_slots_7days"], reverse=True)

    return {
        "department": dept,
        "count": len(doctors),
        "doctors": doctors,
        "message": (
            f"Có {len(doctors)} bác sĩ ở khoa {dept}. "
            f"Bác sĩ có nhiều lịch trống nhất: {doctors[0]['name']} ({doctors[0]['available_slots_7days']} slot)"
            if doctors else f"Không có bác sĩ ở khoa {dept}."
        ),
    }
