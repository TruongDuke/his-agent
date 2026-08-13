# ÔN TẬP — Complete Visit Modal (Kết thúc khám)

> Luồng bác sĩ "hoàn tất khám" — gộp nhiều hành động thành một thao tác (orchestration).
> Backend: `api/routes/appointments.py` (endpoint `/api/complete-appointment/{id}`).
> Frontend: `submitCompleteAppt()` gọi tuần tự endpoint này rồi `/api/prescription`.

---

## 1. BẢN CHẤT (1 câu)
Đây là luồng **điều phối** (không phải thuật toán): khi bác sĩ bấm "Hoàn tất khám", hệ thống thực hiện nhiều hành động ghi dữ liệu + gửi email trong một thao tác.

## 2. 4 HÀNH ĐỘNG
| # | Hành động | Ở đâu | Dòng |
|---|---|---|---|
| 1 | Appointment → **`status: fulfilled`** (GET → set → PUT) | backend | 161–168 |
| 2 | Tạo **ClinicalImpression** (chẩn đoán + ghi chú + kế hoạch) | backend | 170–192 |
| 3 | **Đơn thuốc** (`/api/prescription`, có check dị ứng 3 tầng) | frontend gọi riêng | — |
| 4 | **Email tóm tắt** khám (tùy chọn, non-blocking) | backend | 194–231 |
| — | Return kết quả gộp (appt_id, ci_id, email) | backend | 233–238 |

→ Backend làm 1, 2, 4; frontend gọi backend **rồi** gọi prescription (3).

## 3. BA ĐIỂM ĐÁNG NÓI

### a) ClinicalImpression lưu 3 loại thông tin + mẹo `__plan__:`
- `description` = **chẩn đoán**.
- `note[]` = **ghi chú thường** + **kế hoạch tái khám**.
- Kế hoạch gắn tiền tố **`__plan__:`** (dòng 174–175) để tách được "kế hoạch" khỏi "ghi chú" — vì FHIR ClinicalImpression không có field "plan" riêng.

### b) Vòng khép kín với "agent chủ động"
`__plan__:` chính là thứ tính năng **`__init__`** đọc lại: lần khám sau, agent lấy ClinicalImpression gần nhất có kế hoạch → **chủ động nhắc** BN/BS.
- Đọc lại: `/api/patient/{id}/clinical-impressions` (appointments.py:241) + `pending-plans` (~285).
- Agent dùng: khối `__init__` trong `chat.py:81–99` → tiêm vào system prompt.
→ Khám xong ghi kế hoạch → lần sau agent nhắc = vòng khép kín.

### c) Email non-blocking, tùy chọn
Chỉ gửi khi `send_email=true` + có `patient_email` (dòng 196). Kết quả email trả **riêng** trong field `email` (dòng 237) → lỗi email không làm hỏng việc kết thúc khám.

## 4. ⚠️ ĐIỂM TRUNG THỰC (tự nói trước, đừng để hội đồng bắt)
> *"Em gọi '4 hành động' nhưng **chưa atomic thật sự** — không có transaction/rollback. Nếu ClinicalImpression đã tạo mà email lỗi thì appointment vẫn đã `fulfilled`. Em giảm rủi ro bằng cách: cập nhật trạng thái + lưu hồ sơ TRƯỚC, email/đơn thuốc SAU, và email non-blocking. Làm atomic đúng nghĩa cần **FHIR transaction Bundle** — là hướng cải tiến."*

## 5. CÂU HỎI BẪY + ĐÁP
- *"Atomic thật không?"* → Không; tuần tự, không rollback. Hướng cải tiến: FHIR transaction Bundle.
- *"Sao đơn thuốc gọi riêng, không gộp backend?"* → Đơn thuốc cần check dị ứng 3 tầng + có thể bị block/override; tách endpoint `/api/prescription` để xử lý riêng, frontend điều phối thứ tự.
- *"Lưu 'plan' ở đâu trong FHIR?"* → Trong `note[]` của ClinicalImpression, gắn tiền tố `__plan__:` để nhận diện lại.

## 6. CÂU CHỐT (học thuộc)
> *"Complete Visit Modal gộp việc kết thúc khám thành một thao tác: cập nhật lịch hẹn thành 'fulfilled', tạo ClinicalImpression lưu chẩn đoán/ghi chú/kế hoạch, kê đơn (có kiểm tra dị ứng), và gửi email tóm tắt. Kế hoạch đánh dấu `__plan__:` để lần khám sau agent chủ động nhắc — một vòng khép kín. Chưa atomic thật; hướng cải tiến là FHIR transaction Bundle."*

---

# BẢN ĐỒ DÒNG CODE (`api/routes/appointments.py`)

| Mục | Dòng |
|---|---|
| Endpoint `/api/complete-appointment/{id}` | 150–151 |
| **HĐ1** GET appointment → set `fulfilled` → PUT | 161–168 |
| **HĐ2** Gom `note[]` (ghi chú + kế hoạch) | 171–175 |
| ├ ghi chú thường | 172–173 |
| └ **kế hoạch gắn `__plan__:`** ← chỉ tay | 174–175 |
| ├ build ClinicalImpression (`description=diagnosis`) | 177–184 |
| └ POST lên Aidbox, lấy `ci_id` | 188–192 |
| **HĐ4** điều kiện gửi email | 196 |
| ├ lấy tên BN / BS | 198–213 |
| └ gọi `fhir_send_visit_summary` | 215–231 |
| Return (appt_id, ci_id, email) | 233–238 |
| Đọc lại kế hoạch: `/clinical-impressions` | 241+ |
| Đọc lại kế hoạch: `pending-plans` (bác sĩ) | ~285 |

## Liên quan
- Agent chủ động dùng kế hoạch: `api/routes/chat.py:81–99` (khối `__init__`).
- Đơn thuốc + check dị ứng: `tools/fhir/fhir_create_prescription.py` + `fhir_check_drug_allergy.py` (xem `ON_TAP_ALLERGY.md`).

## 3 DÒNG "CHỈ TAY"
- **Mẹo `__plan__:`** → dòng **175**
- **Vòng khép kín với agent** → `chat.py:81–99`
- **Chưa atomic** → so dòng **166** (đã ghi) với **215** (bước sau, có thể lỗi), không rollback

---

# BỔ SUNG: Nút "AI gợi ý" — `/api/suggest-completion` (dòng 355+)

## Là gì
Trong modal kết thúc khám, bác sĩ bấm **"AI gợi ý"** → hệ thống tự soạn **nháp** chẩn đoán / ghi chú / kế hoạch để bác sĩ tham khảo (rồi sửa).

## 5 bước
| Bước | Việc | Dòng |
|---|---|---|
| 1 | Lấy ngữ cảnh **SONG SONG** (`asyncio.gather`): CBC mới nhất + ClinicalImpression trước + Appointment | 369–385 |
| 2 | Parse CBC → chạy `dengue_cbc_predict` lấy đánh giá sàng lọc | 390–425 |
| 3 | Trích lý do khám + triệu chứng từ note Appointment | 427–438 |
| 4 | Trích chẩn đoán + kế hoạch lần trước (parse `__plan__:`) | 440–455 |
| 5 | Ghép prompt → gọi LLM (JSON) → trả `{diagnosis, notes, plan}` | 457–511 |

## KHÁC agent loop (điểm phải nhớ)
| | Agent loop (chat) | suggest-completion |
|---|---|---|
| Kiểu gọi LLM | vòng lặp + tool-calling | **one-shot, KHÔNG tool** |
| Đầu ra | text stream | **JSON có cấu trúc** |
| temperature | mặc định | **0.3** (thấp, ổn định) |
| Mục đích | hội thoại nhiều bước | điền sẵn 1 lần cho BS sửa |
→ Tác vụ bounded (điền 3 ô) → one-shot + JSON + temp thấp cho đáng tin cậy; agent loop là thừa.

## Điểm ăn điểm
- **Grounding**: gợi ý dựa dữ liệu thật (CBC + dengue + lý do khám + lần trước), tái dùng `dengue_cbc_predict`. Không bịa.
- **Human-in-the-loop**: chỉ là NHÁP, bác sĩ duyệt/sửa rồi mới lưu. AI không tự ghi hồ sơ.
- Bóc JSON an toàn (bỏ markdown code block) + try/except: dòng 498–504.

## Câu hỏi bẫy
- *"AI tự chẩn đoán rồi lưu?"* → Không, chỉ gợi ý nháp; bác sĩ duyệt/sửa trước khi lưu.
- *"Sao không dùng agent loop?"* → tác vụ bounded, one-shot JSON temp 0.3 ổn định hơn.
- *"LLM trả sai JSON?"* → có bóc code block + try/except trả lỗi rõ (498–504).
