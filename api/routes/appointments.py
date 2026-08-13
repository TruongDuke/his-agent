"""Pending appointment routes — list, confirm, reject."""

import os
import httpx
from datetime import date as _date_cls, timedelta
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.deps import _aidbox, _entries, _patient_name, _pract_name

router = APIRouter()


@router.get("/api/pending-appointments")
async def api_pending_appointments(date_from: str = "", date_to: str = "", doctor_id: str = ""):
    url, auth = _aidbox()
    if not url:
        raise HTTPException(503, "AIDBOX_URL not configured")

    d_from = date_from or str(_date_cls.today())
    d_to   = date_to   or str(_date_cls.today() + timedelta(days=7))

    async with httpx.AsyncClient(timeout=20, auth=auth) as client:
        r = await client.get(f"{url}/fhir/Appointment", params=[
            ("status", "proposed"),
            ("date",   f"ge{d_from}T00:00:00"),
            ("_count", "100"),
            ("_sort",  "date"),
        ])
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text[:300])
        entries = r.json().get("entry") or []

        patient_ids = set()
        pract_ids   = set()
        for e in entries:
            appt = e.get("resource", {})
            for p in (appt.get("participant") or []):
                ref = (p.get("actor") or {}).get("reference", "")
                if ref.startswith("Patient/"):
                    patient_ids.add(ref.split("/")[1])
                elif ref.startswith("Practitioner/"):
                    pract_ids.add(ref.split("/")[1])

        p_names: dict = {}
        if patient_ids:
            r2 = await client.get(f"{url}/fhir/Patient",
                                  params={"_id": ",".join(patient_ids), "_count": "100"})
            for p in _entries(r2.json(), "Patient"):
                p_names[p["id"]] = _patient_name(p)

        pr_names: dict = {}
        if pract_ids:
            r3 = await client.get(f"{url}/fhir/Practitioner",
                                  params={"_id": ",".join(pract_ids), "_count": "100"})
            for p in _entries(r3.json(), "Practitioner"):
                pr_names[p["id"]] = _pract_name(p)

        # Lọc theo khoa của bác sĩ đang đăng nhập (nếu truyền doctor_id):
        # lấy mã khoa từ các Schedule của bác sĩ đó, chỉ giữ lịch cùng khoa.
        doctor_depts = None
        if doctor_id:
            rs = await client.get(f"{url}/fhir/Schedule",
                                  params={"actor": f"Practitioner/{doctor_id}", "_count": "50"})
            doctor_depts = set()
            for s in _entries(rs.json(), "Schedule"):
                for st in (s.get("serviceType") or []):
                    c = (((st.get("concept") or {}).get("coding")) or [{}])[0].get("code")
                    if c:
                        doctor_depts.add(c)

    rows = []
    for e in entries:
        appt = e.get("resource", {})
        if (appt.get("start") or "")[:10] > d_to:
            continue
        start        = appt.get("start", "")
        date_vi      = start[8:10] + "/" + start[5:7] + "/" + start[:4] if start else ""
        time_str     = start[11:16] if start else ""
        patient_name = ""
        pract_name   = ""
        patient_id   = None

        for p in (appt.get("participant") or []):
            ref = (p.get("actor") or {}).get("reference", "")
            if ref.startswith("Patient/"):
                patient_id   = ref.split("/")[1]
                patient_name = p_names.get(patient_id, "")
            elif ref.startswith("Practitioner/"):
                pract_name = pr_names.get(ref.split("/")[1], "")

        coding    = (((appt.get("serviceType") or [{}])[0]).get("concept") or {}).get("coding") or [{}]
        dept_code = coding[0].get("code", "")
        dept      = coding[0].get("display", "")
        # Chỉ lọc khi xác định được khoa của bác sĩ; không có schedule → hiện tất (fallback an toàn).
        if doctor_depts and dept_code not in doctor_depts:
            continue

        clinical_note = ""
        patient_email = ""
        for note in (appt.get("note") or []):
            text = note.get("text", "")
            if text.startswith("__patient_email__:"):
                patient_email = text.replace("__patient_email__:", "").strip()
            else:
                clinical_note = text

        reason = ""
        for r_item in (appt.get("reason") or []):
            reason = (r_item.get("concept") or {}).get("text", "")
            break

        rows.append({
            "appointment_id": appt.get("id", ""),
            "patient_name":   patient_name,
            "patient_id":     patient_id,
            "patient_email":  patient_email,
            "department":     dept,
            "practitioner":   pract_name,
            "date":           date_vi,
            "time":           time_str,
            "reason":         reason,
            "symptoms":       clinical_note,
        })

    rows.sort(key=lambda a: a["date"] + a["time"])
    return {"total": len(rows), "pending": rows}


@router.post("/api/confirm-appointment/{appointment_id}")
async def api_confirm_appointment(appointment_id: str):
    from tools.fhir.fhir_confirm_appointment import run as confirm_run
    result = confirm_run({
        "appointment_id": appointment_id,
        "_settings": {
            "gmail_user":         os.getenv("GMAIL_USER", ""),
            "gmail_app_password": os.getenv("GMAIL_APP_PASSWORD", ""),
            "gmail_from_name":    os.getenv("GMAIL_FROM_NAME", "Bệnh viện Đa khoa Hà Nội"),
        }
    })
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.post("/api/reject-appointment/{appointment_id}")
async def api_reject_appointment(appointment_id: str, reason: str = "Bác sĩ từ chối lịch hẹn"):
    from tools.fhir.fhir_reject_appointment import run as reject_run
    result = reject_run({"appointment_id": appointment_id, "reason": reason})
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


class CompleteRequest(BaseModel):
    patient_id:      str
    practitioner_id: str
    diagnosis:       str = ""
    notes:           str = ""
    plan:            str = ""
    # Tùy chọn gửi email tóm tắt
    send_email:      bool = False
    patient_email:   str  = ""
    medications:     list[dict] = []  # [{drug_name, instruction}]


@router.post("/api/complete-appointment/{appointment_id}")
async def api_complete_appointment(appointment_id: str, body: CompleteRequest):
    """Kết thúc khám: appointment → fulfilled + tạo ClinicalImpression."""
    url, auth = _aidbox()
    if not url:
        raise HTTPException(503, "AIDBOX_URL not configured")

    from datetime import datetime as _dt

    async with httpx.AsyncClient(timeout=15, auth=auth) as client:
        # 1. GET appointment rồi set status = fulfilled
        r = await client.get(f"{url}/fhir/Appointment/{appointment_id}")
        if r.status_code >= 400:
            raise HTTPException(404, f"Không tìm thấy lịch hẹn {appointment_id}")
        appt = r.json()
        appt["status"] = "fulfilled"
        r2 = await client.put(f"{url}/fhir/Appointment/{appointment_id}", json=appt) # đóng lịch(fullfiled)
        if r2.status_code >= 400:
            raise HTTPException(r2.status_code, "Không cập nhật được lịch hẹn")

        # 2. Tạo ClinicalImpression
        # FHIR ClinicalImpression không có field "plan" riêng -> lưu kế hoạch trong note[] với tiền tố
        # "__plan__:" để nhận diện lại. Lần khám sau, agent (chat.py, khối __init__) tách kế hoạch này ra
        # và CHỦ ĐỘNG nhắc BN/BS -> vòng khép kín "khám xong ghi kế hoạch -> lần sau tự nhắc".
        note_entries = []
        if body.notes:
            note_entries.append({"text": body.notes})
        if body.plan:
            note_entries.append({"text": f"__plan__:{body.plan}"})

        impression: dict = {
            "resourceType": "ClinicalImpression",
            "status":       "completed",
            "subject":      {"reference": f"Patient/{body.patient_id}"},
            "performer":    {"reference": f"Practitioner/{body.practitioner_id}"},
            "date":         _dt.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "description":  body.diagnosis or "(Không có chẩn đoán)",
        }
        if note_entries:
            impression["note"] = note_entries

        r3 = await client.post(f"{url}/fhir/ClinicalImpression", json=impression)
        if r3.status_code >= 400:
            raise HTTPException(r3.status_code, "Lưu ghi chú lâm sàng thất bại")

        ci_id = r3.json().get("id", "")

        # 3. Gửi email tóm tắt (tùy chọn, non-blocking) ───────────
        email_result = None
        if body.send_email and body.patient_email:
            # Lấy thông tin BN + BS để hiển thị đẹp trong email
            p_resp = await client.get(f"{url}/fhir/Patient/{body.patient_id}")
            patient_name = ""
            if p_resp.status_code < 400:
                p = p_resp.json()
                name = (p.get("name") or [{}])[0]
                given = " ".join(name.get("given") or [])
                patient_name = f"{name.get('family', '')} {given}".strip()

            doctor_name = ""
            if body.practitioner_id:
                d_resp = await client.get(f"{url}/fhir/Practitioner/{body.practitioner_id}")
                if d_resp.status_code < 400:
                    d = d_resp.json()
                    name = (d.get("name") or [{}])[0]
                    given = " ".join(name.get("given") or [])
                    doctor_name = f"BS. {name.get('family', '')} {given}".strip()

            from tools.fhir.fhir_send_visit_summary import run as send_summary
            from datetime import date as _date
            email_result = send_summary({
                "patient_email":     body.patient_email,
                "patient_name":      patient_name or "Bệnh nhân",
                "visit_date":        _date.today().isoformat(),
                "diagnosis":         body.diagnosis,
                "notes":             body.notes,
                "plan":              body.plan,
                "medications":       body.medications or [],
                "practitioner_name": doctor_name,
                "_settings": {
                    "gmail_user":         os.getenv("GMAIL_USER", ""),
                    "gmail_app_password": os.getenv("GMAIL_APP_PASSWORD", ""),
                    "gmail_from_name":    os.getenv("GMAIL_FROM_NAME", "Bệnh viện Đa khoa Hà Nội"),
                },
            })

    return {
        "ok": True,
        "appointment_id": appointment_id,
        "clinical_impression_id": ci_id,
        "email": email_result,
    }


@router.get("/api/patient/{patient_id}/clinical-impressions")
async def api_clinical_impressions(patient_id: str):
    """Lấy lịch sử ghi chú lâm sàng của bệnh nhân."""
    url, auth = _aidbox()
    if not url:
        raise HTTPException(503, "AIDBOX_URL not configured")

    async with httpx.AsyncClient(timeout=15, auth=auth) as client:
        r = await client.get(f"{url}/fhir/ClinicalImpression", params={
            "subject": f"Patient/{patient_id}",
            "_sort":   "-date",
            "_count":  "20",
        })
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text[:200])

    rows = []
    for e in (r.json().get("entry") or []):
        ci = e["resource"]
        notes_raw = ci.get("note") or []
        note_text = ""
        plan_text = ""
        for n in notes_raw:
            t = n.get("text", "")
            if t.startswith("__plan__:"):
                plan_text = t[len("__plan__:"):]
            else:
                note_text = t

        performer_ref = (ci.get("performer") or {}).get("reference", "")
        rows.append({
            "id":          ci.get("id", ""),
            "date":        (ci.get("date") or "")[:10],
            "diagnosis":   ci.get("description", ""),
            "notes":       note_text,
            "plan":        plan_text,
            "practitioner_ref": performer_ref,
        })

    return {"total": len(rows), "impressions": rows}


@router.get("/api/doctor/{doctor_id}/pending-plans")
async def api_doctor_pending_plans(doctor_id: str, days: int = 7):
    """Lấy danh sách kế hoạch chưa theo dõi từ ClinicalImpression (N ngày gần nhất)."""
    from datetime import datetime as _dt, timedelta as _td
    import asyncio as _asyncio

    url, auth = _aidbox()
    if not url:
        raise HTTPException(503, "AIDBOX_URL not configured")

    since = (_dt.utcnow() - _td(days=days)).strftime("%Y-%m-%dT00:00:00Z")

    async with httpx.AsyncClient(timeout=15, auth=auth) as client:
        r = await client.get(f"{url}/fhir/ClinicalImpression", params={
            "performer": f"Practitioner/{doctor_id}",
            "date":      f"ge{since}",
            "_sort":     "-date",
            "_count":    "20",
        })
        if r.status_code >= 400:
            return {"total": 0, "plans": []}

        entries = r.json().get("entry") or []

        # Collect patient IDs
        patient_ids = set()
        ci_list = []
        for e in entries:
            ci = e["resource"]
            has_plan = any(
                n.get("text", "").startswith("__plan__:")
                for n in (ci.get("note") or [])
            )
            if not has_plan:
                continue
            pid = (ci.get("subject") or {}).get("reference", "").split("/")[-1]
            if pid:
                patient_ids.add(pid)
            ci_list.append(ci)

        # Batch-fetch patient names
        p_names: dict[str, str] = {}
        if patient_ids:
            r2 = await client.get(f"{url}/fhir/Patient",
                                  params={"_id": ",".join(patient_ids), "_count": "50"})
            for p in _entries(r2.json(), "Patient"):
                p_names[p["id"]] = _patient_name(p)

    plans = []
    for ci in ci_list:
        pid = (ci.get("subject") or {}).get("reference", "").split("/")[-1]
        plan_text = ""
        for n in (ci.get("note") or []):
            t = n.get("text", "")
            if t.startswith("__plan__:"):
                plan_text = t[len("__plan__:"):]
        plans.append({
            "patient_id":   pid,
            "patient_name": p_names.get(pid, "Bệnh nhân"),
            "date":         (ci.get("date") or "")[:10],
            "diagnosis":    ci.get("description", ""),
            "plan":         plan_text,
        })

    return {"total": len(plans), "plans": plans}


class SuggestRequest(BaseModel):
    patient_id:     str
    appointment_id: str = ""


@router.post("/api/suggest-completion")
async def api_suggest_completion(body: SuggestRequest):
    """AI gợi ý chẩn đoán / ghi chú / kế hoạch dựa trên CBC + lý do khám + ghi chú cũ."""
    import asyncio as _asyncio
    from datetime import datetime as _dt

    url, auth = _aidbox()
    if not url:
        raise HTTPException(503, "AIDBOX_URL not configured")

    pid   = body.patient_id
    appt_id = body.appointment_id

    async with httpx.AsyncClient(timeout=15, auth=auth) as client:
        tasks = [
            # CBC mới nhất
            client.get(f"{url}/fhir/Observation", params={
                "subject": f"Patient/{pid}",
                "code":    "http://loinc.org|58410-2",
                "_sort":   "-date", "_count": "1",
            }),
            # Ghi chú lâm sàng lần trước
            client.get(f"{url}/fhir/ClinicalImpression", params={
                "subject": f"Patient/{pid}",
                "_sort":   "-date", "_count": "1",
            }),
        ]
        if appt_id:
            tasks.append(client.get(f"{url}/fhir/Appointment/{appt_id}"))

        results = await _asyncio.gather(*tasks)

    obs_r, ci_r = results[0], results[1]
    appt_r = results[2] if len(results) > 2 else None

    # ── CBC ──
    cbc_parts = []
    _COMP_MAP = {"777-3": "PLT", "6690-2": "WBC", "4544-3": "HCT", "718-7": "HGB"}
    _UNITS    = {"PLT": "K/μL", "WBC": "K/μL", "HCT": "%", "HGB": "g/dL"}
    cbc_values: dict = {}
    obs_date = ""
    if obs_r.status_code < 400:
        obs_list = _entries(obs_r.json(), "Observation")
        if obs_list:
            latest = obs_list[0]
            obs_date = (latest.get("effectiveDateTime") or "")[:10]
            for comp in latest.get("component") or []:
                c_code = ((comp.get("code") or {}).get("coding") or [{}])[0].get("code", "")
                key = _COMP_MAP.get(c_code)
                if key:
                    val = (comp.get("valueQuantity") or {}).get("value")
                    if val is not None:
                        cbc_values[key] = float(val)
                        cbc_parts.append(f"{key}={val} {_UNITS[key]}")

    # ── Dengue screening ──
    dengue_text = ""
    if "PLT" in cbc_values:
        import sys as _sys
        from pathlib import Path as _Path
        _dengue_dir = str(_Path(__file__).parent.parent.parent / "tools" / "dengue")
        if _dengue_dir not in _sys.path:
            _sys.path.insert(0, _dengue_dir)
        from dengue_cbc_predict import run as _dengue_run  # type: ignore
        dres = _dengue_run({
            "plt": cbc_values.get("PLT"),
            "wbc": cbc_values.get("WBC"),
            "hct": cbc_values.get("HCT"),
            "hgb": cbc_values.get("HGB"),
        })
        dengue_text = f"{dres.get('likelihood_label','')} — {dres.get('next_action','')}"

    # ── Lý do khám ──
    reason = ""
    symptoms = ""
    if appt_r and appt_r.status_code < 400:
        appt = appt_r.json()
        for r_item in (appt.get("reason") or []):
            reason = (r_item.get("concept") or {}).get("text", "")
            break
        for note in (appt.get("note") or []):
            t = note.get("text", "")
            if not t.startswith("__patient_email__:"):
                symptoms = t

    # ── Ghi chú lâm sàng lần trước ──
    prev_note = ""
    if ci_r.status_code < 400:
        ci_list = _entries(ci_r.json(), "ClinicalImpression")
        if ci_list:
            ci = ci_list[0]
            prev_diag = ci.get("description", "")
            prev_plan = ""
            for n in (ci.get("note") or []):
                t = n.get("text", "")
                if t.startswith("__plan__:"):
                    prev_plan = t[len("__plan__:"):]
            prev_date = (ci.get("date") or "")[:10]
            prev_note = f"Lần {prev_date}: {prev_diag}"
            if prev_plan:
                prev_note += f" → Kế hoạch: {prev_plan}"

    # ── Build prompt ──
    context_lines = []
    if reason:
        context_lines.append(f"- Lý do đến khám: {reason}")
    if symptoms:
        context_lines.append(f"- Triệu chứng bệnh nhân khai: {symptoms}")
    if cbc_parts:
        context_lines.append(f"- CBC ngày {obs_date}: {', '.join(cbc_parts)}")
    if dengue_text:
        context_lines.append(f"- Đánh giá sàng lọc: {dengue_text}")
    if prev_note:
        context_lines.append(f"- Ghi chú lần khám trước: {prev_note}")

    if not context_lines:
        raise HTTPException(400, "Không đủ dữ liệu để gợi ý (chưa có CBC hoặc lý do khám)")

    prompt = (
        "Bạn là trợ lý AI hỗ trợ bác sĩ ghi chú lâm sàng tại bệnh viện Việt Nam.\n"
        "Dựa trên thông tin sau, hãy đề xuất ngắn gọn 3 mục để bác sĩ tham khảo:\n\n"
        + "\n".join(context_lines)
        + "\n\nTrả về JSON theo đúng định dạng sau (không giải thích thêm):\n"
        '{"diagnosis": "...", "notes": "...", "plan": "..."}\n\n'
        "Yêu cầu:\n"
        "- diagnosis: 1 câu, chẩn đoán sơ bộ\n"
        "- notes: 1-2 câu, ghi nhận lâm sàng quan trọng\n"
        "- plan: 1-2 câu, kế hoạch theo dõi / tái khám"
    )

    # ── Gọi LLM: ONE-SHOT, KHÔNG dùng agent loop ──
    # Tác vụ bounded (điền sẵn 3 ô: diagnosis/notes/plan) -> gọi 1 lần, ép đầu ra JSON, temperature thấp
    # (0.3) cho ỔN ĐỊNH & ít bịa. Gợi ý grounded trên dữ liệu thật (CBC + dengue + lý do khám + lần trước).
    # Đây chỉ là BẢN NHÁP -> bác sĩ duyệt/sửa rồi mới lưu (human-in-the-loop), AI không tự ghi hồ sơ.
    from agent import _CLIENT, _MODEL  # type: ignore
    import json as _json

    try:
        resp = _CLIENT.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=300,
        )
        raw = resp.choices[0].message.content or ""
        # Trích JSON từ response (có thể có markdown code block)
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        suggestion = _json.loads(raw.strip())
    except Exception as e:
        raise HTTPException(500, f"LLM error: {e}")

    return {
        "diagnosis": suggestion.get("diagnosis", ""),
        "notes":     suggestion.get("notes", ""),
        "plan":      suggestion.get("plan", ""),
        "context":   context_lines,
    }


