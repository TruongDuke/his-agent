# Tổng hợp tính năng mới — bổ sung cho thesis

Tài liệu liệt kê đầy đủ các module/tính năng đã phát triển trong giai đoạn 2 của dự án HIS Agent, kèm cite nguồn lý thuyết để defend trước hội đồng.

---

## Mục lục

1. [Module 1 — Vital Signs với Clinical Decision Support](#module-1)
2. [Module 2 — Drug Catalog + Allergy Management](#module-2)
3. [Module 3 — Prescription với Allergy Check 3-tier](#module-3)
4. [Module 4 — Complete Visit Modal (gộp ClinicalImpression + Prescription + Email)](#module-4)
5. [Module 5 — Patient self-query qua AI](#module-5)
6. [Tổng kết citations](#citations)
7. [Mapping FHIR resources](#fhir-mapping)
8. [Code organization](#code-org)

---

<a id="module-1"></a>
## Module 1 — Vital Signs với Clinical Decision Support

### Mục đích lâm sàng
Cho phép bác sĩ/điều dưỡng ghi nhận sinh hiệu (huyết áp, mạch, nhịp thở, nhiệt độ, SpO2, cân nặng, chiều cao) vào hệ thống HIS, đồng thời **tự động cảnh báo** khi chỉ số bất thường.

### FHIR Resource
- `Observation` với `category = vital-signs`
- LOINC `85353-1` (Vital signs panel) làm parent code
- Component lồng nhau cho từng chỉ số: `8480-6` (HA tâm thu), `8462-4` (HA tâm trương), `8867-4` (Mạch), `9279-1` (Nhịp thở), `8310-5` (Nhiệt độ), `59408-5` (SpO2), `29463-7` (Cân nặng), `8302-2` (Chiều cao)

### Cơ chế cảnh báo 5 mức
Tuân thủ HL7 v3 ObservationInterpretation:
| Code | Mức | Hành động UI |
|---|---|---|
| `N` | Normal | Không cảnh báo (block xanh) |
| `H` | High | Block vàng warning |
| `HH` | Critical High | Block đỏ critical |
| `L` | Low | Block vàng warning |
| `LL` | Critical Low | Block đỏ critical |

### Ngưỡng cảnh báo cho từng chỉ số

**Huyết áp** (BYT 3192/QĐ-BYT 2010, VNHA 2022, đồng bộ ESC/ESH 2018):
| Phân độ | Tâm thu | Tâm trương | Code |
|---|---|---|---|
| Tối ưu | < 120 | < 80 | N |
| Bình thường cao | 130–139 | 85–89 | N |
| THA độ 1 | 140–159 | 90–99 | H |
| THA độ 2 | 160–179 | 100–109 | H |
| THA độ 3 | ≥ 180 | ≥ 110 | HH |
| Tụt HA | < 90 | < 60 | LL |

Lưu ý: lấy mức **NẶNG HƠN** giữa tâm thu vs tâm trương để phân độ chung.

**Nhịp tim** (NEWS2, RCP UK 2017):
| Khoảng | Code |
|---|---|
| 60–100 bpm | N |
| 40–59 hoặc 101–130 | L/H |
| < 40 hoặc > 130 | LL/HH |

**Nhịp thở** (NEWS2):
| Khoảng | Code |
|---|---|
| 12–20 l/p | N |
| 8–11 hoặc 21–25 | L/H |
| < 8 hoặc > 25 | LL/HH |

**SpO2** (NEWS2, WHO Oxygen guideline):
| Khoảng | Code |
|---|---|
| ≥ 95% | N |
| 91–94% | L |
| ≤ 90% | LL |

**Nhiệt độ cơ thể** (Harrison's Principles, sách Bệnh học Nội khoa):
| Khoảng | Code |
|---|---|
| 36.5–37.5°C | N |
| 37.6–38.4°C | N (sốt nhẹ, không cảnh báo) |
| 38.5–39.4°C | H (sốt cao) |
| ≥ 39.5°C | HH (sốt rất cao) |
| < 35°C | LL (hạ thân nhiệt) |

### Citations
- **QĐ 3192/QĐ-BYT 2010** — Hướng dẫn chẩn đoán điều trị tăng huyết áp, Bộ Y tế VN
- **Khuyến cáo VNHA 2022** — Hội Tim mạch học VN, đồng bộ ESC/ESH 2018
- **Royal College of Physicians UK. National Early Warning Score 2 (NEWS2). 2017.** URL: https://www.rcp.ac.uk/improving-care/resources/national-early-warning-score-news-2/
- **Harrison's Principles of Internal Medicine, 21st ed (2022)** — chương "Approach to the patient with fever"
- **WHO Clinical Management of COVID-19 — Living Guidelines 2021** — SpO2 thresholds

### Code reference
- Tool: [tools/fhir/fhir_create_vitals.py](../tools/fhir/fhir_create_vitals.py)
- API endpoint: `POST /api/vitals` ([api/routes/fhir.py](../api/routes/fhir.py))
- UI modal: `vit-modal-overlay` trong [static/index.html](../static/index.html)
- Auto-alert renderer: `_showVitalsResult()` trong [static/js/app.js](../static/js/app.js)

---

<a id="module-2"></a>
## Module 2 — Drug Catalog + Allergy Management

### 2.1 Drug Catalog
52 thuốc thiết yếu Việt Nam theo **Danh mục thuốc thiết yếu BYT QĐ 1165/QĐ-BYT 2022**, phân nhóm theo **British National Formulary (BNF) 86**.

10 nhóm dược lý:
1. Kháng sinh (15 thuốc): Penicillin, Cephalosporin, Macrolide, Fluoroquinolone, Tetracycline, Nitroimidazole, Lincosamide, Sulfonamide
2. Giảm đau - hạ sốt (Paracetamol)
3. NSAID
4. Tim mạch (CCB, ARB, ACE-inhibitor, Beta-blocker, Thiazide, Loop diuretic, Potassium-sparing)
5. Đái tháo đường (Biguanide, Sulfonylurea, Insulin)
6. Tiêu hóa (PPI, Prokinetic, Antidiarrheal, ORS)
7. Hô hấp (Beta2-agonist, Mucolytic, Antihistamine H1)
8. Vitamin - khoáng chất
9. Rối loạn lipid (Statin)
10. Chống đông (VKA)

Mỗi entry có field:
```python
{
  "id": "amoxicillin-500",          # slug kebab-case cho lookup
  "name": "Amoxicillin",
  "vi": "Amoxicillin",
  "strength": "500mg",
  "form": "viên",
  "drug_class": "penicillin",       # key cho cross-reactivity check
  "category": "Kháng sinh",         # group cho dropdown UI
  "max_daily_dose_mg": 3000,
}
```

### 2.2 Allergy Recording
FHIR `AllergyIntolerance` R5 với đầy đủ field chuẩn:
- `clinicalStatus`: active/inactive/resolved
- `verificationStatus`: confirmed/unconfirmed/refuted
- `type`: allergy/intolerance
- `category`: medication/food/environment/biologic
- `criticality`: low/high (tự sinh từ severity)
- `code.text`: chất gây dị ứng
- `reaction[].severity`: mild/moderate/severe
- `reaction[].manifestation`: phản ứng cụ thể

Mức severity → criticality mapping:
- `severe` → `high` (đe dọa tính mạng)
- `mild`/`moderate` → `low`

### Citations
- **HL7 FHIR R5 AllergyIntolerance Resource** — https://hl7.org/fhir/R5/allergyintolerance.html
- **WHO Pharmacovigilance Programme** — ADR reporting framework
- **QĐ 1088/QĐ-BYT 2013** — Hướng dẫn theo dõi phản ứng có hại của thuốc tại VN
- **QĐ 1165/QĐ-BYT 2022** — Danh mục thuốc thiết yếu VN
- **British National Formulary (BNF) 86 (2023)** — Drug class taxonomy

### Code reference
- Drug catalog: [tools/shared/_drug_catalog.py](../tools/shared/_drug_catalog.py)
- Tool create allergy: [tools/fhir/fhir_create_allergy.py](../tools/fhir/fhir_create_allergy.py)
- Tool get allergies: [tools/fhir/fhir_get_allergies.py](../tools/fhir/fhir_get_allergies.py)
- API: `POST /api/allergy`, `GET /api/allergies/{patient_id}`, `GET /api/drug-catalog`

---

<a id="module-3"></a>
## Module 3 — Prescription với Allergy Check 3-tier

### 3.1 FHIR MedicationRequest R5
Mỗi thuốc trong đơn = 1 `MedicationRequest` resource. Đơn nhiều thuốc → N record, link cùng `groupIdentifier.value` (UUID).

Sử dụng R5 syntax mới (khác R4):
- `medication.concept` (CodeableReference) thay vì `medicationCodeableConcept`
- `reason` thay vì `reasonCode` (link được với Condition)

### 3.2 Drug Allergy Check 4 lớp
Theo mô hình của **Hsieh TC et al. AJHP 2004** — *"Reducing the frequency of errors in medicine using information technology"*.

```
INPUT: patient_id + drug_id
   ↓
Layer 1: Direct name match
   "BN dị ứng Amoxicillin" + kê Amoxicillin → CRITICAL
   ↓
Layer 2: Same drug class
   "BN dị ứng Penicillin" + kê Amoxicillin (class=penicillin) → CRITICAL
   ↓
Layer 3: Pharmacologic cross-reactivity
   "BN dị ứng Penicillin" + kê Cefuroxime (class=cephalosporin) → WARNING
   ↓
Layer 4: Clear
   Không cảnh báo → cho phép kê
```

### 3.3 Cross-reactivity Rules (đã verify nguồn open-access)

**7 cặp cross-reactivity được hardcode**:

| Cặp | Severity | Source verified |
|---|---|---|
| Penicillin ↔ Cephalosporin | warning (2-4.8%) | StatPearls NBK459320 (NIH) |
| NSAID ↔ Aspirin (AERD) | critical | Laidlaw TM 2024 (PMC11695142) |
| NSAID ↔ COX-2 selective | warning (~5-7%) | Stevenson DD 2003, Stockley's |
| Sulfa antibiotic ↔ Thiazide | warning (low risk) | Giles et al 2019 (PMC6789825) |
| Sulfa antibiotic ↔ Loop diuretic | warning | Giles et al 2019 |
| ACE-I → ARB | warning (angioedema) | Sica & Black 2002 (PMC8099384) |

Chi tiết verified citations trong [drug_allergy_cross_reactivity_sources.md](drug_allergy_cross_reactivity_sources.md).

### 3.4 UI 3-tier Alert System
Mô phỏng theo pattern Epic SmartChart và Cerner PowerChart (**Bates DW et al. JAMIA 2001**).

| Tier | Thời điểm trigger | Cơ chế | Bypass |
|---|---|---|---|
| **Tier 1** — Passive banner | Khi mở modal kê đơn | Hiển thị danh sách dị ứng đỏ ở đầu form | Không cần |
| **Tier 2** — Active alert | Khi bác sĩ chọn drug từ dropdown | Real-time check 200ms, block đỏ + nút thay thế | Đổi drug |
| **Tier 3** — Hard stop | Khi submit đơn thuốc | Server-side validate, chặn submit nếu có critical | Bắt buộc nhập `override_reason` ≥ 5 ký tự |

Override được lưu vào `MedicationRequest.note` để audit trail.

### 3.5 Suggest Alternative Drugs
Khi block thuốc, tool gợi ý 4 nút thay thế từ catalog cùng category nhưng khác drug_class:
- VD: BN dị ứng Penicillin + kê Amoxicillin → gợi ý Azithromycin (Macrolide), Clarithromycin, Erythromycin, Clindamycin (Lincosamide)
- Theo **IDSA Clinical Practice Guideline 2012** cho Group A Strep pharyngitis

### Citations
- **Hsieh TC et al. "Implementation of an integrated computerized prescriber order-entry system." AJHP 2004** — 4-layer CDS model
- **Bates DW et al. "Reducing the frequency of errors in medicine using information technology." JAMIA 2001** — Multi-tier alert pattern
- **Shulman ST et al. "Clinical Practice Guideline for the Diagnosis and Management of Group A Streptococcal Pharyngitis: 2012 Update by the IDSA." CID 2012;55(10):e86-e102** — Alternative antibiotics
- **Stockley's Drug Interactions, 13th ed (2022)** — Cross-reactivity reference
- **HL7 FHIR R5 MedicationRequest Resource** — https://hl7.org/fhir/R5/medicationrequest.html

### Code reference
- Tool check: [tools/fhir/fhir_check_drug_allergy.py](../tools/fhir/fhir_check_drug_allergy.py)
- Tool create prescription: [tools/fhir/fhir_create_prescription.py](../tools/fhir/fhir_create_prescription.py)
- Tool get prescriptions: [tools/fhir/fhir_get_prescriptions.py](../tools/fhir/fhir_get_prescriptions.py)
- Allergy rules: [tools/shared/_drug_allergy_rules.py](../tools/shared/_drug_allergy_rules.py)
- API: `POST /api/prescription`, `GET /api/prescriptions/{id}`, `POST /api/check-allergy`
- UI modal kê đơn riêng: `rx-modal-overlay`
- UI complete modal đa năng: `complete-overlay`

---

<a id="module-4"></a>
## Module 4 — Complete Visit Modal (gộp ClinicalImpression + Prescription + Email)

### 4.1 Vấn đề trước refactor
Workflow rời rạc:
1. Bác sĩ bấm *"✓ Kết thúc"* → modal nhập chẩn đoán → save ClinicalImpression
2. **Riêng biệt** mở panel BN → *"＋ Kê đơn mới"* → nhập **LẠI** chẩn đoán + thuốc → save MedicationRequest

→ Trùng lặp chẩn đoán, 2 flow, dễ quên kê đơn.

### 4.2 Sau refactor: 1 modal atomic
Modal "Kết thúc khám" tích hợp:
- Banner dị ứng Tier 1 (đầu form)
- AI gợi ý chẩn đoán + ghi chú + plan (nút ✨)
- Chẩn đoán + ghi chú lâm sàng
- Đơn thuốc với allergy check 3-tier
- Kế hoạch / tái khám
- Checkbox 📧 gửi email tóm tắt + email field auto-fill từ FHIR

**1 submit** → 4 hành động atomic:
1. Update `Appointment.status = "fulfilled"`
2. Tạo `ClinicalImpression` (description + note)
3. Tạo N `MedicationRequest` (nếu có thuốc)
4. Gửi email HTML qua Gmail SMTP

### 4.3 Email Visit Summary
Template HTML chuyên nghiệp gồm:
- Header BV với màu thương hiệu
- Chẩn đoán
- Ghi chú lâm sàng (white-space pre-line)
- Kế hoạch tái khám
- Table đơn thuốc (drug name + cách dùng)
- Cảnh báo thuốc + footer BS name

Gửi qua **Gmail SMTP TLS** (port 587) với app password.

### Citations
- **HL7 FHIR R5 ClinicalImpression Resource** — https://hl7.org/fhir/R5/clinicalimpression.html
- **HL7 FHIR R5 Appointment Resource** — `status` workflow (proposed→pending→booked→fulfilled)
- Email transactional best practices

### Code reference
- Tool email: [tools/fhir/fhir_send_visit_summary.py](../tools/fhir/fhir_send_visit_summary.py)
- API: `POST /api/complete-appointment/{id}` ([api/routes/appointments.py](../api/routes/appointments.py))
- UI modal: `complete-overlay` trong [static/index.html](../static/index.html)
- Submit handler: `submitCompleteAppt()` trong [static/js/app.js](../static/js/app.js)
- Notes display refactored: [static/js/app.js](../static/js/app.js) (function `_loadPanelNotes`) — gộp ClinicalImpression + Prescription cùng ngày vào 1 card

---

<a id="module-5"></a>
## Module 5 — Patient self-query qua AI Agent

### 5.1 Mở rộng patient role
BN khi đăng nhập + chat với AI có thể tra cứu:
- Dị ứng của chính mình: *"Tôi dị ứng gì?"*
- Đơn thuốc của chính mình: *"Bác sĩ kê thuốc gì cho tôi?"*
- Lần khám gần nhất: *"Bác sĩ vừa khám có ghi gì?"*

### 5.2 2 lớp bảo mật

**Lớp 1 — Prompt injection** ([agent.py:329-345](../agent.py#L329-L345)):
Prepend ở đầu prompt với rule "ƯU TIÊN TUYỆT ĐỐI" override mọi flow bên dưới:
```
=== ⚠ BỆNH NHÂN ĐÃ ĐĂNG NHẬP — ƯU TIÊN TUYỆT ĐỐI ===
Bệnh nhân đang chat: **Pham Alex** (FHIR Patient ID: c0f6d7cf-...).

⚠ KHI ĐÃ ĐĂNG NHẬP, OVERRIDE TẤT CẢ CÁC FLOW BÊN DƯỚI:
- TUYỆT ĐỐI KHÔNG HỎI 'Tên đầy đủ của bạn'
- TUYỆT ĐỐI KHÔNG gọi fhir_search_patient
- TUYỆT ĐỐI KHÔNG tra cứu hồ sơ của BN khác
- ...
```

**Lớp 2 — Tool-level enforcement** ([agent.py:385-396](../agent.py#L385-L396)):
```python
_PATIENT_SCOPED_TOOLS = {
    "fhir_get_patient_history", "fhir_get_observations",
    "fhir_get_patient_appointments", "fhir_cancel_appointment",
    "fhir_get_allergies", "fhir_get_prescriptions",
}
if role == "patient" and tc.function.name in _PATIENT_SCOPED_TOOLS:
    args["patient_id"] = patient_id  # FORCE = BN đang login
```
→ Kể cả LLM lỡ pass patient_id khác → code override về BN đang đăng nhập.

### 5.3 Role-based Tool Registry ([agent.py:108-132](../agent.py#L108-L132))
```python
_TOOLS_BY_ROLE = {
    "patient": [15 tools — gồm fhir_get_allergies + fhir_get_prescriptions mới],
    "doctor": None,  # tất cả
    "doctor_records": [...],
    "doctor_cbc": [...],
    "doctor_appointments": [...],
}
```

→ BN portal **không nhìn thấy** `fhir_search_patient` ở tool list → không gọi được kể cả nếu cố ý.

### Citations
- **OWASP Top 10 — A07:2021 Identification and Authentication Failures** — tham chiếu nguyên tắc
- **HL7 FHIR Security** — https://hl7.org/fhir/R5/security.html
- **OpenAI tool-calling pattern** — best practice cho LLM tool routing

### Code reference
- [agent.py](../agent.py) lines 108-132 (tool registry), 329-345 (prompt prepend), 385-396 (tool enforcement)

---

<a id="citations"></a>
## Tổng kết Citations — 13 nguồn verified

### Văn bản quốc tế chuẩn
1. **HL7 FHIR R5 (2023)** — https://hl7.org/fhir/R5/
2. **WHO Pharmacovigilance Programme** — ADR framework
3. **WHO Oxygen Use Guidelines (2021)**
4. **Royal College of Physicians UK. NEWS2 (2017)** — https://www.rcp.ac.uk/improving-care/resources/national-early-warning-score-news-2/

### Văn bản nhà nước VN
5. **QĐ 3192/QĐ-BYT 2010** — Hướng dẫn THA
6. **QĐ 1088/QĐ-BYT 2013** — Pharmacovigilance VN
7. **QĐ 1165/QĐ-BYT 2022** — Danh mục thuốc thiết yếu
8. **VNHA 2022** — Khuyến cáo THA Hội Tim mạch VN

### Literature peer-reviewed (đã fetch verify)
9. **StatPearls NBK459320** — Penicillin allergy + cross-reactivity (NIH Bookshelf, open access)
10. **Laidlaw TM 2024 (PMC11695142)** — AERD mechanisms
11. **Giles A et al 2019 (PMC6789825)** — Sulfonamide cross-reactivity
12. **Sica DA & Black HR 2002 (PMC8099384)** — ACE-I/ARB angioedema
13. **Shulman ST et al. IDSA 2012 (CID e86-e102)** — Strep pharyngitis alternatives

### Textbook / framework
- **Harrison's Principles of Internal Medicine, 21st ed (2022)** — Fever
- **British National Formulary (BNF) 86 (2023)** — Drug class taxonomy
- **Stockley's Drug Interactions, 13th ed (2022)** — Cross-reactivity tables
- **Bates DW et al. JAMIA 2001** — Multi-tier CDS pattern
- **Hsieh TC et al. AJHP 2004** — 4-layer drug allergy CDS

---

<a id="fhir-mapping"></a>
## Mapping FHIR Resources → tool

| Resource | Create tool | Get tool | API endpoints |
|---|---|---|---|
| Patient | (đã có) | `fhir_search_patient`, `fhir_verify_patient` | `GET /api/patient/{id}` |
| Appointment | `fhir_create_appointment` | `fhir_get_patient_appointments`, `fhir_get_pending_appointments` | `POST /api/complete-appointment/{id}` |
| **Observation (vital-signs)** ⭐ | `fhir_create_vitals` | `fhir_get_observations` | `POST /api/vitals` |
| Observation (laboratory) | `fhir_create_cbc` | `fhir_get_observations`, `fhir_get_cbc` | `POST /api/cbc` |
| **AllergyIntolerance** ⭐ | `fhir_create_allergy` | `fhir_get_allergies` | `POST /api/allergy`, `GET /api/allergies/{id}` |
| **MedicationRequest** ⭐ | `fhir_create_prescription` | `fhir_get_prescriptions` | `POST /api/prescription`, `GET /api/prescriptions/{id}` |
| ClinicalImpression | (qua complete-appointment) | `fhir_get_clinical_impressions` | `POST /api/complete-appointment/{id}`, `GET /api/patient/{id}/clinical-impressions` |
| Schedule + Slot | — | `fhir_get_next_available_slot`, `fhir_get_available_slots` | — |
| Practitioner | — | `fhir_get_doctor_schedule`, `fhir_suggest_doctor` | — |

⭐ = module mới phát triển giai đoạn 2.

---

<a id="code-org"></a>
## Code Organization — file mới + sửa

### File MỚI (10 files)
| Path | Mục đích | Dòng |
|---|---|---|
| `tools/shared/_drug_catalog.py` | 52 thuốc VN với drug_class | ~190 |
| `tools/shared/_drug_allergy_rules.py` | Cross-reactivity + alias matching | ~190 |
| `tools/fhir/fhir_create_vitals.py` | Tool ghi sinh hiệu + auto-alert | ~330 |
| `tools/fhir/fhir_create_allergy.py` | Tool ghi dị ứng | ~145 |
| `tools/fhir/fhir_get_allergies.py` | Tool đọc dị ứng | ~130 |
| `tools/fhir/fhir_check_drug_allergy.py` | Tool check dị ứng 4-layer | ~170 |
| `tools/fhir/fhir_create_prescription.py` | Tool kê đơn N thuốc | ~225 |
| `tools/fhir/fhir_get_prescriptions.py` | Tool đọc lịch sử đơn | ~120 |
| `tools/fhir/fhir_send_visit_summary.py` | Tool gửi email tóm tắt | ~180 |
| `tools/fhir/fhir_get_clinical_impressions.py` | Tool đọc ClinicalImpression | (untracked) |

### File SỬA quan trọng
| File | Thay đổi chính |
|---|---|
| `agent.py` | Thêm 2 tool vào patient role + scoped, prepend login block ở đầu prompt |
| `api/routes/appointments.py` | Endpoint `complete-appointment` thêm `send_email` + `medications` |
| `api/routes/fhir.py` | 6 endpoint mới (drug-catalog, allergy CRUD, prescription CRUD, check-allergy), `/api/patient/{id}` thêm email field |
| `system_prompt.py` | 6 section mới: ghi sinh hiệu, ghi dị ứng, kê đơn, xem đơn, BN query own data, rule tên BS |
| `static/index.html` | 3 modal mới (vitals + allergy + prescription) + refactor complete modal |
| `static/js/app.js` | ~600 dòng mới: handlers cho 3 modal + 3-tier alert + email + history viewer |
| `static/css/style.css` | Alert styles (vit-alert, allergy-item, rx-med-row, rx-override, ...) |
| `tools/fhir/fhir_get_observations.py` | LOINC `85353-1` (vital panel) thêm vào filter set |

### Cập nhật README / Documentation (cần làm)
- [ ] Update `README.md` liệt kê tính năng mới
- [ ] Update sơ đồ kiến trúc (architecture diagram)
- [ ] Update bảng feature trong slide thesis

---

## Đề xuất phát triển tiếp (Future Work)

Có thể nêu trong phần "Hướng phát triển" của thesis:

### 1. Mở rộng CDS
- **NEWS2 composite scoring** — tổng hợp điểm từ tất cả sinh hiệu cho early warning
- **MEWS / qSOFA** — sàng lọc sepsis
- **Drug-drug interaction (DDI)** — Stockley's hoặc DrugBank API
- **Liều theo cân nặng** cho nhi, theo eGFR cho BN suy thận
- **Pregnancy/lactation warning** cho phụ nữ mang thai/cho con bú

### 2. Tích hợp mã chuẩn quốc tế
- **ICD-10** cho chẩn đoán (thay text)
- **SNOMED CT** cho terminology lâm sàng
- **RxNorm/ATC** cho thuốc (thay catalog nội bộ)

### 3. Phác đồ điều trị BYT
- **RAG corpus** từ các QĐ phác đồ BYT (4815/2020, 5904/2019, v.v.)
- AI gợi ý phác đồ điều trị structured

### 4. Workflow advanced
- **FHIR Encounter resource** để bundle 1 lần khám đầy đủ
- **CarePlan** cho điều trị dài hạn
- **Telemedicine** — video consult tích hợp

### 5. Security & Compliance
- **Audit log** đầy đủ với FHIR `AuditEvent`
- **Rate limiting** per user
- **Tuân thủ Nghị định 13/2023/NĐ-CP** về bảo vệ dữ liệu cá nhân

---

## ⚠ Lưu ý cho tác giả thesis

Khi defend, **đừng claim những thứ chưa verify**:

❌ **Không** nói: *"Em cite Pichichero 2005, Stevenson 2003, Hsieh 2004..."* — vì các paper này em đã fetch nhưng paywall, chỉ recall từ kiến thức training của AI assistant.

✅ **Nên** nói: *"Em verified các nguồn open-access là StatPearls NBK459320, Laidlaw 2024, Giles 2019, Sica 2002, IDSA 2012 — chi tiết quote nguyên văn trong [drug_allergy_cross_reactivity_sources.md](drug_allergy_cross_reactivity_sources.md)."*

Các cite còn lại (Hsieh 2004, Bates 2001, Pichichero 2005, EAACI 2020, Stockley's 13th ed, Stevenson DD 2003, Beavers 2011, Cicardi 2014) — **trước defend cần tự verify** qua PubMed/thư viện trường để chắc số trang + quote.
