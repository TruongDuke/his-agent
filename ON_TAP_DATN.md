# ÔN TẬP BẢO VỆ ĐATN — HIS Agent

> Trợ lý AI cho Hệ thống Thông tin Bệnh viện. Tài liệu ôn nhanh trước buổi phản biện.

---

## 1. SƠ ĐỒ DUY NHẤT — nhớ cái này là nhớ cả hệ thống

```
┌─────────────────────────────────────────────────────────────┐
│  NGƯỜI DÙNG gõ tin nhắn trên web (static/)                   │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
   [1] chat.py  ── PHỤC VỤ: nhận tin, KHÔNG tự nghĩ
                           ▼
   [2] agent.py ── ĐẦU BẾP: điều phối (KHÔNG chứa trí thông minh)
                           │
        ┌──────────────────┴───────────────────┐
        ▼                                       ▼
   [3] LLM bên ngoài                    [4] TOOLS (code Python)
   (Claude/Qwen) = TRÍ THÔNG MINH        = DỮ LIỆU THẬT
   "dùng tool nào?"                       fhir_*    → bệnh viện (FHIR)
        │                                 dengue_*  → sàng lọc SXHD
        │                                 outbreak_*→ số ca HCDC
        └───────────► VÒNG LẶP ◄──────────┘   knowledge → tra thuốc NCBI
         hỏi LLM → LLM đòi tool → chạy tool →
         đưa kết quả lại → hỏi tiếp → ... → LLM trả lời xong
                           ▼
   [5] chat.py bê câu trả lời về web (hiện dần từng chữ — SSE)
```

**Hành trình 1 câu hỏi "tìm bệnh nhân Nguyễn Văn A":**
1. chat.py nhận → đưa agent.py
2. agent.py hỏi LLM
3. LLM: "dùng tool fhir_search_patient, query='Nguyễn Văn A'"
4. agent.py chạy run() của tool đó
5. run() gọi fhir_get() → hỏi bệnh viện thật (Aidbox)
6. bệnh viện trả danh sách BN khớp
7. agent.py đưa kết quả lại cho LLM
8. LLM viết câu trả lời đẹp
9. chat.py bê về web ✅

---

## 2. SÁU Ý CỐT LÕI

| # | Ý | Câu nói chuẩn cho hội đồng |
|---|---|---|
| 1 | chat.py = tầng API | "Nhận request từ giao diện, chuyển cho agent, không tự sinh câu trả lời." |
| 2 | Trí thông minh ở LLM, không ở agent.py | "agent.py chỉ điều phối; trí thông minh ở LLM bên ngoài, nên cần API_KEY." |
| 3 | Vòng lặp agent | "Hỏi LLM → LLM đòi tool → chạy tool → đưa kết quả lại → lặp tới khi LLM trả lời xong." |
| 4 | Tool = hàm Python 4 phần | "TOOL_NAME, DESCRIPTION (cho LLM đọc), ARGS_SCHEMA, và **run()** trả về dữ liệu thật." |
| 5 | LLM không bịa số liệu | "LLM chọn tool và diễn giải; dữ liệu từ run() — FHIR, HCDC, NCBI — đều thật và dẫn nguồn." |
| 6 | Sàng lọc y khoa = rule-based, dẫn nguồn | "Dị ứng/SXHD dùng luật theo QĐ 2760/Stockley's — giải thích được, quan trọng hơn 'hộp đen'." |

---

## 3. CÁC NHÓM TOOL (đầy đủ)

### 3.1 `fhir_*` — kết nối hệ thống bệnh viện
- Dữ liệu thật, theo chuẩn quốc tế **FHIR R5**, lưu trên máy chủ **Aidbox**.
- Đường dây nối tới bệnh viện: `tools/shared/_aidbox_client.py` (hàm `fhir_get`, `fhir_post`).
- Ví dụ: `fhir_search_patient`, `fhir_get_patient_history`, `fhir_create_appointment`,
  `fhir_create_prescription`, `fhir_send_visit_summary` (gửi email tóm tắt)...
- **Điểm cộng:** FHIR là chuẩn quốc tế (của HL7) → tích hợp được với HIS bệnh viện thật.

### 3.2 `fhir_check_drug_allergy` — chặn kê đơn gây dị ứng (4 lớp)
| Lớp | Tình huống | Ví dụ | Kết quả |
|---|---|---|---|
| 1. Trùng tên thẳng | dị ứng đúng thuốc đó | dị ứng "Amoxicillin", kê Amoxicillin | 🔴 block |
| 2. Cùng nhóm | khác tên, cùng họ dược lý | dị ứng "Penicillin", kê Amoxicillin | 🔴 block |
| 3. Phản ứng chéo | hai nhóm "bà con" | dị ứng "Penicillin", kê **Cefuroxime** (Cephalosporin) | 🟡 warn |
| 4. Không liên quan | hoàn toàn khác | dị ứng "Penicillin", kê Paracetamol | 🟢 clear |
- Bộ luật y khoa tách riêng: `tools/shared/_drug_allergy_rules.py`
  (bảng đổi tên→nhóm `ALLERGY_ALIASES`, bảng phản ứng chéo `CROSS_REACTIVITY`).
- Dẫn nguồn: **Stockley's Drug Interactions 13th, BNF 86, QĐ 1088/QĐ-BYT**.
- "Ca cefuroxime" (lớp 3) = ví dụ demo đắt giá nhất.

### 3.3 `dengue_symptom_assessment` — sàng lọc SXHD từ TRIỆU CHỨNG (bệnh nhân)
- Đầu vào: vùng dịch, số ngày sốt, triệu chứng cơ bản, dấu hiệu cảnh báo, dấu hiệu nặng.
- Đầu ra: mức độ none / mild / warning / severe + lời khuyên.
- Logic = chuỗi "cửa ải" theo mức nguy hiểm giảm dần; **dấu hiệu nặng/cảnh báo xét TRƯỚC**
  cả điều kiện vùng dịch (ưu tiên an toàn).
- Phác đồ tách ra file JSON riêng (`knowledge_base/dengue_protocol.json`) → sửa nội dung không cần đụng code.
- Lọc `& _VALID_SYMPTOMS` để bỏ tham số LLM bịa.

### 3.4 `dengue_cbc_predict` — sàng lọc SXHD từ XÉT NGHIỆM MÁU (bác sĩ)
- Đầu vào: PLT (tiểu cầu), WBC (bạch cầu), HCT, men gan AST/ALT...
- Chấm điểm theo ngưỡng **QĐ 2760/QĐ-BYT 2023 + WHO 2009**, mỗi ngưỡng dẫn nguồn trang.
- Là tool **sàng lọc (screening)**, KHÔNG chẩn đoán xác định (chẩn đoán phải qua NS1/IgM).

### 3.5 `outbreak_get_stats` — số ca SXHD THẬT từ HCDC TP.HCM
- Minh chứng cho "knowledge base **động**" — dữ liệu cập nhật thời gian thực, không bị "đóng băng".
- **Cào (scrape)** bản tin tuần từ web HCDC (`tools/outbreak/_hcdc_scraper.py`).
- Cơ chế **lazy + cache** (SQLite `data/outbreak_cache.db`): tuần đã có → dùng lại, khỏi vào mạng.
- Tra được **tuần cụ thể** (search) hoặc **tuần mới nhất** (category page); có **so sánh tuần-trên-tuần**.
- Luôn trả `source_url` để dẫn nguồn.
- **Demo offline:** bật biến môi trường `HCDC_MOCK=1` → dùng số liệu mẫu, không cần mạng.
  ⭐ **NHỚ BẬT khi demo trước hội đồng để tránh rủi ro wifi/web HCDC sập.**
- Phạm vi hẹp: chỉ TP.HCM, chỉ SXHD, theo tuần (không có tử vong/chia quận/cả nước).
- Hạn chế: cào web phụ thuộc cấu trúc trang HCDC → họ đổi giao diện thì phải cập nhật bộ cào.

### 3.6 `drug_info` — tra thông tin thuốc từ NCBI (RAG qua API)
- Kiểu **RAG thứ 2** (kiểu 1 là vector gợi ý khoa): lấy tài liệu thật rồi mới để LLM trả lời.
- Gọi API NCBI E-utilities: **StatPearls** (chuyên luận) + **PubMed** (abstract bài báo thật).
- Trả về `sources` (link, đánh số [1][2][3]) + `evidence_en` (nội dung thật) + `note_for_llm` (lệnh grounding).
- **Cơ chế chống bịa (grounding):** `note_for_llm` bắt LLM **chỉ dùng nội dung evidence**, KHÔNG
  tự bịa số liều bằng kiến thức nền; phải chèn đúng số trích dẫn [n] → ra chip nguồn bấm được.
- Hạn chế: nguồn **tiếng Anh** (NCBI), **chưa theo Dược thư Quốc gia Việt Nam** (hướng phát triển).
- KHÁC `fhir_check_drug_allergy`: drug_info = tra **kiến thức**; allergy = **kiểm tra dị ứng** khi kê đơn.

### 3.7 RAG gợi ý khoa khám (`tools/shared/_rag_departments.py`)
- Kiểu **RAG thứ 1: vector**. Dùng `sentence-transformers` (paraphrase-multilingual-MiniLM-L12-v2).
- Biến triệu chứng & mô tả khoa thành vector → tính **cosine similarity** → cộng điểm (weighted voting) → top khoa.
- Vì sao không để LLM tự gợi ý? → RAG ổn định, dựa trên danh mục khoa thật, tránh LLM bịa khoa.

---

## 4. BẢO MẬT / PHÂN QUYỀN

- Tool theo vai trò: `_TOOLS_BY_ROLE` trong `agent.py` (patient / doctor / doctor_records / ...).
- **2 lớp chặn bệnh nhân xem hồ sơ người khác:**
  1. **Lớp prompt** (nhắc): `login_block` ở đầu system prompt — `agent.py:336`.
  2. **Lớp code (chắc chắn):** ép `patient_id` của người đăng nhập vào mọi tool — `agent.py:412`:
     ```python
     args["patient_id"] = patient_id   # ghi đè cứng, LLM bị dụ cũng không lách được
     ```
- Mật khẩu: hash bằng **bcrypt** (`db.py`), đăng nhập bằng SĐT.

---

## 5. BA BẪY PHẢN BIỆN — PHẢI NHỚ

1. **Model ML (`dengue_cbc_model_core.joblib`) KHÔNG được dùng** — hệ thống chạy rule-based.
   → Kể: *"Em có train model ML (Random Forest ~1500 mẫu) để tham khảo, nhưng chọn rule-based
   theo QĐ 2760 vì **giải thích được** — quan trọng hơn 'hộp đen' trong y tế."*
   ⚠ ĐỪNG nói cụt "em dùng Machine Learning" → mở code thấy if-else là mâu thuẫn.

2. **"Đọc ảnh CBC" là OCR** (`agent.py:264`, model qwen-vl-ocr) — đọc số từ ảnh rồi đưa vào tool
   rule-based. KHÔNG phải AI chẩn đoán qua ảnh.

3. **Các tool sàng lọc chỉ là screening**, không thay chẩn đoán xác định (NS1/IgM/IgG/PCR).

---

## 6. CHÍN CÂU HỎI ÔN + ĐÁP ÁN CHUẨN

**1. chat.py có tự nghĩ ra câu trả lời không? Ai nghĩ?**
Không. chat.py chỉ nhận và chuyển tin nhắn. LLM mới sinh câu trả lời.

**2. Một tool gồm mấy phần? Kể tên.**
4 phần: `TOOL_NAME`, `DESCRIPTION`, `ARGS_SCHEMA`, và **`run()`** (hàm chạy, trả dữ liệu — quan trọng nhất).

**3. Trí thông minh nằm ở đâu? Vì sao cần API_KEY?**
Ở LLM bên ngoài (Claude/Qwen). agent.py chỉ điều phối. Cần API_KEY để gọi tới LLM đó.

**4. Mô tả vòng lặp agent. Khi nào dừng?**
Hỏi LLM → LLM đòi tool → chạy tool → đưa kết quả lại → lặp. Dừng khi LLM không đòi tool nữa mà viết câu trả lời cuối.

**5. FHIR là gì? Vì sao là điểm cộng?**
Chuẩn quốc tế (của HL7) để lưu/trao đổi dữ liệu y tế. Điểm cộng: tích hợp được với HIS bệnh viện thật, không phải định dạng tự chế.

**6. Làm sao đảm bảo LLM không bịa số liệu y khoa?**
Không để LLM tự sinh số liệu — nó phải GỌI TOOL lấy dữ liệu thật (FHIR/HCDC/NCBI). Với kiến thức thuốc còn có "grounding": đưa tài liệu thật + cấm bịa thêm + bắt trích nguồn [n]. Mọi câu dẫn nguồn kiểm chứng được.

**7. Cơ chế kiểm tra dị ứng 4 lớp? Ví dụ.**
(1) trùng tên thẳng → block; (2) cùng nhóm dược lý → block; (3) phản ứng chéo (penicillin↔cefuroxime) → warn; (4) không liên quan → clear. Dựa bảng phản ứng chéo Stockley's/BNF.

**8. Em dùng thuật toán gì để sàng lọc sốt xuất huyết? (BẪY ML)**
Rule-based theo QĐ 2760/BYT — vì giải thích được. Có train model ML để tham khảo nhưng hệ thống thật chọn rule-based (xem bẫy #1).

**9. Bệnh nhân A có xem được hồ sơ bệnh nhân B không? Vì sao?**
Không. Chặn ở 2 tầng: prompt nhắc, và quan trọng hơn là **code ép `patient_id`** của người đăng nhập vào mọi truy vấn (`agent.py:412`) — LLM bị dụ cũng không lấy được hồ sơ người khác.

---

## 7. CHECKLIST TRƯỚC BUỔI BẢO VỆ

- [ ] Quay sẵn video demo backup (phòng wifi/API lỗi).
- [ ] Bật `HCDC_MOCK=1` khi demo phần số ca dịch.
- [ ] Kiểm tra API key LLM còn quota.
- [ ] Chuẩn bị kịch bản demo cố định (tài khoản, ca cefuroxime để show chặn dị ứng).
- [ ] Học thuộc 3 câu sống còn: **6, 8, 9**.
- [ ] Hoàn thiện slide cuối + thêm slide Kết luận / Hạn chế / Hướng phát triển.
- [ ] Chuẩn bị trả lời nhận xét của GV phản biện.
