# Kịch bản Demo HIS Agent (Happy Case) — khớp Sequence Diagram

> Mỗi demo map với 1 sơ đồ trong báo cáo. Gõ đúng câu, nói đúng narration.

## ⚙️ Chuẩn bị trước (5 phút)
- [ ] **Restart server** (`python main.py`) — nạp prompt + dist mới.
- [ ] Mở 2 tab: UI (localhost:8000) + Aidbox REST Console (dự phòng cô hỏi CSDL).
- [ ] Chuẩn bị 1 ảnh phiếu CBC (jpg/pdf) cho Demo 6.
- [ ] Đăng nhập sẵn 1 tài khoản **bệnh nhân** + 1 **bác sĩ**.
- [ ] Chụp screenshot mỗi bước làm dự phòng (mạng/Aidbox 502).

---

# 👤 PHẦN 1 — BỆNH NHÂN

## Demo 1 — Gợi ý khoa (RAG) + Đặt lịch  ·  SD: Flow C + Flow A
**Gõ rời từng câu (bệnh nhân đã đăng nhập):**
```
1. tôi hay đau dạ dày ợ chua sau khi ăn, khám khoa nào?
2. có, đặt lịch sớm nhất giúp tôi
3. ok, email test@gmail.com
```
**Kết quả:** ① gợi ý Khoa Tiêu Hóa (SEMI_URGENT) → ② chốt slot + bác sĩ (KHÔNG hỏi tên) → ③ tạo lịch ngay + mã lịch.

**Nói (khớp SD Flow A):**
> "RAG hiểu 'ợ chua đau dạ dày' → gợi ý đúng Tiêu Hóa dù không gõ chữ 'tiêu hóa'. Vì bệnh nhân **đã đăng nhập** nên agent dùng luôn patient_id — **không hỏi tên** — rồi tự chuỗi 3 công cụ: `suggest_department → get_next_available_slot → create_appointment`, đúng sơ đồ tuần tự Flow A. Lịch ở trạng thái proposed, chờ bác sĩ duyệt."

⚠️ Nói "đặt lịch **sớm nhất**" (không nói ngày/giờ cụ thể) → khớp hành vi `get_next_available_slot`.

FLow B tôi bị ho khan kéo dài 1 tuần


## Demo 2 — Sàng lọc Sốt xuất huyết (+ đặt lịch khẩn)  ·  SD: Flow D
**Gõ:** `tôi bị sốt 3 ngày, đau người, nổi mẩn đỏ`
**Kết quả:** hiện **phiếu tích Có/Không** → tích dịch tễ "Có", sốt "3", vài triệu chứng → Gửi → phân độ + khuyến cáo + trích QĐ 2760.

**Đặt lịch khẩn (2 lượt — GÕ ĐÚNG THẾ NÀY):**
```
1. đặt lịch khoa truyền nhiễm sớm nhất giúp tôi
2. ok đặt slot đó luôn, email <email của bạn>
```
→ Lượt 1: agent hiện **slot sớm nhất + bác sĩ**, hỏi xác nhận.
→ Lượt 2: gộp **xác nhận + email** → agent **tạo lịch ngay**, trả **mã lịch** + "⏳ chờ bác sĩ duyệt".

⚠️ **Mẹo chắc ăn:** ở lượt 2 luôn **gộp "đồng ý + email" trong 1 câu**. Đừng tách "ok" rồi mới gửi email ở lượt sau.

**Nói:**
> "Flow D — hội thoại 2 lượt: agent nhận diện triệu chứng SXH → **sơ đồ mô tả luồng logic 2 lượt; giao diện nâng cấp lượt hỏi thành phiếu tích cho nhanh** — bản chất vẫn 2 lượt. Tool phân độ bằng luật QĐ 2760, không phải LLM tự phán. Vì cảnh báo → agent tự đề xuất **đặt lịch khẩn Khoa Truyền Nhiễm**, lịch ở trạng thái *proposed* chờ bác sĩ duyệt (nối sang Demo 7)."

## Demo 3 — Tra thông tin thuốc (drug_info)  ·  (không có SD tuần tự)
**Gõ:** `tác dụng phụ của metformin là gì?`
**Kết quả:** trả lời tiếng Việt + thẻ nguồn (StatPearls/PubMed) + số [n].
**Nói:** "RAG tra NCBI, có dẫn nguồn [n], LLM chỉ nói cái có trong bằng chứng — chống bịa liều. (Phần này em mô tả bằng luồng chữ, không vẽ SD riêng.)"

## Demo 4 — Số ca dịch bệnh (outbreak)  ·  Sơ đồ luồng (pipeline, không phải SD)
**Gõ:** `hiện có bao nhiêu ca sốt xuất huyết ở TP.HCM?`
**Kết quả:** số ca tuần + xu hướng + nguồn HCDC + tuần cụ thể.
**Nói:** "Số thật từ HCDC, cache lazy 24h; xu hướng render sẵn để LLM không bịa số. Đây là **sơ đồ luồng xử lý** (lazy-refresh + tra cứu động), không phải sequence diagram."

---

# 🩺 PHẦN 2 — BÁC SĨ

## Demo 5 — Cảnh báo dị ứng khi kê đơn (3-tier) ⭐  ·  SD: 3-tier allergy
**Thao tác:** Tra **Phan Hùng** → **Kê đơn**.
- Banner đỏ đầu form: **"Dị ứng thuốc: Penicilin"** (Tier 1)
- Chọn **Amoxicillin 500** → dòng đỏ **BLOCK** (cùng nhóm penicillin, Tier 2/3)
- Đổi **Azithromycin** → xanh, kê được

**Nói:**
> "3-tier alert: banner cảnh báo sớm (Tier 1), check real-time khi chọn thuốc (Tier 2), hard-stop chặn kê (Tier 3). Bắt cả **phản ứng chéo**, không chỉ trùng tên — luật từ Stockley's/BNF, đúng sơ đồ 3-tier."

## Demo 6 — Phân tích CBC từ ảnh  ·  SD: Flow E
**Thao tác:** Tra **Phan Hùng** → **CBC** → upload ảnh phiếu → phân tích.
**Kết quả:** trích PLT/WBC/HCT + lưu FHIR + đánh giá nguy cơ SXHD.
**Nói:** "Flow E: OCR đọc số từ ảnh → LLM trích → lưu Observation → tự sàng lọc SXHD bằng luật. Chỉ bác sĩ dùng được."
*(Dự phòng ảnh lỗi: nhập tay qua form CBC → cùng kết quả.)*

## Demo 7 — Duyệt lịch + Kết thúc khám  ·  SD: Complete Visit
**Thao tác:** Lịch chờ → **Xác nhận** lịch Demo 1 (email xác nhận gửi đi) → mở bệnh nhân → **Kết thúc khám** → nhập chẩn đoán/kế hoạch → gửi email tóm tắt.
**Nói:** "Vòng khép kín: proposed → booked (email xác nhận) → fulfilled (tạo ClinicalImpression + email tóm tắt)."

---

## 🎯 Trình tự đề xuất (7-8 phút)
1. Demo 1 (đặt lịch) — khoe RAG + agent tự chuỗi tool (khớp Flow A)
2. Demo 5 (dị ứng) — ĂN ĐIỂM NHẤT
3. Demo 2 (SXH form) — luật y khoa có nguồn
4. Demo 6 (CBC ảnh) — nếu còn thời gian
5. Demo 7 (duyệt lịch → email) — vòng khép kín

## Câu chốt mọi demo
> "Phần quyết định lâm sàng là **luật có nguồn**, LLM chỉ điều phối — nên đáng tin, không ảo giác."

## ⚠️ Tránh khi demo happy-case
- Đừng gõ "đau ngực khó thở" ở demo gợi ý khoa → ra cảnh báo 115 (đúng nhưng không phải happy case).
- Demo 1: nói "sớm nhất", đừng nói ngày/giờ cụ thể.
