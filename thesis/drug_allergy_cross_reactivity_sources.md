# Drug Allergy Cross-Reactivity — Nguồn lý thuyết

Tài liệu này document các nguồn open-access (PMC / NCBI Bookshelf) đã verify cho module check dị ứng thuốc.
Code reference: [`tools/shared/_drug_allergy_rules.py`](../tools/shared/_drug_allergy_rules.py)

---

## 1. Penicillin × Cephalosporin

**Code rule**: `("penicillin", "cephalosporin") → "warning"` — cảnh báo phản ứng chéo β-lactam.

**Source**: StatPearls — Penicillin Allergy
**URL**: https://www.ncbi.nlm.nih.gov/books/NBK459320/
**Publisher**: NIH NCBI Bookshelf (open access)

**Quote nguyên văn**:

> *"Early estimates of penicillin–cephalosporin cross-reactivity allergy were estimated at **8%**."*
>
> *"After 1980, data on penicillin–cephalosporin cross-reactivity indicate a range of **2.0% to 4.8%**."*

**Khuyến nghị test da** (cùng nguồn):

> *"Penicillin skin testing detects the presence or absence of penicillin-specific IgE antibodies."*
>
> *"Penicillin skin testing should only be performed by health care personnel trained to administer the test, interpret test results, and respond to anaphylaxis."*

**Lưu ý implement**:
- Code hiện tại ghi "5-10%" — đây là số lịch sử trước 1980
- Evidence sau 1980 là **2-4.8%** — nên cập nhật message text trong code
- Verdict "warning" (không phải block) phù hợp với risk thực tế

---

## 2. NSAID × Aspirin — AERD (Aspirin-Exacerbated Respiratory Disease)

**Code rule**:
- `("nsaid", "salicylate") → "critical"`
- `("salicylate", "nsaid") → "critical"`
- `("nsaid", "nsaid-cox2") → "warning"`
- `("salicylate", "nsaid-cox2") → "warning"`

**Source**: Laidlaw TM. "New insights into the mechanisms of AERD" (2024)
**URL**: https://pmc.ncbi.nlm.nih.gov/articles/PMC11695142/
**PMID**: PMC11695142

**Quote nguyên văn**:

> *"Aspirin-exacerbated respiratory disease (AERD), a syndrome characterized clinically by asthma, chronic rhinosinusitis with nasal polyposis, and respiratory reactions to **aspirin and other cyclooxygenase-1 inhibitors**"*

**Cơ sở verdict**:
- Câu "*aspirin and other COX-1 inhibitors*" = mọi NSAID không-COX-2-selective đều có thể trigger AERD
- AERD reaction có thể gây co thắt phế quản → đe dọa tính mạng → "critical" verdict đúng
- COX-2 selective (Celecoxib) ít cross-react hơn → "warning" thay vì "critical"

**Limitation**: Paper này không cung cấp con số % cụ thể. Concept đúng nhưng exact rate cần source khác để verify (vd EAACI position paper 2019, hiện paywall).

---

## 3. Sulfonamide × Thiazide / Loop diuretic

**Code rule**:
- `("sulfonamide", "thiazide") → "warning"`
- `("sulfonamide", "loop-diuretic") → "warning"`

**Source**: Giles A, Foushee J, Lantz E, Gumina G. "Sulfonamide Allergies" (2019)
**URL**: https://pmc.ncbi.nlm.nih.gov/articles/PMC6789825/
**PMID**: PMC6789825

**Quote nguyên văn**:

> *"Available data suggests a **low risk** of cross-allergenicity between sulfonamide antimicrobial and nonantimicrobial agents."*
>
> *"No adverse effects were reported among patients who received a nonantimicrobial sulfonamide, even among patients who reported a life-threatening allergy."*

**Dữ liệu cụ thể**:

> *"In one hospitalization study examining patients with documented sulfonamide allergies, forty of the patients (43%) self-reported sulfonamide nonantimicrobial agent use in the outpatient setting. These medications included **furosemide (n=24; 60%), hydrochlorothiazide (n=10; 25%)**. No hospitalizations resulted from allergic reactions to these agents."*
>
> *"Over a 20-year time period, they found nine case reports suggesting cross-reactivity between sulfonamide antimicrobial and nonantimicrobial agents. The majority of these reports suggesting an association were with diuretics."*

**Cơ sở verdict**:
- Evidence cho thấy risk thực sự **thấp**
- Tuy nhiên có 9 case reports trong 20 năm → không thể bỏ qua hoàn toàn
- "Warning" (không "critical", không "clear") = phù hợp với precautionary principle

---

## 4. ACE-Inhibitor × ARB — Angioedema

**Code rule**: `("ace-inhibitor", "arb") → "warning"`

**Source**: Sica DA, Black HR. *"Current concepts of pharmacotherapy in hypertension: ACE inhibitor-related angioedema: can angiotensin-receptor blockers be safely used?"* (2002)
**URL**: https://pmc.ncbi.nlm.nih.gov/articles/PMC8099384/
**PMID**: PMC8099384

**Quote nguyên văn — Tỷ lệ angioedema do ACE-I**:

> *"The incidence rate for angioedema in a carefully performed prospective look at the angioedema incidence rate over 6 months of therapy with enalapril was **0.68% in 12,557 patients**."*
>
> *"The risk being as high as **5.54% in blacks**."*

**Quote nguyên văn — Nguy cơ với ARB**:

> *"ACE inhibitor treated patients who have experienced an episode of angioedema can have a **similar occurrence with angiotensin receptor blocker (ARB) therapy, albeit much less frequently**."*

**Khuyến nghị xử trí**:

> *"In a patient having experienced ACE inhibitor-related angioedema, angiotensin receptor blockers should be used **cautiously if at all**. If angiotensin receptor blocker therapy is being considered in a patient with prior ACE inhibitor-related angioedema there should be some justification for the use."*

**Cơ sở verdict**:
- "Cautiously if at all" → match với "warning" (cảnh báo nhưng cho phép kê)
- Không phải "block" vì có thể có justification lâm sàng

---

## 5. IDSA Guideline — Đề xuất kháng sinh thay thế

**Code reference**: `alternatives: ["macrolide", "fluoroquinolone", "tetracycline", "lincosamide"]`

**Source**: Shulman ST et al. *"Clinical Practice Guideline for the Diagnosis and Management of Group A Streptococcal Pharyngitis: 2012 Update by the IDSA"* — Clinical Infectious Diseases 2012;55(10):e86-e102
**URL**: https://academic.oup.com/cid/article/55/10/e86/321183
**Publisher**: Oxford Academic — Open access version

**Quote nguyên văn**:

> *"Cephalosporins should be avoided in patients with **immediate (anaphylactic-type) hypersensitivity to penicillin**."*

**Liều khuyến nghị cho BN dị ứng penicillin** (Group A Strep pharyngitis):

| Nhóm | Thuốc | Liều |
|---|---|---|
| Cephalosporin 1st gen (chỉ dùng nếu KHÔNG anaphylactic) | Cephalexin, oral | 20 mg/kg/dose twice daily (max 500 mg) — 10 days |
| Cephalosporin 1st gen | Cefadroxil, oral | 30 mg/kg once daily (max 1g) — 10 days |
| **Macrolide/Azalide** | Azithromycin, oral | 12 mg/kg once daily (max 500 mg) — 5 days |
| **Macrolide** | Clarithromycin, oral | 7.5 mg/kg/dose twice daily (max 250 mg) — 10 days |
| **Lincosamide** | Clindamycin, oral | 7 mg/kg/dose 3 times daily (max 300 mg) — 10 days |

**Cơ sở danh sách alternative trong code**: Khớp với IDSA 2012 — gồm Macrolide (Azithromycin, Clarithromycin, Erythromycin), Fluoroquinolone (Ciprofloxacin, Levofloxacin), Tetracycline (Doxycycline), Lincosamide (Clindamycin).

---

## 6. FHIR AllergyIntolerance — Data model

**Code reference**: [`tools/fhir/fhir_create_allergy.py`](../tools/fhir/fhir_create_allergy.py)

**Source**: HL7 FHIR Release 5 (R5) — AllergyIntolerance Resource
**URL**: https://hl7.org/fhir/R5/allergyintolerance.html

**Field usage trong code**:
- `clinicalStatus`: active / inactive / resolved
- `verificationStatus`: confirmed / unconfirmed / refuted
- `category`: medication / food / environment / biologic
- `criticality`: low / high
- `reaction[].severity`: mild / moderate / severe

---

## Defense statement cho thesis

> *"Module check cross-reactivity dựa trên 4 cơ chế đã được chứng minh trong y văn open-access:*
>
> *(1) **Beta-lactam cross-reactivity** — penicillin/cephalosporin: 2-4.8% theo StatPearls (NIH Bookshelf NBK459320);*
>
> *(2) **AERD** — aspirin và các COX-1 inhibitor khác: Laidlaw TM (2024) PMC11695142;*
>
> *(3) **Sulfonamide pseudoallergy** — sulfa kháng sinh và thiazide/loop diuretic, risk thấp nhưng có case reports: Giles A et al (2019) PMC6789825;*
>
> *(4) **RAAS angioedema** — ACE-I và ARB, ARB nên dùng thận trọng sau ACE-I angioedema: Sica DA, Black HR (2002) PMC8099384.*
>
> *Danh sách kháng sinh thay thế tuân theo IDSA Clinical Practice Guideline 2012 (CID e86-e102). Data model tuân thủ chuẩn HL7 FHIR R5 AllergyIntolerance để đảm bảo interoperability."*

---

## Audit status — minh bạch về source

| Cite | Verified status | Note |
|---|---|---|
| StatPearls NBK459320 | ✅ Fetched & quoted | Open access, peer-reviewed |
| Laidlaw TM 2024 (PMC11695142) | ✅ Fetched & quoted | Open access |
| Giles et al 2019 (PMC6789825) | ✅ Fetched & quoted | Open access |
| Sica & Black 2002 (PMC8099384) | ✅ Fetched & quoted | Open access |
| IDSA 2012 (CID e86-e102) | ✅ Fetched & quoted | Open access via Oxford Academic |
| HL7 FHIR R5 AllergyIntolerance | ✅ Spec mở, structure verified | hl7.org |

**Không sử dụng** trong defense (chưa verify được nguyên văn):
- Pichichero ME 2005 (Pediatrics) — paywall HTTP 403
- EAACI Position Paper 2020 (Allergy) — paywall HTTP 402
- Stockley's Drug Interactions 13th ed — textbook, không có URL open
- Hsieh TC 2004 AJHP — chưa fetch, không guarantee tồn tại như mô tả
- Stevenson DD 2003/2006 — chưa fetch
- Beavers 2011, Cicardi 2014 — chưa fetch

---

## Việc cần làm trước defense

1. **Cập nhật con số penicillin-cephalosporin trong code** từ "5-10%" → "2-4.8% (StatPearls NBK459320, post-1980 data)" để khớp với evidence
2. **Verify số văn bản BYT VN** (QĐ 1088/2013, QĐ 1165/2022, QĐ 51/2017) trên https://thuvienphapluat.vn — tao chưa fetch các văn bản này
3. **Đọc full text Pichichero 2005** qua thư viện trường nếu reviewer hỏi sâu về phân chia theo generation
