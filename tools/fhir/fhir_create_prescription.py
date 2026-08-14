"""Kê đơn thuốc cho bệnh nhân — tạo nhiều FHIR MedicationRequest cùng lúc.

Mỗi thuốc = 1 MedicationRequest resource, tất cả link cùng patient + practitioner +
shared groupIdentifier (để nhận diện là 1 đơn).

Trước khi gọi tool này, BẮT BUỘC phải gọi fhir_check_drug_allergy cho từng thuốc.
Nếu có verdict='block' mà không có override_reason → tool sẽ từ chối.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
import json
import uuid

TOOL_NAME = "fhir_create_prescription"
CATEGORY  = "Healthcare"
DESCRIPTION = (
    "Tạo đơn thuốc cho bệnh nhân (FHIR MedicationRequest R5). "
    "Một đơn có thể gồm nhiều thuốc. Mỗi thuốc cần: drug_id, dose_per_intake, "
    "frequency_per_day, duration_days, instructions (tùy chọn). "
    "Tool tự động check dị ứng — nếu có 'block' mà không có override_reason sẽ từ chối."
)
ARGS_SCHEMA = {
    "patient_id":     "string — ID bệnh nhân. BẮT BUỘC.",
    "practitioner_id":"string — ID bác sĩ kê đơn. BẮT BUỘC.",
    "diagnosis":      "string — chẩn đoán (free text). VD: 'Viêm họng cấp'. BẮT BUỘC.",
    "medications":    (
        "list[dict] — danh sách thuốc trong đơn. Mỗi dict gồm: "
        "{drug_id: 'amoxicillin-500', dose_per_intake: 1, frequency_per_day: 3, "
        "duration_days: 7, instructions: 'Sau ăn', override_reason: '...'}. "
        "BẮT BUỘC ≥1 thuốc."
    ),
    "notes":          "string — Ghi chú chung cho đơn thuốc. Tùy chọn.",
    "remind":         (
        "boolean (tùy chọn, mặc định true) — bật nhắc giờ uống thuốc qua email cho "
        "bệnh nhân. Chỉ đặt false khi bác sĩ nói rõ là không cần nhắc."
    ),
}


def _safe_int(v, default=None):
    try:
        return int(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _format_dosage_text(med: dict, drug: dict) -> str:
    dose = _safe_int(med.get("dose_per_intake")) or 1
    freq = _safe_int(med.get("frequency_per_day")) or 1
    dur  = _safe_int(med.get("duration_days"))
    unit = drug.get("form", "viên")
    text = f"{dose} {unit} × {freq} lần/ngày"
    if dur:
        text += f" × {dur} ngày"
    inst = (med.get("instructions") or "").strip()
    if inst:
        text += f" ({inst})"
    return text


def _build_medication_request(
    patient_id: str, practitioner_id: str,
    drug: dict, med_args: dict,
    diagnosis: str, group_id: str, authored_on: str,
    override_reason: str | None,
) -> dict:
    dose = _safe_int(med_args.get("dose_per_intake")) or 1
    freq = _safe_int(med_args.get("frequency_per_day")) or 1
    dur  = _safe_int(med_args.get("duration_days"))

    dosage_text = _format_dosage_text(med_args, drug)
    instructions = (med_args.get("instructions") or "").strip()

    dosage_instruction: dict = {
        "text": dosage_text,
        "timing": {
            "repeat": {
                "frequency":  freq,
                "period":     1,
                "periodUnit": "d",
            }
        },
        "doseAndRate": [{
            "doseQuantity": {
                "value": dose,
                "unit":  drug.get("form", "viên"),
            }
        }],
    }
    if dur:
        dosage_instruction["timing"]["repeat"]["boundsDuration"] = {
            "value": dur, "unit": "d",
            "system": "http://unitsofmeasure.org", "code": "d",
        }
    if instructions:
        dosage_instruction["patientInstruction"] = instructions

    mr: dict = {
        "resourceType": "MedicationRequest",
        "status":       "active",
        "intent":       "order",
        "subject":      {"reference": f"Patient/{patient_id}"},
        "requester":    {"reference": f"Practitioner/{practitioner_id}"},
        "authoredOn":   authored_on,
        "medication": {
            "concept": {
                "text": f"{drug['name']} {drug['strength']}",
                "coding": [{
                    "system":  "https://his.local/drug-catalog",
                    "code":    drug["id"],
                    "display": f"{drug['name']} {drug['strength']}",
                }],
            }
        },
        "reason":               [{"concept": {"text": diagnosis}}] if diagnosis else None,
        "dosageInstruction":    [dosage_instruction],
        "groupIdentifier": {
            "system": "https://his.local/prescription-group",
            "value":  group_id,
        },
    }
    if mr["reason"] is None:
        del mr["reason"]

    if override_reason: # ghi vào reason voà note của MedicationRequest để bác sĩ biết lý do override cảnh báo dị ứng
        mr["note"] = [{
            "text": f"⚠ Override cảnh báo dị ứng — lý do: {override_reason}"
        }]

    return mr


def run(args: dict) -> dict:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
    from _aidbox_client import fhir_post, fhir_get, patient_summary
    from _drug_catalog import get_drug

    sys.path.insert(0, os.path.dirname(__file__))
    from fhir_check_drug_allergy import run as check_allergy  # type: ignore

    pid = str(args.get("patient_id") or "").strip()
    if not pid:
        return {"error": "patient_id là bắt buộc"}

    practitioner_id = str(args.get("practitioner_id") or "").strip()
    if not practitioner_id:
        return {"error": "practitioner_id là bắt buộc"}

    diagnosis = str(args.get("diagnosis") or "").strip()
    if not diagnosis:
        return {"error": "diagnosis là bắt buộc"}

    medications = args.get("medications") or []
    # LLM thỉnh thoảng gửi cả danh sách dưới dạng chuỗi JSON thay vì mảng thật. Nhận
    # luôn cho chắc, thay vì bắt nó đoán lại định dạng qua mấy lượt thử-sai.
    if isinstance(medications, str):
        try:
            medications = json.loads(medications)
        except (json.JSONDecodeError, TypeError):
            return {"error": "medications không đọc được — cần mảng thuốc, mỗi thuốc là một object"}
    if isinstance(medications, dict):  # gửi 1 thuốc trần thay vì mảng 1 phần tử
        medications = [medications]
    if not isinstance(medications, list) or not medications:
        return {"error": "medications phải là list ≥1 thuốc"}

    # ── Validate + allergy check từng thuốc ──
    valid_meds: list[tuple[dict, dict]] = []  # (drug, med_args)
    blocked: list[dict] = []
    warnings: list[dict] = []

    for i, med in enumerate(medications):
        drug_id = med.get("drug_id")
        if not drug_id:
            return {"error": f"medications[{i}].drug_id là bắt buộc"}
        drug = get_drug(drug_id)
        if not drug:
            return {"error": f"Thuốc '{drug_id}' không có trong catalog"}

        # Check dị ứng
        chk = check_allergy({"patient_id": pid, "drug_id": drug_id}) #gọi lại check allergy
        if "error" in chk:
            return {"error": f"Allergy check lỗi cho {drug_id}: {chk['error']}"}

        verdict = chk.get("verdict")
        override_reason = (med.get("override_reason") or "").strip()

        if verdict == "block" and not override_reason:
            blocked.append({
                "drug_id":   drug_id,
                "drug_name": chk["drug_name"],
                "checks":    chk.get("checks", []),
                "alternatives": chk.get("suggested_alternatives", []),
            })
            continue

        if verdict == "warn":
            warnings.append({
                "drug_id":   drug_id,
                "drug_name": chk["drug_name"],
                "checks":    chk.get("checks", []),
            })

        valid_meds.append((drug, med))

    # Nếu có thuốc bị block → từ chối toàn đơn
    if blocked:
        return {
            "saved":   False,
            "error":   "prescription_blocked",
            "blocked": blocked,
            "message": (
                f"Đơn bị từ chối: {len(blocked)} thuốc có cảnh báo dị ứng nguy hiểm. "
                "Phải cung cấp 'override_reason' trong từng thuốc bị block, "
                "hoặc đổi sang thuốc thay thế."
            ),
        }

    # ── Tạo group_id chung cho toàn đơn ──
    group_id    = str(uuid.uuid4())
    authored_on = datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%dT%H:%M:%S+07:00")

    # ── POST từng MedicationRequest ──
    created: list[dict] = []
    errors: list[dict]  = []

    for drug, med in valid_meds:
        override_reason = (med.get("override_reason") or "").strip() or None
        mr_body = _build_medication_request(
            patient_id=pid, practitioner_id=practitioner_id,
            drug=drug, med_args=med,
            diagnosis=diagnosis, group_id=group_id, authored_on=authored_on,
            override_reason=override_reason,
        )
        result = fhir_post("MedicationRequest", mr_body)
        if "error" in result:
            errors.append({"drug_id": drug["id"], "error": result["error"]})
            continue
        created.append({
            "id":          result.get("id"),
            "drug_id":     drug["id"],
            "drug_name":   f"{drug['name']} {drug['strength']}",
            "instruction": _format_dosage_text(med, drug),
            "override":    bool(override_reason),
            "override_reason": override_reason,
            # Giữ lại liều/tần suất thô để dựng lịch nhắc bên dưới — chuỗi instruction
            # đã format cho người đọc, không parse ngược ra số được.
            "_freq":       _safe_int(med.get("frequency_per_day"), 1),
            "_dose":       med.get("dose_per_intake") or 1,
            "_duration":   _safe_int(med.get("duration_days"), 0),
            "_instr":      med.get("instructions") or "",
        })

    if errors and not created:
        return {"saved": False, "errors": errors}

    # ── Patient summary ──
    patient = fhir_get(f"Patient/{pid}")
    p_summary = patient_summary(patient) if "error" not in patient else {}

    # ── Lịch nhắc uống thuốc ──
    # Kê đơn qua form UI thì frontend gọi /api/med-reminders/.../from-prescription, còn
    # kê qua agent thì trước đây không ai gọi — cùng một việc mà bệnh nhân lúc được nhắc
    # lúc không, và không ai biết. Dựng luôn ở đây cho hai đường hành xử giống nhau.
    remind = args.get("remind")
    remind = True if remind is None else bool(remind)
    reminder_info = None
    if remind and created:
        email = next((t.get("value") for t in (patient.get("telecom") or [])
                      if t.get("system") == "email"), "")
        if not email:
            reminder_info = {"enabled": False,
                             "reason": "Bệnh nhân chưa có email nên không bật nhắc uống thuốc được."}
        else:
            try:
                import sys as _sys, os as _os
                _root = _os.path.join(_os.path.dirname(__file__), "..", "..")
                if _root not in _sys.path:
                    _sys.path.insert(0, _root)
                from api.reminder_service import merge_from_prescription

                doc = merge_from_prescription(
                    pid,
                    [{"drug_name": c["drug_name"], "dose_per_intake": c["_dose"],
                      "frequency_per_day": c["_freq"], "duration_days": c["_duration"],
                      "instructions": c["_instr"]} for c in created],
                    email=email, patient_name=p_summary.get("name", ""),
                )
                reminder_info = {"enabled": True, "email": email, "added": doc.get("added", 0)}
            except Exception as e:  # noqa: BLE001 — nhắc thuốc hỏng KHÔNG được làm hỏng đơn đã kê
                reminder_info = {"enabled": False, "reason": f"Lỗi tạo lịch nhắc: {e}"}

    for c in created:  # bỏ field nội bộ trước khi trả cho LLM
        for k in ("_freq", "_dose", "_duration", "_instr"):
            c.pop(k, None)

    summary = f"Đã kê {len(created)} thuốc cho chẩn đoán '{diagnosis}'."
    if reminder_info and reminder_info.get("enabled"):
        summary += f" Đã bật nhắc giờ uống thuốc qua email tới {reminder_info['email']}."
    elif reminder_info and reminder_info.get("reason"):
        summary += f" {reminder_info['reason']}"

    return {
        "saved":             True,
        "prescription_id":   group_id,
        "prescription_date": authored_on[:10],
        "patient_id":        pid,
        "patient_name":      p_summary.get("name"),
        "practitioner_id":   practitioner_id,
        "diagnosis":         diagnosis,
        "medications":       created,
        "warnings":          warnings,
        "errors":            errors or None,
        "med_reminders":     reminder_info,
        "summary":           summary,
    }
