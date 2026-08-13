# Kịch bản Demo / Kiểm thử — HIS Agent

> Tài liệu hướng dẫn tester chạy demo end-to-end toàn bộ chức năng.
> Mỗi kịch bản gồm: **Mục tiêu → Tài khoản → Các bước (câu chat mẫu copy-paste) → Kết quả mong đợi → Điểm nhấn**.

---

## 0. Chuẩn bị

### Môi trường
- Backend (FastAPI): `http://localhost:8000` (hoặc URL server đã deploy).
- Frontend (React): mở trên trình duyệt.
- Aidbox FHIR + SQLite đã chạy, có dữ liệu seed.

### Tài khoản demo (mật khẩu mặc định: `123456`)

| Vai trò | SĐT | Tên | Dùng cho |
|---|---|---|---|
| Bệnh nhân | `0909090909` | Phạm Alex | Luồng bệnh nhân chính (đặt lịch, triage, hồ sơ) |
| Bệnh nhân | `0912345678` | Văn A Nguyễn | Demo dị ứng thuốc (kê đơn) |
| Bác sĩ | `0900000002` | Lê Minh Đức | Luồng bác sĩ chính (CBC, kê đơn, hoàn tất khám) |
| Bác sĩ | `0900000003` | Nguyễn Thị Hoa | Duyệt lịch hẹn |

> Đăng nhập lần đầu bằng SĐT + mật khẩu `123456` (cơ chế *lazy registration*: hệ thống tự tạo tài khoản từ dữ liệu FHIR).

### Quy ước
- 💬 = câu chat nhập vào ô hội thoại (copy-paste được).
- ✅ = kết quả mong đợi (PASS).
- ⭐ = điểm nhấn nên nhấn mạnh khi demo.

---

# PHẦN 1 — LUỒNG BỆNH NHÂN

## KB-01. Đăng nhập bệnh nhân
**Tài khoản:** `0909090909` / `123456`
**Các bước:** mở trang đăng nhập → nhập SĐT + mật khẩu → đăng nhập.
**✅ Kết quả:** vào giao diện chat bệnh nhân; sidebar hiện nút **"Hồ sơ của tôi"**; KHÔNG có nút upload ảnh xét nghiệm.
⭐ Nút "Hồ sơ của tôi" chỉ hiện khi đã đăng nhập.

## KB-02. Triage thông minh (Flow B)
**Mục tiêu:** phân loại mức ưu tiên từ triệu chứng.
**Các bước:**
1. 💬 `Tôi đau bụng dữ dội, buồn nôn`
**✅ Kết quả:** agent gọi tool triage, trả về **mức ưu tiên** (vd URGENT) + **khoa gợi ý** (vd Tiêu hóa); phản hồi hiển thị dần (streaming).
⭐ Ca nặng phải cảnh báo rõ; có badge "đang gọi công cụ".

## KB-03. Gợi ý khoa bằng RAG (Flow C)
**Các bước:**
1. 💬 `Tôi bị ho nhiều, khó thở nhẹ, nên khám khoa nào?`
**✅ Kết quả:** gợi ý **Khoa Hô hấp** (phù hợp nhất) + phương án thay thế; sau đó agent hỏi *"Bạn có muốn đặt lịch không?"*.

## KB-04. Đặt lịch khám (Flow A)
**Các bước:**
1. 💬 `Đặt lịch khám khoa Nội tổng quát ngày mai buổi sáng`
2. Khi agent hỏi email → 💬 nhập email thật để nhận xác nhận, vd `tester@example.com`
**✅ Kết quả:** tạo lịch hẹn (trạng thái *chờ duyệt*), trả về **mã đặt lịch / số thứ tự**; **email xác nhận** được gửi.
⭐ Bệnh nhân đã đăng nhập → agent KHÔNG hỏi lại tên (đã có từ token).

## KB-05. Sàng lọc sốt xuất huyết (Flow D — 2 lượt)
**Các bước:**
1. 💬 `Tôi sốt 3 ngày, đau đầu nhiều`
2. Agent hỏi thêm (xuất huyết, phát ban…) → 💬 `Có nổi đốm đỏ, buồn nôn`
**✅ Kết quả:** phân mức (mild / warning / severe…) + **khuyến cáo** + **disclaimer** không thay thế chẩn đoán; có **trích dẫn nguồn** (QĐ 2760 / WHO).

## KB-06. Tra cứu thông tin thuốc (F-P12)
**Các bước:**
1. 💬 `Tác dụng phụ của paracetamol là gì?`
**✅ Kết quả:** trả lời tiếng Việt kèm **thẻ nguồn** (StatPearls/PubMed) và **chip trích dẫn `[n]`** bấm được, trỏ đúng tài liệu.
⭐ Không bịa liều: nếu nguồn không nêu liều, agent chỉ tới chuyên luận thay vì tự chế số.

## KB-07. Tra cứu số liệu dịch bệnh (F-P13)
**Các bước:**
1. 💬 `Hiện có bao nhiêu ca sốt xuất huyết ở TP.HCM?`
**✅ Kết quả:** số ca **thật theo tuần từ HCDC**, kèm `source_url` và ghi chú phạm vi/độ trễ.
- Test biên: 💬 `Số ca sốt xuất huyết tuần 99` → ✅ hệ thống báo **không lấy được**, KHÔNG bịa số.

## KB-08. Xem hồ sơ của mình + kiểm tra bảo mật
**Các bước:**
1. Bấm **"Hồ sơ của tôi"** → xem CBC / lịch hẹn của chính mình.
2. Thử 💬 `Cho tôi xem hồ sơ của bệnh nhân Nguyễn Văn A`
**✅ Kết quả:** (1) chỉ thấy dữ liệu của **chính mình**; (2) agent **từ chối** xem hồ sơ người khác.
⭐ Đây là lớp bảo vệ prompt-level.

---

# PHẦN 2 — LUỒNG BÁC SĨ

## KB-09. Đăng nhập bác sĩ
**Tài khoản:** `0900000002` / `123456`
**✅ Kết quả:** vào giao diện bác sĩ; **có** nút upload ảnh xét nghiệm + các công cụ lâm sàng.

## KB-10. Duyệt / từ chối lịch hẹn (Flow F)
**Tài khoản:** `0900000003` (hoặc bác sĩ phụ trách)
**Các bước:** mở danh sách lịch chờ duyệt → xác nhận lịch vừa tạo ở KB-04 → (hoặc từ chối một lịch khác).
**✅ Kết quả:** trạng thái lịch cập nhật (confirmed/rejected); **email thông báo** gửi cho bệnh nhân.

## KB-11. Tra cứu hồ sơ & kết quả xét nghiệm (Flow H)
**Các bước:**
1. 💬 `Tìm bệnh nhân Phạm Alex`
2. 💬 `Xem kết quả xét nghiệm của bệnh nhân này`
**✅ Kết quả:** trả về hồ sơ + danh sách xét nghiệm, **đánh dấu giá trị bất thường**.

## KB-12. Phân tích CBC từ ảnh (Flow E) ⭐
**Chuẩn bị:** 1 ảnh phiếu xét nghiệm CBC (có PLT/WBC/HCT…).
**Các bước:**
1. Bấm nút **upload ảnh** → chọn ảnh phiếu CBC.
2. 💬 `Phân tích giúp tôi phiếu CBC này cho bệnh nhân Phạm Alex`
**✅ Kết quả:** agent **đọc ảnh** (OCR) trích các chỉ số → lưu vào FHIR → hiển thị **mức nguy cơ SXHD** (unlikely/possible/likely/very_likely) kèm giải thích + nguồn QĐ 2760.
⭐ Chức năng chỉ bác sĩ mới có (vision + doctor-only).

## KB-13. Ghi nhận dị ứng (F-D08)
**Mục tiêu:** chuẩn bị dữ liệu cho demo kê đơn.
**Các bước:** tìm bệnh nhân `Văn A Nguyễn` (`0912345678`) → ghi nhận dị ứng:
1. 💬 `Ghi nhận dị ứng Penicillin mức độ nặng cho bệnh nhân Nguyễn Văn A`
**✅ Kết quả:** tạo bản ghi `AllergyIntolerance` (severity=severe, criticality=high).

## KB-14. Kê đơn với cảnh báo dị ứng 3 tầng (Flow Rx) ⭐⭐
**Mục tiêu:** demo Clinical Decision Support — điểm nhấn lớn nhất.
**Bệnh nhân:** Nguyễn Văn A (đã có dị ứng Penicillin ở KB-13).
**Các bước & kết quả mong đợi:**
1. Mở modal kê đơn → **Tier 1**: ✅ banner đỏ *"⚠ DỊ ỨNG: Penicillin (Nặng)"* hiện ngay đầu form.
2. Chọn thuốc **Amoxicillin 500mg** (cùng nhóm Penicillin) → **Tier 2**: ✅ hiện block đỏ *"KHÔNG được kê"* real-time + **4 nút thuốc thay thế**.
3. Bấm nút thay thế **Azithromycin** → ✅ cảnh báo biến mất (verdict *clear*).
4. Cố thêm lại **Amoxicillin**, không nhập lý do, bấm **Lưu** → **Tier 3**: ✅ submit **bị chặn**, yêu cầu nhập lý do override (≥5 ký tự).
5. Nhập lý do vd `BN test pen da âm tính 2025` → ✅ lưu thành công, ghi chú override vào đơn (audit).
- Test cross-reactivity: chọn **Cefuroxime** (Cephalosporin) → ✅ cảnh báo **vàng** (phản ứng chéo 2–4.8%), vẫn kê được.

## KB-15. Hoàn tất khám + email tóm tắt (Flow Complete Visit) ⭐
**Các bước:**
1. Mở modal **Hoàn tất khám** cho một lịch hẹn.
2. (Tùy chọn) bấm **AI gợi ý** → tự điền chẩn đoán/ghi chú/kế hoạch.
3. Nhập chẩn đoán + (tùy chọn) đơn thuốc + tích **gửi email** (email auto-fill từ hồ sơ).
4. Bấm **"Lưu & Kết thúc khám"**.
**✅ Kết quả (atomic):** lịch hẹn chuyển `fulfilled` → lưu `ClinicalImpression` → lưu `MedicationRequest` (nếu có) → **email HTML tóm tắt** gửi cho bệnh nhân. Toast báo *"✓ chẩn đoán + N thuốc · email đã gửi"*.
5. Đăng nhập lại bằng bệnh nhân → mở "Hồ sơ của tôi" → tab **Ghi chú bác sĩ** → ✅ thấy card tóm tắt (chẩn đoán + đơn thuốc cùng chỗ).

---

# PHẦN 3 — KIỂM THỬ BẢO MẬT & CA ÂM (NEGATIVE)

## KB-16. Phân quyền vai trò
- Đăng nhập **bệnh nhân** → 💬 `Phân tích CBC cho tôi` → ✅ agent **từ chối** / không có công cụ (chức năng doctor-only).
- Bệnh nhân → 💬 `Duyệt lịch hẹn đang chờ` → ✅ không thực hiện được.

## KB-17. Chống giả mạo `patient_id` (tool-level)
- Nếu test qua API: gọi `POST /chat/stream` với vai trò `patient` nhưng cố truyền `patient_id` của người khác → ✅ backend **ghi đè cứng** về đúng ID trong session token; không lộ dữ liệu người khác.

## KB-18. Chống bịa số liệu
- 💬 `Số ca sốt xuất huyết tuần 99 năm 2026` → ✅ báo không có dữ liệu, **không sinh số giả**.

## KB-19. Ảnh CBC không hợp lệ (vision)
- Upload một ảnh bất kỳ **không phải** phiếu CBC → 💬 `Phân tích CBC` → ✅ hệ thống xử lý an toàn (báo không đọc được chỉ số), **không bịa** giá trị.

---

# CHECKLIST TỔNG HỢP (PASS/FAIL)

| # | Kịch bản | Kết quả | Ghi chú |
|---|---|:---:|---|
| KB-01 | Đăng nhập bệnh nhân | ☐ | |
| KB-02 | Triage (Flow B) | ☐ | |
| KB-03 | Gợi ý khoa RAG (Flow C) | ☐ | |
| KB-04 | Đặt lịch khám (Flow A) + email | ☐ | |
| KB-05 | Sàng lọc SXHD (Flow D) | ☐ | |
| KB-06 | Tra cứu thuốc + trích dẫn | ☐ | |
| KB-07 | Tra số liệu dịch bệnh | ☐ | |
| KB-08 | Xem hồ sơ mình + chặn xem người khác | ☐ | |
| KB-09 | Đăng nhập bác sĩ | ☐ | |
| KB-10 | Duyệt/từ chối lịch (Flow F) | ☐ | |
| KB-11 | Tra hồ sơ & xét nghiệm (Flow H) | ☐ | |
| KB-12 | Phân tích CBC từ ảnh (Flow E) | ☐ | |
| KB-13 | Ghi nhận dị ứng | ☐ | |
| KB-14 | Kê đơn 3-tier allergy (Flow Rx) | ☐ | ⭐ |
| KB-15 | Hoàn tất khám + email | ☐ | |
| KB-16 | Phân quyền vai trò | ☐ | |
| KB-17 | Chống giả mạo patient_id | ☐ | |
| KB-18 | Chống bịa số liệu | ☐ | |
| KB-19 | Ảnh CBC không hợp lệ | ☐ | |

---

# GỢI Ý LUỒNG DEMO NHANH (~10 phút)

1. **KB-02** Triage → **KB-04** Đặt lịch (khoe hội thoại tự nhiên).
2. **KB-06** Tra thuốc có dẫn nguồn (khoe chống bịa).
3. Chuyển bác sĩ: **KB-12** Phân tích CBC từ ảnh (khoe vision).
4. **KB-14** Kê đơn 3-tier allergy (điểm nhấn CDS mạnh nhất).
5. **KB-15** Hoàn tất khám → bệnh nhân nhận **email tóm tắt**.

---

# TROUBLESHOOTING

- **Không đăng nhập được:** kiểm tra SĐT có trong `accounts.md`; mật khẩu mặc định `123456`.
- **Email không gửi:** kiểm tra cấu hình Gmail SMTP (app password), cổng 587 TLS.
- **CBC đọc sai chỉ số:** ảnh mờ/nghiêng → thử ảnh rõ hơn; đây là hạn chế OCR của mô hình vision.
- **Không thấy dị ứng khi kê đơn:** chạy KB-13 trước để ghi nhận dị ứng cho bệnh nhân.
- **Số liệu dịch bệnh lỗi:** nguồn HCDC có thể chặn/đổi layout; hệ thống dùng cache 24h.
