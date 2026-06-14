"""Kiểm tra dị ứng thuốc cho bệnh nhân trước khi kê đơn.

Cơ chế 4 lớp:
  1. Direct name match — BN dị ứng "Amoxicillin" + kê Amoxicillin → CRITICAL
  2. Same class — BN dị ứng "Penicillin" + kê Amoxicillin (penicillin) → CRITICAL
  3. Cross-reactivity — BN dị ứng "Penicillin" + kê Cefuroxime (cephalosporin) → WARNING
  4. Clear — không liên quan → không cảnh báo

Cite:
  - Stockley's Drug Interactions, 13th ed (2022)
  - British National Formulary (BNF) 86
  - WHO Pharmacovigilance guidelines
"""
from __future__ import annotations

TOOL_NAME = "fhir_check_drug_allergy"
CATEGORY  = "Healthcare"
DESCRIPTION = (
    "Kiểm tra dị ứng thuốc cho bệnh nhân trước khi kê đơn. "
    "Đối chiếu thuốc kê với danh sách dị ứng đã ghi nhận, "
    "trả về verdict: 'block' (cấm kê), 'warn' (cảnh báo), 'clear' (an toàn). "
    "GỌI tool này TRƯỚC khi gọi fhir_create_prescription."
)
ARGS_SCHEMA = {
    "patient_id": "string — ID bệnh nhân. BẮT BUỘC.",
    "drug_id":    (
        "string — drug ID trong catalog (VD: 'amoxicillin-500'). "
        "Dùng cái này hoặc drug_name. BẮT BUỘC nếu không có drug_name."
    ),
    "drug_name":  (
        "string — Tên thuốc free text (VD: 'Amoxicillin 500mg'). "
        "Dùng khi không biết drug_id chính xác. Tool sẽ tự match catalog."
    ),
}


def _find_drug(drug_id: str | None, drug_name: str | None) -> dict | None:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
    from _drug_catalog import get_drug, all_drugs

    if drug_id:
        d = get_drug(drug_id)
        if d:
            return d
    if drug_name:
        norm = drug_name.strip().lower()
        for d in all_drugs():
            full = f"{d['name']} {d.get('strength','')}".lower()
            if norm == d["name"].lower() or norm == full or norm in full:
                return d
    return None


def run(args: dict) -> dict:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
    from _drug_catalog import all_drugs
    from _drug_allergy_rules import match_allergy_classes, check_cross_reactivity

    # Import sibling tool
    sys.path.insert(0, os.path.dirname(__file__))
    from fhir_get_allergies import run as fetch_allergies  # type: ignore

    pid = str(args.get("patient_id") or "").strip()
    if not pid:
        return {"error": "patient_id là bắt buộc"}

    drug_id   = str(args.get("drug_id") or "").strip() or None
    drug_name = str(args.get("drug_name") or "").strip() or None

    if not drug_id and not drug_name:
        return {"error": "Cần drug_id hoặc drug_name"}

    drug = _find_drug(drug_id, drug_name)
    if not drug:
        return {
            "verdict":   "warn",
            "drug_id":   drug_id,
            "drug_name": drug_name,
            "checks":    [{
                "severity":       "warning",
                "type":           "unknown_drug",
                "message":        f"Thuốc '{drug_name or drug_id}' không có trong catalog — không tự động check dị ứng được. Hãy verify thủ công.",
                "alternatives":   [],
            }],
            "patient_allergies": [],
        }

    # ── Fetch dị ứng của BN ──
    allergy_result = fetch_allergies({"patient_id": pid, "active_only": True})
    if "error" in allergy_result:
        return allergy_result
    allergies = allergy_result.get("allergies") or []

    if not allergies:
        return {
            "verdict":   "clear",
            "drug_id":   drug["id"],
            "drug_name": f"{drug['name']} {drug['strength']}",
            "drug_class": drug["drug_class"],
            "checks":    [],
            "patient_allergies": [],
            "message":   "BN chưa ghi nhận dị ứng nào. An toàn để kê.",
        }

    # ── Check từng dị ứng ──
    checks: list[dict] = []
    suggested_classes: set[str] = set()
    drug_class = drug["drug_class"]
    drug_name_lower = drug["name"].lower()

    for allergy in allergies:
        # Chỉ check dị ứng thuốc (medication) — food/environment không liên quan
        if allergy.get("category") != "medication":
            continue

        substance = allergy.get("substance") or ""
        substance_lower = substance.lower()

        # ── Layer 1: Direct name match ──
        if substance_lower == drug_name_lower or drug_name_lower in substance_lower:
            checks.append({
                "severity":       "critical",
                "type":           "direct_match",
                "allergy":        substance,
                "allergy_severity": allergy.get("severity"),
                "message":        f"BN đã ghi nhận dị ứng trực tiếp với {substance} — KHÔNG được kê thuốc này.",
                "alternatives":   [],
            })
            continue

        # ── Layer 2 + 3: Match qua alias → class → cross-reactivity ──
        allergy_classes = match_allergy_classes(substance)
        if not allergy_classes:
            # Không match được class nào → cảnh báo nhẹ cho bác sĩ verify
            checks.append({
                "severity":       "warning",
                "type":           "unmatched_allergy",
                "allergy":        substance,
                "message":        f"BN dị ứng '{substance}' — không tự động phân loại được nhóm dược lý. Hãy verify thủ công với thuốc {drug['name']}.",
                "alternatives":   [],
            })
            continue

        for ac in allergy_classes:
            rule = check_cross_reactivity(ac, drug_class)
            if rule:
                checks.append({
                    "severity":       rule["severity"],
                    "type":           "same_class" if ac == drug_class else "cross_reactivity",
                    "allergy":        substance,
                    "allergy_class":  ac,
                    "allergy_severity": allergy.get("severity"),
                    "drug_class":     drug_class,
                    "message":        rule["message"],
                    "alternatives":   rule.get("alternatives", []),
                })
                for alt in rule.get("alternatives", []):
                    suggested_classes.add(alt)

    # ── Tổng hợp verdict ──
    if any(c["severity"] == "critical" for c in checks):
        verdict = "block"
    elif any(c["severity"] == "warning" for c in checks):
        verdict = "warn"
    else:
        verdict = "clear"

    # ── Gợi ý thuốc thay thế ──
    suggested_drugs: list[dict] = []
    if suggested_classes:
        for d in all_drugs():
            if d["drug_class"] in suggested_classes and d["category"] == drug["category"]:
                suggested_drugs.append({
                    "id":         d["id"],
                    "name":       f"{d['name']} {d['strength']}",
                    "drug_class": d["drug_class"],
                })
        suggested_drugs = suggested_drugs[:5]

    return {
        "verdict":        verdict,
        "drug_id":        drug["id"],
        "drug_name":      f"{drug['name']} {drug['strength']}",
        "drug_class":     drug_class,
        "checks":         checks,
        "patient_allergies": [
            {"substance": a["substance"], "severity": a.get("severity_vi") or a.get("severity")}
            for a in allergies if a.get("category") == "medication"
        ],
        "suggested_alternatives": suggested_drugs,
        "_citation":      "Stockley's Drug Interactions 13th ed (2022); BNF 86; WHO Pharmacovigilance",
    }
