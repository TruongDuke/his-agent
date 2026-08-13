# Kịch bản Demo HIS Agent (Happy Case) — khớp Sequence Diagram

> Mỗi demo map với 1 sơ đồ trong báo cáo. Gõ đúng câu, nói đúng narration.

## ⚙️ Chuẩn bị trước (5 phút)
- [ ] Chạy trên **bản deploy thật**: https://his.svisor.vn (không phải localhost — đỡ rủi ro
      máy cá nhân, và đúng cái đang chạy production). Dự phòng local: `python main.py` → localhost:8000.
- [ ] Mở 2 tab: UI + Aidbox REST Console (dự phòng cô hỏi CSDL).
- [ ] Chuẩn bị 1 ảnh phiếu CBC (jpg/pdf) cho Demo 6.
- [ ] Đăng nhập sẵn 1 tài khoản **bệnh nhân** + 1 **bác sĩ**.
- [ ] **Mở sẵn 1 hộp thư Gmail thật** — Demo 7/8 gửi email xác nhận và nhắc uống thuốc,
      phải chiếu được email nhận thật thì mới ăn điểm.
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

⚠️ Câu chốt hiện đúng là **"Đã ghi nhận lịch khám, đang chờ bác sĩ xác nhận."** — KHÔNG còn chữ
"đặt lịch thành công" như bản cũ. Đây là sửa theo bug QA báo (AYT-3): nói "thành công" khiến bệnh
nhân tưởng xong rồi ngồi chờ email, trong khi email chỉ gửi sau khi bác sĩ duyệt. Nếu cô hỏi, đây là
chi tiết đáng khoe: **trạng thái hiển thị phải khớp trạng thái thật của dữ liệu.**

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

**Nối tiếp — vết audit (làm luôn, tốn 20 giây):**
Quay lại **Amoxicillin**, nhập lý do override *"BN đã test pen da âm tính, theo dõi sát"* → kê →
mở lại tab **Đơn thuốc** của bệnh nhân đó.
**Kết quả:** đơn hiện tag **⚠ Có override** và **nguyên câu lý do** dưới tên thuốc.

**Nói:**
> "Chặn được là một chuyện, nhưng lâm sàng vẫn có ca bác sĩ buộc phải kê đè cảnh báo. Khi đó hệ
> thống **bắt nhập lý do và lưu vĩnh viễn vào bệnh án** (note của MedicationRequest), tra lại lúc nào
> cũng thấy ai kê, kê gì, vì sao. Không có vết này thì tính năng cảnh báo mất ý nghĩa pháp lý."

## Demo 6 — Phân tích CBC từ ảnh  ·  SD: Flow E
**Thao tác:** Tra **Phan Hùng** → **CBC** → upload ảnh phiếu → phân tích.
**Kết quả:** trích PLT/WBC/HCT + lưu FHIR + đánh giá nguy cơ SXHD.
**Nói:** "Flow E: OCR đọc số từ ảnh → LLM trích → lưu Observation → tự sàng lọc SXHD bằng luật. Chỉ bác sĩ dùng được."
*(Dự phòng ảnh lỗi: nhập tay qua form CBC → cùng kết quả.)*

## Demo 7 — Duyệt lịch + Kết thúc khám  ·  SD: Complete Visit
**Thao tác:** Lịch chờ → **Xác nhận** lịch Demo 1 (email xác nhận gửi đi) → mở bệnh nhân → **Kết thúc khám** → nhập chẩn đoán/kế hoạch → gửi email tóm tắt.
**Nói:** "Vòng khép kín: proposed → booked (email xác nhận) → fulfilled (tạo ClinicalImpression + email tóm tắt)."

💡 **Chiếu email thật** vừa nhận trong Gmail — đây là lúc ăn điểm, đừng chỉ nói suông.

**Nhánh từ chối (nếu còn thời gian):** đặt thêm 1 lịch rác rồi bấm **Từ chối**.
**Kết quả:** lịch chuyển `cancelled` + **slot được trả lại** → mở lại danh sách slot thấy giờ đó trống.
**Nói:** "Từ chối không chỉ đổi trạng thái mà phải **giải phóng slot**, nếu không giờ đó bị khoá vĩnh
viễn mà không ai đặt được. Thứ tự thao tác cũng quan trọng: hủy lịch thành công rồi mới trả slot —
làm ngược lại thì lúc lỗi sẽ có slot trống nhưng lịch vẫn treo, bệnh nhân khác đặt trùng."

---

# 🆕 PHẦN 3 — TÍNH NĂNG MỚI

## Demo 8 — Nhắc uống thuốc qua email ⭐  ·  (mở rộng từ Demo 5/7)
**Thao tác (bác sĩ):** kê đơn ở Demo 5 → tích sẵn **"⏰ Nhắc bệnh nhân uống thuốc qua email"** +
điền email → kê.
**Thao tác (bệnh nhân):** đăng nhập → **Hồ sơ của tôi** → tab **Nhắc uống thuốc**.
**Kết quả:** lịch nhắc tự suy ra từ đơn — thuốc 2 lần/ngày ra **08:00 và 20:00**, kèm ngày bắt đầu/kết
thúc theo số ngày điều trị. Bệnh nhân sửa giờ / tắt từng thuốc được. Bấm **Gửi thử** → chiếu email thật.

**Nói:**
> "Bác sĩ không phải nhập lịch nhắc thủ công — hệ thống suy từ chính đơn thuốc: tần suất mấy lần/ngày
> ra bấy nhiêu mốc giờ, hết liệu trình thì tự dừng. Chạy bằng luồng nền tick mỗi phút, có chống gửi
> trùng, và **bù được nhắc bị lỡ trong 30 phút** phòng khi server restart đúng giờ uống thuốc."

⚠️ Nhắc thật chạy theo giờ hệ thống nên **đừng ngồi chờ tới 08:00** — dùng nút **Gửi thử**, hoặc sửa
giờ nhắc thành 2 phút sau giờ hiện tại rồi chờ.

## Demo 9 — Bác sĩ tự cấu hình báo cáo CBC  ·  (khoe tính cá nhân hoá)
**Thao tác:** vai bác sĩ → trong khung chat bấm **"Cấu hình báo cáo CBC"** → đổi *độ dài* sang **ngắn
gọn**, tắt **trích dẫn**, bật **thang điểm** → lưu → phân tích lại 1 phiếu CBC.
**Kết quả:** cùng dữ liệu, báo cáo trình bày khác hẳn theo đúng cấu hình.

**Nói:**
> "Mỗi bác sĩ có thói quen đọc khác nhau — người muốn đủ trích dẫn, người chỉ cần kết luận. Cấu hình
> lưu riêng theo từng bác sĩ rồi **biên dịch thành một đoạn prompt ghép vào system prompt** lúc chat.
> Nói cách khác, bác sĩ chỉnh được hành vi AI mà không cần ai sửa code."

## Demo 10 — Đầu chờ tích hợp HIS bệnh viện  ·  (trả lời câu "triển khai thật thì sao?")
Đây là **demo bằng lời + 1 câu lệnh**, không có UI. Chỉ dùng khi hội đồng hỏi về khả năng tích hợp.

```bash
curl https://his.svisor.vn/api/his/capabilities
```
**Kết quả:** trả về hợp đồng tích hợp — 5 loại bản tin (bệnh nhân, lượt khám, kết quả xét nghiệm,
đơn thuốc, lịch hẹn), cách xác thực, quy tắc chống gửi trùng, và `status: stub`.

**Nói:**
> "Hệ thống hiện chạy trên FHIR/Aidbox. Muốn ghép vào HIS thật của bệnh viện thì em đã **chốt sẵn hợp
> đồng API**: schema từng loại bản tin, xác thực bằng API key, chống gửi trùng theo message_id. Bên HIS
> tích hợp và test được ngay từ bây giờ; phần ánh xạ dữ liệu sang FHIR làm sau mà **không phải đổi hợp
> đồng**, họ không phải sửa code. Em cố ý để `persisted_to_fhir: false` cho minh bạch — chưa ghi vào
> bệnh án chính thức thì phải nói rõ là chưa."

⚠️ Cổng đang **đóng** (chưa đặt `HIS_API_KEY` trên server) nên POST sẽ trả 503 — **đó là đúng thiết
kế**, không phải lỗi. Nếu muốn demo POST thành công thì đặt key vào `.env` trên server rồi deploy lại.

---

## 🎯 Trình tự đề xuất

**Bản 7-8 phút (an toàn — nếu bị giới hạn thời gian):**
1. Demo 1 (đặt lịch) — khoe RAG + agent tự chuỗi tool (khớp Flow A)
2. Demo 5 (dị ứng **+ vết audit override**) — ĂN ĐIỂM NHẤT
3. Demo 2 (SXH form) — luật y khoa có nguồn
4. Demo 6 (CBC ảnh) — nếu còn thời gian
5. Demo 7 (duyệt lịch → email) — vòng khép kín

**Bản 12-15 phút (đầy đủ — nên dùng nếu được):**
Chạy nguyên mạch 1 bệnh nhân từ đầu tới cuối, **không nhảy cóc** — hội đồng thấy được vòng đời trọn vẹn:

| # | Bước | Demo |
|---|------|------|
| 1 | Bệnh nhân tả triệu chứng → gợi ý khoa → đặt lịch | Demo 1 |
| 2 | Bác sĩ duyệt lịch → bệnh nhân nhận email xác nhận | Demo 7 |
| 3 | Khám: đọc ảnh CBC → phân tích | Demo 6 |
| 4 | Kê đơn: cảnh báo dị ứng chặn → override có lý do | Demo 5 |
| 5 | Vết audit: mở lại đơn, thấy lý do override | Demo 5 (nối) |
| 6 | Bệnh nhân nhận lịch nhắc uống thuốc | Demo 8 |
| 7 | Kết thúc khám → email tóm tắt | Demo 7 |

Demo 9 (cấu hình CBC) và Demo 10 (đầu chờ HIS) để **dành trả lời câu hỏi**, đừng nhét vào mạch chính:
- Hỏi *"AI trả lời cứng nhắc, bác sĩ muốn khác thì sao?"* → Demo 9
- Hỏi *"triển khai vào bệnh viện thật thế nào?"* → Demo 10
- Hỏi *"LLM có bịa không?"* → Demo 3 (drug_info có trích dẫn) + câu chốt bên dưới

## Câu chốt mọi demo
> "Phần quyết định lâm sàng là **luật có nguồn**, LLM chỉ điều phối — nên đáng tin, không ảo giác."

## ⚠️ Tránh khi demo happy-case
- Đừng gõ "đau ngực khó thở" ở demo gợi ý khoa → ra cảnh báo 115 (đúng nhưng không phải happy case).
- Demo 1: nói "sớm nhất", đừng nói ngày/giờ cụ thể.
- Demo 8: đừng ngồi chờ tới giờ nhắc thật — dùng nút **Gửi thử**.
- Demo 10: POST vào `/api/his/*` sẽ trả 503 vì cổng đang đóng. Chỉ chiếu `capabilities` (GET), đừng
  demo POST trừ khi đã đặt `HIS_API_KEY` trên server trước.

## 🛡️ Nếu gặp sự cố giữa demo
- **Model chèn chữ Trung vào câu tiếng Việt** — đã có bộ lọc chặn ở tầng code, nhưng nếu vẫn lọt thì
  cứ nói thẳng: *"model nền là Qwen, thỉnh thoảng rò token tiếng Trung; em chặn bằng bộ lọc hậu xử lý,
  đây là giới hạn của model chứ không phải logic hệ thống."* Thành thật ăn điểm hơn là lờ đi.
- **Aidbox 502 / mạng chết** → chuyển sang screenshot dự phòng, kể tiếp bằng lời, đừng ngồi F5.
- **Agent gọi sai tool / hỏi lại lòng vòng** → gõ lại đúng câu trong kịch bản. Các câu này đã test,
  đừng ứng biến câu mới lúc đang bị chấm.
