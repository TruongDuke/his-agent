---
marp: true
theme: gaia
paginate: true
size: 16:9
title: HIS Agent — Trợ lý AI cho Hệ thống Thông tin Bệnh viện
---

<!--
HƯỚNG DẪN:
- Xuất PDF: cài extension "Marp for VS Code" → mở file này → Export (PDF).
  Hoặc CLI: npx @marp-team/marp-cli deck.md --pdf   (PPTX: --pptx)
- Mỗi "---" là một slide.
-->

<!-- _class: lead -->

# HIS-Agent

---

<!-- _class: lead -->

# Nỗi đau

- 📞 Đặt lịch phải **gọi điện, xếp hàng**
- ❓ Có triệu chứng nhưng **không biết khám khoa nào**
- 🦟 Sốt xuất huyết **nhập viện muộn**
- 💊 Bác sĩ có thể **kê nhầm thuốc gây dị ứng**

> HIS hiện tại **quản lý dữ liệu** — nhưng không giúp con người **ra quyết định**.

---

<!-- _class: lead -->

# Giải pháp

## Một trợ lý AI **nói chuyện bằng tiếng Việt**,
## làm việc **thật** trên hồ sơ bệnh viện (FHIR R5).

---

# Bài toán 1 — Bệnh nhân tự phục vụ
## *Khỏi gọi điện. Khỏi xếp hàng.*

- Kể triệu chứng → AI **phân loại mức độ (triage)**
- **Gợi ý khoa** phù hợp bằng RAG
- **Đặt / huỷ / xem lịch** ngay trong hội thoại

---

# Bài toán 2 — Sàng lọc Sốt xuất huyết
## *Phát hiện sớm, theo chuẩn Bộ Y tế.*

- Hàng trăm nghìn ca/năm ở VN — nhiều ca **nhập viện muộn**
- Sàng lọc theo **QĐ 2760/QĐ-BYT 2023**:
  - Từ **triệu chứng** (hội thoại)
  - Từ **ảnh phiếu xét nghiệm CBC** (đọc số tự động)

---

# Bài toán 3 — Bác sĩ & an toàn kê đơn
## *Hỗ trợ quyết định lâm sàng (CDS).*

- Tra hồ sơ, xét nghiệm bằng ngôn ngữ tự nhiên
- Ghi **sinh hiệu** → tự cảnh báo bất thường (BYT 3192, NEWS2)
- **Kê đơn chặn dị ứng**: 4 lớp kiểm tra · 3 mức cảnh báo
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

# Knowledge base **động**
## *Tri thức cập nhật theo thời gian thực — không "đóng băng".*

- LLM chỉ biết tới thời điểm huấn luyện. HIS Agent **truy hồi nguồn sống** ngay khi được hỏi:
  - 💊 **NCBI** (StatPearls / PubMed) — thông tin thuốc
  - 🦟 **HCDC** — số ca dịch bệnh theo tuần
  - 🏥 **FHIR** — hồ sơ bệnh nhân thật
- Mọi câu trả lời **dẫn nguồn**: thẻ nguồn + chip **[n]** bấm được — kiểm chứng tận gốc

---

# HIS Agent vs MedDeep AI

<style scoped>
table { font-size: 24px; }
blockquote { font-size: 21px; margin-top: 0.3em; }
small { font-size: 15px; color: #4a4a4a; }
</style>

| Tiêu chí | MedDeep AI | **HIS Agent** |
|---|:---:|:---:|
| Đối tượng | Bác sĩ | **BN + Bác sĩ** |
| Tích hợp HIS (FHIR) | ❌ | ✅ |
| Đặt lịch · kê đơn · hồ sơ | ❌ | ✅ |
| Nguồn tri thức | PubMed | **QĐ 2760·3192·1165/QĐ-BYT**<br>WHO · HCDC · NCBI |

> *MedDeep AI **tra cứu cho bác sĩ** — HIS Agent **vận hành cả bệnh viện**.*

---

# Bên trong

- Hội thoại → **Agent (tool-calling loop)** → FHIR / SQLite
- **33 công cụ** module hoá, **phân quyền** theo vai trò
- **2 kiểu RAG**: vector (gợi ý khoa) + truy hồi API (tra thuốc)

---

# Kiểm thử & kết quả

- ✅ Sàng lọc SXHD: khớp phác đồ trên các kịch bản chuẩn
- ✅ Phân quyền: bệnh nhân **không** truy cập được dữ liệu người khác
- ✅ **Kiểm chứng trích dẫn**: đối chiếu từng nguồn (ca cefuroxime)
- ✅ Phản hồi thời gian thực qua **SSE streaming**

---

<!-- _class: lead -->

# Tầm nhìn
