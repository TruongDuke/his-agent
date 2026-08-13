# HIS Agent — Tài liệu bán hàng (Sales Brief)

> Tài liệu tổng hợp cho team Sale: đọc bản này là đủ hiểu sản phẩm để dựng slide và trả lời khách hàng.
> Đối tượng khách: lãnh đạo bệnh viện, phòng CNTT/HIS, đối tác công nghệ y tế.

---

## 1. Một câu định vị (elevator pitch)

**HIS Agent là trợ lý AI hội thoại tiếng Việt cho bệnh viện, thao tác THẬT trên hồ sơ bệnh nhân theo chuẩn FHIR R5 — không phải chatbot hỏi-đáp, mà là một "nhân viên số" biết đặt lịch, tra hồ sơ, hỗ trợ bác sĩ ra quyết định và tự động hoá quy trình khám từ đầu đến cuối.**

Câu chốt bán hàng:
> *"HIS hiện tại quản lý dữ liệu — HIS Agent giúp con người ra quyết định trên dữ liệu đó."*

---

## 2. Vấn đề khách hàng đang gặp (nỗi đau)

- 📞 **Đặt lịch thủ công** — bệnh nhân phải gọi điện, xếp hàng; tổng đài & quầy tiếp nhận quá tải.
- ❓ **Định tuyến sai khoa** — bệnh nhân không biết khám khoa nào, đi lòng vòng.
- 🦟 **Sốt xuất huyết nhập viện muộn** — hàng trăm nghìn ca/năm ở VN, nhiều ca phát hiện trễ.
- 💊 **Rủi ro kê đơn** — nguy cơ kê thuốc gây dị ứng, bỏ sót cảnh báo lâm sàng.
- 🧊 **Tri thức "đóng băng"** — công cụ AI thông thường chỉ biết tới thời điểm huấn luyện, không cập nhật.

---

## 3. Ba nhóm giá trị cốt lõi

### Giá trị 1 — Bệnh nhân tự phục vụ (*khỏi gọi điện, khỏi xếp hàng*)
- Kể triệu chứng → AI phân loại mức độ khẩn cấp (triage).
- Gợi ý đúng khoa trong 18 chuyên khoa bằng RAG.
- Đặt / huỷ / xem lịch ngay trong hội thoại; tự gửi email xác nhận.
- **Lợi ích:** giảm tải tổng đài & quầy tiếp nhận, tăng trải nghiệm bệnh nhân.

### Giá trị 2 — Sàng lọc Sốt xuất huyết (*phát hiện sớm, đúng phác đồ*)
- Theo **Quyết định 2760/QĐ-BYT 2023**.
- Sàng lọc từ **triệu chứng** (qua hội thoại) và từ **ảnh phiếu xét nghiệm CBC** (đọc số tự động).
- **Lợi ích:** phát hiện sớm, giảm ca nhập viện muộn, chuẩn hoá theo Bộ Y tế.

### Giá trị 3 — Bác sĩ & an toàn kê đơn / Hỗ trợ quyết định lâm sàng (CDS)
- Tra hồ sơ, kết quả xét nghiệm bằng ngôn ngữ tự nhiên.
- Ghi sinh hiệu → tự cảnh báo bất thường (**BYT 3192**, thang điểm **NEWS2**).
- Kê đơn có kiểm tra dị ứng: đối chiếu danh mục ~50 thuốc, cảnh báo **dị ứng chéo**, 3 mức cảnh báo.
- Hoàn tất khám → tự gửi email tóm tắt (chẩn đoán + đơn thuốc) cho bệnh nhân.
- **Lợi ích:** giảm sai sót, tăng an toàn người bệnh, tiết kiệm thời gian bác sĩ.

---

## 4. Danh mục chức năng đầy đủ (34 công cụ)

| Nhóm nghiệp vụ | Chức năng |
|---|---|
| 🧭 Phân loại & định tuyến | Triage mức độ khẩn cấp · Gợi ý khoa (RAG, 18 khoa) · Liệt kê khoa · Chuyển thẳng đăng ký |
| 📅 Đặt lịch (bệnh nhân) | Xem slot trống / slot gần nhất · Đặt · Huỷ · Xem lịch hẹn · Email xác nhận |
| 🗂️ Quản lý lịch (bác sĩ) | Xem lịch chờ duyệt · Xác nhận / Từ chối · Lịch làm việc bác sĩ · Gợi ý bác sĩ |
| 🆔 Định danh bệnh nhân | Đăng ký mới · Tìm kiếm · Xác thực |
| 📋 Tra cứu hồ sơ (BN chỉ xem của mình) | Tiền sử khám · Sinh hiệu / quan sát · Chẩn đoán · Dị ứng · Đơn thuốc · Kết quả CBC |
| 🩺 Hỗ trợ quyết định lâm sàng (bác sĩ) | Ghi sinh hiệu + cảnh báo (BYT 3192/NEWS2) · Ghi dị ứng · Kê đơn chặn dị ứng · Tạo & đọc CBC |
| ✉️ Tổng kết khám | Gửi email tóm tắt khám tự động |
| 🦟 Sàng lọc Sốt xuất huyết | Từ triệu chứng · Từ ảnh phiếu CBC (theo QĐ 2760) |
| 🌐 Tri thức sống (dẫn nguồn) | Thông tin thuốc (NCBI/StatPearls) · Số ca dịch theo tuần (HCDC) |

**18 chuyên khoa:** Tim mạch, Nội tiết, Tai Mũi Họng, Thần kinh, Tiêu hoá, Cơ Xương Khớp, Da liễu, Sản Phụ khoa, Nhi, Mắt, Thận-Tiết niệu, Nội tổng quát, Ngoại, Răng Hàm Mặt, Hô hấp, Chấn thương Chỉnh hình, Cấp cứu.

**Danh mục thuốc (~50):** kháng sinh (beta-lactam, macrolide, quinolon…), giảm đau/NSAID, tim mạch–huyết áp, tiểu đường, tiêu hoá, hô hấp, kháng histamine, vitamin, chống đông… — có kiểm tra dị ứng chéo theo nhóm.

---

## 5. Quy trình khám bệnh — đầu đến cuối

1. **Đặt lịch (Bệnh nhân):** mô tả triệu chứng → triage + gợi ý khoa (RAG) → chọn lịch → *chờ duyệt*.
2. **Duyệt lịch (Bác sĩ):** xác nhận / từ chối → 📧 email xác nhận cho bệnh nhân.
3. **Khám (Bác sĩ):** tra hồ sơ → ghi sinh hiệu (cảnh báo CDS) → phân tích CBC → kê đơn (chặn dị ứng).
4. **Hoàn tất khám:** lưu hồ sơ FHIR (chẩn đoán + đơn thuốc) → 📧 email tóm tắt cho bệnh nhân.

---

## 6. Nền tảng công nghệ (tóm tắt để Sale nắm)

- **Backend:** FastAPI (Python), phản hồi thời gian thực qua **SSE streaming**.
- **Giao diện:** web **React + TypeScript**; xác thực **2 lớp** cho cổng bệnh nhân.
- **Lõi AI:** agent tool-calling loop — LLM gọi 34 công cụ, phân quyền theo vai trò.
- **Dữ liệu:** chuẩn **FHIR R5** (qua Aidbox) cho hồ sơ y tế; 2 kiểu RAG (vector gợi ý khoa + truy hồi API tra thuốc).
- **Tích hợp:** hỗ trợ giao thức **A2A** để hệ thống ngoài gọi vào như một agent chuẩn.

---

## 7. Tích hợp — KHÔNG xâm lấn (điểm bán hàng lớn)

- Cắm vào **HIS/EMR sẵn có** của viện qua **chuẩn mở FHIR R5** — nói cùng ngôn ngữ dữ liệu.
- Giao thức **A2A**: hệ thống khác (cổng bệnh viện, nền tảng điều phối…) gọi HIS Agent như một agent chuẩn, không cần hard-code API.
- **Không thay hệ thống hiện có, không khoá vendor.** Bổ sung lớp "ra quyết định" lên trên hạ tầng dữ liệu đang chạy.
- Triển khai theo từng phần → rủi ro thấp.

---

## 8. Bảo mật & Tuân thủ (điều bệnh viện lo nhất)

- 🏥 **Triển khai on-prem** — dữ liệu bệnh nhân ở lại trong viện.
- 🔐 **Phân quyền theo vai trò** — bệnh nhân chỉ xem hồ sơ của chính mình (đã kiểm chứng).
- 🧱 **Kiến trúc tách "agent dữ liệu"** — cô lập khóa truy cập FHIR; nếu lớp AI bị tấn công cũng không lấy được dữ liệu ngoài phạm vi; tạo **một cửa audit** ghi lại mọi truy cập.
- 🚪 **A2A làm ranh giới** — hệ thống ngoài chỉ nhận câu trả lời đã lọc, **không chạm dữ liệu thô**.
- ⚖️ **Tuân thủ chuyên môn:** QĐ **2760** (SXH), **3192** (sinh hiệu), **1165**/QĐ-BYT, khuyến cáo **WHO**.

---

## 9. Tri thức sống — không "đóng băng"

- LLM thường chỉ biết tới ngày huấn luyện. HIS Agent **truy hồi nguồn sống khi được hỏi**:
  - 💊 **NCBI** (StatPearls / PubMed) — thông tin thuốc.
  - 🦟 **HCDC** — số ca dịch bệnh theo tuần.
  - 🏥 **FHIR** — hồ sơ bệnh nhân thật.
- Mọi câu trả lời **dẫn nguồn**: thẻ nguồn + chip **[n]** bấm được → kiểm chứng tận gốc.

---

## 10. Độ tin cậy (đã kiểm chứng)

- ✅ Sàng lọc SXHD khớp phác đồ trên các kịch bản chuẩn.
- ✅ Phân quyền: bệnh nhân không truy cập được dữ liệu người khác.
- ✅ Kiểm chứng trích dẫn: đối chiếu từng nguồn.
- ✅ Phản hồi thời gian thực qua SSE streaming.

---

## 11. Vì sao chọn HIS Agent (điểm khác biệt)

| | Chatbot y tế thường | Công cụ tra cứu cho bác sĩ | **HIS Agent** |
|---|:---:|:---:|:---:|
| Hội thoại tiếng Việt | ✅ | một phần | ✅ |
| Thao tác thật trên HIS (FHIR) | ❌ | ❌ | ✅ |
| Đặt lịch · kê đơn · hồ sơ | ❌ | ❌ | ✅ |
| Phục vụ cả bệnh nhân & bác sĩ | một phía | bác sĩ | ✅ cả hai |
| Dẫn nguồn kiểm chứng được | hiếm | một phần | ✅ |
| Tuân thủ QĐ-BYT | ❌ | một phần | ✅ |

> *Không chỉ "trả lời" — HIS Agent "vận hành" một phần quy trình bệnh viện.*

---

## 12. Mô hình triển khai

- **On-prem / hybrid** — phù hợp yêu cầu dữ liệu tại chỗ.
- **Tích hợp qua FHIR sẵn có** — không đập đi làm lại.
- **Lộ trình pilot:** 1 khoa / 1 luồng khám → đánh giá → mở rộng toàn viện.

---

## 13. Câu hỏi thường gặp (FAQ) — dành cho Sale

**H: Dữ liệu bệnh nhân có ra khỏi bệnh viện không?**
Đ: FHIR/hồ sơ triển khai on-prem, ở lại trong viện. *Lưu ý trung thực:* hiện phần AI (LLM) dùng dịch vụ đám mây, nên câu hỏi + phần dữ liệu đã chắt lọc được gửi lên LLM. **Nếu khách yêu cầu dữ liệu tuyệt đối không ra ngoài, có tuỳ chọn chạy LLM nội bộ (cần hạ tầng GPU).** → Đừng hứa "100% offline" ở cấu hình mặc định.

**H: Có phải thay hệ thống HIS hiện tại không?**
Đ: Không. Tích hợp qua chuẩn FHIR + A2A, bổ sung lên trên hệ thống đang chạy.

**H: Bệnh nhân có xem được hồ sơ người khác không?**
Đ: Không. Phân quyền theo vai trò, bệnh nhân chỉ xem hồ sơ của chính mình sau khi đăng nhập.

**H: AI có bịa thông tin không?**
Đ: Câu trả lời dẫn nguồn (FHIR/NCBI/HCDC) với chip bấm được để kiểm chứng; thao tác y tế dựa trên dữ liệu thật, không phải "trí nhớ" LLM.

**H: Có đúng quy định Bộ Y tế không?**
Đ: Sàng lọc/cảnh báo theo QĐ 2760, 3192, 1165/QĐ-BYT và khuyến cáo WHO.

**H: Nếu AI bị tấn công (prompt injection) thì sao?**
Đ: Kiến trúc tách agent dữ liệu + phân quyền phía server: lớp AI không giữ khóa truy cập, chỉ gọi được các thao tác đã whitelist trong phạm vi cho phép.

---

## 14. Câu chốt gợi ý (talking points)

- *"HIS quản lý dữ liệu — HIS Agent giúp ra quyết định."*
- *"Không thay hệ thống của quý viện — chúng tôi cắm thêm một trợ lý biết việc."*
- *"Dữ liệu ở lại trong viện; AI chỉ mượn câu hỏi, không mượn hồ sơ."*
- *"Bắt đầu nhỏ: chạy thử 1 khoa, thấy giá trị rồi mở rộng."*

---

## 15. Thông tin cần bổ sung trước khi gặp khách (team điền)

- [ ] **Giá / gói dịch vụ** theo quy mô viện.
- [ ] **Thời gian triển khai** & yêu cầu hạ tầng (server, GPU nếu LLM nội bộ).
- [ ] **Khách hàng tham chiếu / case study / demo** (nếu có).
- [ ] **Thông tin liên hệ** cho slide CTA.
- [ ] Xác nhận cấu hình LLM chào khách: **đám mây** hay **nội bộ** (ảnh hưởng cam kết bảo mật).
