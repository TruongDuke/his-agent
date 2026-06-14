"""Get patient vital signs and lab observations from HIS (FHIR R5)."""
from __future__ import annotations


TOOL_NAME = "fhir_get_observations"
CATEGORY = "Healthcare"
DESCRIPTION = (
    "Lấy các chỉ số sức khỏe đo được của bệnh nhân từ HIS (FHIR R5): "
    "huyết áp, cân nặng, đường huyết, nhịp tim, nhiệt độ, v.v. "
    "Trả về chuỗi thời gian để thấy xu hướng tăng/giảm. "
    "Input: patient_id (bắt buộc), category (tuỳ chọn: 'vital-signs' | 'laboratory' | 'all')."
)
ARGS_SCHEMA = {
    "patient_id": "string — ID bệnh nhân (lấy từ fhir_search_patient)",
    "category": "string (tuỳ chọn) — 'vital-signs' | 'laboratory' | 'all'. Mặc định: 'all'",
}

# LOINC codes → tên tiếng Việt
_LOINC_VI = {
    "85353-1": "Sinh hiệu",
    "8480-6":  "Huyết áp tâm thu",
    "8462-4":  "Huyết áp tâm trương",
    "55284-4": "Huyết áp",
    "29463-7": "Cân nặng",
    "8302-2":  "Chiều cao",
    "39156-5": "BMI",
    "8867-4":  "Nhịp tim",
    "9279-1":  "Nhịp thở",
    "8310-5":  "Nhiệt độ cơ thể",
    "59408-5": "SpO2",
    "2339-0":  "Đường huyết",
    "4548-4":  "HbA1c",
    "2093-3":  "Cholesterol toàn phần",
    "2085-9":  "HDL Cholesterol",
    "2089-1":  "LDL Cholesterol",
    "3094-0":  "Ure máu",
    "2160-0":  "Creatinine máu",
}


def run(args: dict) -> dict:
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from _aidbox_client import fhir_get, extract_entries

    pid = str(args.get("patient_id") or "").strip()
    if not pid:
        return {"error": "patient_id is required"}

    category = str(args.get("category") or "all").strip().lower()

    _VITAL_LOINC = {
        "85353-1",                           # Vital signs panel (parent code)
        "85354-9",                           # BP panel (parent code)
        "8480-6", "8462-4", "55284-4",       # BP components
        "29463-7", "8302-2", "39156-5",      # weight, height, BMI
        "8867-4", "9279-1",                  # HR, RR
        "8310-5", "59408-5",                 # temp, SpO2
    }
    _LAB_LOINC = {
        # Sinh hóa / metabolic
        "2339-0","4548-4","2093-3","2085-9","2089-1","3094-0","2160-0",
        # CBC panel + components (LOINC codes used by fhir_create_cbc)
        "58410-2",          # CBC panel
        "777-3",            # PLT
        "6690-2",           # WBC
        "4544-3",           # HCT
        "718-7",            # HGB
        "789-8",            # RBC
        "787-2","785-6","786-4",  # MCV, MCH, MCHC
        "736-9","4650-8",   # Lymphocyte %, Neutrophil %
        "1920-8","1742-6",  # AST, ALT
    }

    # Server-side filter by subject
    params = {"subject": f"Patient/{pid}", "_count": "200", "_sort": "-date"}
    if category in ("vital-signs", "laboratory"):
        params["category"] = category

    bundle = fhir_get("Observation", params)
    if "error" in bundle:
        return bundle

    entries = []
    for e in extract_entries(bundle):
        # Skip records ghi nhầm — nguy hiểm y khoa nếu đưa vào summary
        if e.get("status") == "entered-in-error":
            continue
        # Fallback filter if server category search không hoạt động
        if category != "all":
            loinc = ((e.get("code") or {}).get("coding") or [{}])[0].get("code", "")
            if category == "vital-signs" and loinc not in _VITAL_LOINC:
                continue
            if category == "laboratory" and loinc not in _LAB_LOINC:
                continue
        entries.append(e)
    if not entries:
        return {"patient_id": pid, "count": 0, "observations": [], "summary": "Không có chỉ số nào được ghi nhận."}

    obs_list = []
    for o in entries:
        code_obj = o.get("code") or {}
        coding = (code_obj.get("coding") or [{}])[0]
        loinc = coding.get("code", "")
        name = _LOINC_VI.get(loinc) or coding.get("display") or code_obj.get("text") or loinc

        # Lấy giá trị
        value_str = None
        val_q = o.get("valueQuantity")
        val_str = o.get("valueString")
        val_cc = o.get("valueCodeableConcept")
        components = o.get("component")

        if val_q:
            v = val_q.get("value")
            u = val_q.get("unit", "")
            value_str = f"{v} {u}".strip() if v is not None else None
        elif val_str:
            value_str = val_str
        elif val_cc:
            cc_coding = (val_cc.get("coding") or [{}])[0]
            value_str = val_cc.get("text") or cc_coding.get("display")
        elif components:
            parts = []
            for comp in components:
                c_coding = ((comp.get("code") or {}).get("coding") or [{}])[0]
                c_name = _LOINC_VI.get(c_coding.get("code", "")) or c_coding.get("display", "")
                c_val = comp.get("valueQuantity") or {}
                parts.append(f"{c_name}: {c_val.get('value')} {c_val.get('unit', '')}".strip())
            value_str = " | ".join(parts)

        date = (o.get("effectiveDateTime") or "")[:10]
        obs_list.append({
            "date": date,
            "name": name,
            "value": value_str,
            "unit": (val_q or {}).get("unit") if val_q else None,
            "status": o.get("status"),
        })

    # Sort theo date mới nhất trước (server _sort=-date có thể không đảm bảo)
    obs_list.sort(key=lambda o: o.get("date") or "", reverse=True)

    # Tóm tắt: chỉ số gần nhất của mỗi loại (obs_list đã sort desc → lần đầu gặp = mới nhất)
    latest: dict[str, dict] = {}
    for o in obs_list:
        n = o["name"]
        if n not in latest:
            latest[n] = o

    summary_lines = [f"- {n}: {v['value']} (ngày {v['date']})" for n, v in latest.items() if v.get("value")]

    return {
        "patient_id": pid,
        "count": len(obs_list),
        "observations": obs_list,
        "summary": "Chỉ số gần nhất:\n" + "\n".join(summary_lines) if summary_lines else "Không có dữ liệu.",
    }
