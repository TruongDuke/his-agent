---
marp: true
theme: gaia
paginate: true
size: 16:9
title: HIS Agent — Trợ lý AI cho Bệnh viện (Bản giới thiệu khách hàng)
---

<!--
HƯỚNG DẪN:
- Xuất PDF: cài extension "Marp for VS Code" → mở file này → Export (PDF).
  Hoặc CLI: npx @marp-team/marp-cli deck-sales.md --pdf   (PPTX: --pptx)
- Mỗi "---" là một slide.
- Đây là bản CHÀO KHÁCH HÀNG — KHÔNG đụng tới deck.md (bản đồ án).
-->

<!-- _class: lead -->

# HIS-Agent

## Trợ lý AI cho bệnh viện — nói tiếng Việt,
## làm việc **thật** trên hồ sơ bệnh nhân (FHIR R5)

---

<!-- _class: lead -->

# Nỗi đau hôm nay

- 📞 Đặt lịch phải **gọi điện, xếp hàng**
- ❓ Có triệu chứng nhưng **không biết khám khoa nào**
- 🦟 Sốt xuất huyết **nhập viện muộn**
- 💊 Bác sĩ có thể **kê nhầm thuốc gây dị ứng**

> HIS hiện tại **quản lý dữ liệu** — nhưng không giúp con người **ra quyết định**.

---

<!-- _class: lead -->

# Giải pháp

## Một trợ lý AI **hội thoại tiếng Việt**,
## thao tác **thật** trên hồ sơ bệnh viện — không phải chatbot FAQ.

---

# Giá trị 1 — Bệnh nhân tự phục vụ
## *Khỏi gọi điện. Khỏi xếp hàng.*

- Kể triệu chứng → AI **phân loại mức độ khẩn cấp (triage)**
- **Gợi ý đúng khoa** trong 18 chuyên khoa (RAG)
- **Đặt / huỷ / xem lịch** ngay trong hội thoại
- Tự **gửi email xác nhận** lịch hẹn

> Giảm tải tổng đài & quầy tiếp nhận.

---

# Giá trị 2 — Sàng lọc Sốt xuất huyết
## *Phát hiện sớm, theo chuẩn Bộ Y tế.*

- Hàng trăm nghìn ca/năm ở VN — nhiều ca **nhập viện muộn**
- Sàng lọc theo **QĐ 2760/QĐ-BYT 2023**:
  - Từ **triệu chứng** (hội thoại)
  - Từ **ảnh phiếu xét nghiệm CBC** (đọc số tự động)

---

# Giá trị 3 — Bác sĩ & an toàn kê đơn
## *Hỗ trợ quyết định lâm sàng (CDS).*

- Tra hồ sơ, xét nghiệm bằng **ngôn ngữ tự nhiên**
- Ghi **sinh hiệu** → tự cảnh báo bất thường (BYT 3192 · NEWS2)
- **Kê đơn chặn dị ứng**: đối chiếu danh mục ~50 thuốc · cảnh báo dị ứng chéo · 3 mức
- Hoàn tất khám → tự **gửi email tóm tắt** cho bệnh nhân

---

# Quy trình khám bệnh — đầu đến cuối

<style scoped>
section { font-size: 25px; }
</style>

**① Đặt lịch — Bệnh nhân**
Mô tả triệu chứng → triage + gợi ý khoa (RAG) → chọn lịch → *chờ duyệt*

↓

**② Duyệt lịch — Bác sĩ**
Xác nhận / từ chối → 📧 email xác nhận gửi bệnh nhân

↓

**③ Khám — Bác sĩ**
Tra hồ sơ → ghi sinh hiệu (cảnh báo CDS) → phân tích CBC → kê đơn (chặn dị ứng)

↓

**④ Hoàn tất khám**
Lưu hồ sơ FHIR (chẩn đoán + đơn thuốc) → 📧 email tóm tắt gửi bệnh nhân

---

# Năng lực đầy đủ — 34 công cụ

<style scoped>
section { font-size: 21px; }
li { margin: 0.15em 0; }
</style>

- 🧭 **Phân loại & định tuyến** — triage, gợi ý khoa (18 khoa), chuyển đăng ký
- 📅 **Đặt lịch (BN)** — xem slot, đặt/huỷ/xem, email xác nhận
- 🗂️ **Quản lý lịch (BS)** — duyệt/từ chối, lịch làm việc, gợi ý bác sĩ
- 🆔 **Định danh** — đăng ký, tìm kiếm, xác thực bệnh nhân
- 📋 **Tra hồ sơ** (BN chỉ xem của mình) — tiền sử, sinh hiệu, chẩn đoán, dị ứng, đơn thuốc, CBC
- 🩺 **CDS (BS)** — ghi sinh hiệu + cảnh báo, ghi dị ứng, kê đơn chặn dị ứng, tạo/đọc CBC
- ✉️ **Tổng kết khám** — email tóm tắt tự động
- 🦟 **Sàng lọc SXH** — từ triệu chứng + ảnh phiếu CBC
- 🌐 **Tri thức sống** — thuốc (NCBI), số ca dịch (HCDC), dẫn nguồn

---

# Tích hợp KHÔNG xâm lấn
## *Cắm vào hệ thống sẵn có — không thay, không khoá vendor.*

- Chuẩn mở **FHIR R5** — nói cùng ngôn ngữ với HIS/EMR của viện
- Giao thức **A2A** — hệ thống khác gọi HIS Agent như **một agent chuẩn**
- Không cần thay hệ thống hiện có; triển khai theo từng phần

> Bổ sung lớp "ra quyết định" lên trên hạ tầng dữ liệu đang chạy.

---

# Bảo mật & dữ liệu tại chỗ
## *Điều bệnh viện lo nhất — được thiết kế từ gốc.*

- 🏥 Triển khai **on-prem** — dữ liệu bệnh nhân **ở lại trong viện**
- 🔐 **Phân quyền theo vai trò** — bệnh nhân chỉ xem hồ sơ của chính mình *(đã kiểm chứng)*
- 🧱 Kiến trúc **tách "agent dữ liệu"** — cô lập khóa truy cập FHIR, **một cửa audit**
- 🚪 **A2A làm ranh giới** — hệ thống ngoài chỉ nhận câu trả lời đã lọc, **không chạm dữ liệu thô**

<!-- Ghi chú người trình bày: LLM hiện dùng dịch vụ đám mây. Muốn dữ liệu tuyệt đối không
ra ngoài, cần tuỳ chọn LLM chạy nội bộ (on-prem GPU). Không hứa "100% offline". -->

---

# Tri thức sống + Tuân thủ
## *Cập nhật thời gian thực — không "đóng băng" theo ngày huấn luyện.*

- 💊 **NCBI** (StatPearls / PubMed) — thông tin thuốc
- 🦟 **HCDC** — số ca dịch bệnh theo tuần
- 🏥 **FHIR** — hồ sơ bệnh nhân thật
- 📎 Mọi câu trả lời **dẫn nguồn** — chip **[n]** bấm được, kiểm chứng tận gốc
- ⚖️ Tuân thủ **QĐ 2760 · 3192 · 1165/QĐ-BYT**, WHO

---

# Độ tin cậy

- ✅ Sàng lọc SXHD: **khớp phác đồ** trên các kịch bản chuẩn
- ✅ Phân quyền: bệnh nhân **không** truy cập được dữ liệu người khác
- ✅ **Kiểm chứng trích dẫn**: đối chiếu từng nguồn
- ✅ Phản hồi thời gian thực qua **SSE streaming**

---

# Mô hình triển khai

<style scoped>
section { font-size: 24px; }
</style>

- 🏥 **On-prem / hybrid** — phù hợp yêu cầu dữ liệu tại chỗ
- 🔌 **Tích hợp qua FHIR** sẵn có — không đập đi làm lại
- 🚀 **Lộ trình pilot**: 1 khoa / 1 luồng → đánh giá → mở rộng toàn viện

> _Thời gian triển khai · yêu cầu hạ tầng · chi phí: trao đổi theo quy mô từng viện._

---

<!-- _class: lead -->

# Bước tiếp theo

## Chạy thử **pilot** trên 1 khoa / 1 luồng khám
## Thấy giá trị thật trước khi mở rộng.

**Liên hệ:** _[tên · email · điện thoại]_
