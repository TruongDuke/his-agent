# Q&A PHẢN BIỆN MỞ RỘNG — HIS Agent

> Các câu hỏi KHÓ / GÀI về kỹ thuật, đánh giá, đạo đức, pháp lý mà hội đồng AI y tế hay hỏi.
> Đọc kèm `ON_TAP_DATN.md` (kiến trúc + 9 câu cơ bản).
>
> Nguyên tắc trả lời: **thành thật về hạn chế + biến điểm yếu thành hướng phát triển**.
> Hội đồng đánh giá cao người HIỂU giới hạn của mình, không thích người nói "cái gì cũng làm được".

---

## A. ĐẠO ĐỨC & PHÁP LÝ (khó nhất — chuẩn bị kỹ)

### A1. ⭐ Dữ liệu bệnh nhân có rời khỏi hệ thống không? Gửi đi đâu? (CÂU NGUY HIỂM NHẤT)
**Sự thật:** Có. Mỗi lượt hội thoại, hệ thống gửi cả hồ sơ bệnh nhân (lấy từ FHIR) cho LLM bên thứ ba
(hiện là Qwen/Alibaba hoặc Claude/Anthropic qua API) để LLM diễn giải.

**Cách trả lời (thành thật + có hướng xử lý):**
> "Đúng, trong bản demo này dữ liệu được gửi tới LLM qua API bên thứ ba — đây là **giới hạn em ý thức rõ**.
> Với triển khai thật trong bệnh viện, có 3 hướng khắc phục:
> (1) **Self-hosted LLM** — chạy mô hình mã nguồn mở (Llama, Qwen) ngay trong mạng nội bộ bệnh viện,
> dữ liệu không ra ngoài;
> (2) **Ẩn danh hoá (de-identification)** — bỏ tên/CCCD/BHYT trước khi gửi LLM, chỉ gửi chỉ số lâm sàng;
> (3) Dùng nhà cung cấp có cam kết **không lưu/không train trên dữ liệu** (zero-retention) và ký BAA.
> Kiến trúc của em đã dùng **OpenAI-compatible SDK** nên đổi sang LLM nội bộ chỉ cần đổi `base_url`,
> không phải viết lại."

**Điểm mạnh để nhấn:** việc đổi LLM rất dễ vì code dùng chuẩn OpenAI-compatible (`agent.py` chỉ đổi `base_url`/`_MODEL`).

### A2. Nếu AI tư vấn sai dẫn tới hậu quả cho bệnh nhân, ai chịu trách nhiệm?
> "Hệ thống được thiết kế là **công cụ hỗ trợ quyết định (CDS)**, KHÔNG thay bác sĩ. Mọi kết luận lâm sàng
> đều có disclaimer 'không thay thế khám lâm sàng', và **bác sĩ là người ra quyết định cuối cùng**.
> Các tool sàng lọc chỉ gợi ý + dẫn nguồn phác đồ; chẩn đoán xác định vẫn theo quy trình y tế chuẩn.
> Về pháp lý, trách nhiệm thuộc về bác sĩ/cơ sở y tế như mọi công cụ hỗ trợ khác."

### A3. Hệ thống có tuân thủ quy định bảo vệ dữ liệu cá nhân không?
> "Em tham chiếu **Nghị định 13/2023/NĐ-CP** về bảo vệ dữ liệu cá nhân. Hiện đã có: phân quyền theo vai trò,
> mật khẩu hash bcrypt, bệnh nhân chỉ xem được dữ liệu của chính mình (ép ở tầng code).
> Còn thiếu (hướng phát triển): mã hoá dữ liệu khi lưu, nhật ký truy cập (audit log), và xử lý vấn đề
> gửi dữ liệu ra LLM (câu A1)."

### A4. AI có được phép 'chẩn đoán' bệnh không? (Luật Khám bệnh, chữa bệnh)
> "Không, và hệ thống KHÔNG chẩn đoán. Các tool là **sàng lọc (screening)** và **gợi ý** — ví dụ
> `dengue_*` chỉ ước lượng khả năng và khuyến nghị xét nghiệm, ghi rõ 'chẩn đoán xác định chỉ qua NS1/IgM/PCR'.
> Việc chẩn đoán và kê đơn vẫn do bác sĩ có chứng chỉ hành nghề thực hiện."

### A5. Bệnh nhân có biết và đồng ý rằng họ đang nói chuyện với AI không?
> "Giao diện thể hiện rõ đây là trợ lý AI. Hướng phát triển: thêm bước **đồng ý (informed consent)** rõ ràng
> khi bắt đầu, và thông báo dữ liệu được xử lý thế nào."

---

## B. KỸ THUẬT

### B1. LLM bị 'ảo giác' (hallucination) — làm sao tin được số liệu?
> "Em chống bịa bằng **grounding**: LLM không tự sinh số liệu mà phải GỌI TOOL lấy dữ liệu thật
> (hồ sơ qua FHIR, số ca qua HCDC, thuốc qua NCBI). Với tra thuốc, `note_for_llm` còn cấm LLM tự thêm
> liều bằng kiến thức nền và bắt trích nguồn [n]. Mọi câu trả lời đều dẫn nguồn bấm được để kiểm chứng."

### B2. Tham số LLM truyền vào tool có thể sai/bịa — xử lý thế nào?
> "Em có nhiều lớp phòng thủ: (1) lọc tham số hợp lệ (vd `& _VALID_SYMPTOMS` bỏ triệu chứng lạ);
> (2) chặn tool ngoài danh sách vai trò (`agent.py`); (3) ép `patient_id` của người đăng nhập, không tin
> ID do LLM đưa; (4) tool tự kiểm tra đầu vào bắt buộc (vd thiếu `plt` thì báo lỗi)."

### B3. Prompt injection / jailbreak — người dùng dụ LLM lộ dữ liệu người khác thì sao?
> "Phòng thủ quan trọng nhất nằm ở **tầng code, không phải prompt**: dù LLM bị dụ gọi tool với ID người khác,
> code vẫn ghi đè `args['patient_id'] = patient_id` của người đang đăng nhập (`agent.py:412`).
> Prompt chỉ là lớp nhắc; code mới là lớp chặn cứng."

### B4. Chi phí vận hành (gọi API LLM tốn tiền) và độ trễ?
> "Mỗi lượt hội thoại gọi LLM vài lần (theo số tool). Em tối ưu: (1) cắt bớt lịch sử cũ (`_trim_history`)
> để giảm token; (2) cache embedding RAG và số ca HCDC để khỏi tính/cào lại; (3) pre-load model RAG lúc
> khởi động. Chi phí phụ thuộc nhà cung cấp; bản demo dùng model nhỏ (haiku/qwen-plus) cho rẻ và nhanh.
> Triển khai thật có thể dùng LLM nội bộ để cắt chi phí biến đổi."

### B5. Vì sao chọn kiến trúc Agent + tool-calling thay vì hỏi-đáp LLM thuần?
> "Vì bài toán cần **thao tác thật** trên hệ thống bệnh viện (đặt lịch, kê đơn, tra hồ sơ), không chỉ trả lời
> kiến thức. Agent + tool-calling cho phép LLM gọi code thật, dữ liệu chính xác, kiểm soát được và dẫn nguồn —
> tránh LLM bịa."

### B6. Hệ thống chịu được bao nhiêu người dùng đồng thời? Khi LLM provider sập thì sao?
> "Đây là bản demo, chưa tối ưu cho tải cao. Server FastAPI async xử lý được nhiều request, nhưng nút thắt là
> tốc độ LLM bên ngoài. Khi provider lỗi, hệ thống có timeout (60s) và trả thông báo lỗi thay vì treo.
> Hướng phát triển: hàng đợi, nhiều provider dự phòng, hoặc LLM nội bộ."

### B7. Vì sao dùng OpenAI-compatible SDK mà không phải SDK riêng của từng hãng?
> "Để **không khoá cứng vào một nhà cung cấp**. Cùng một đoạn code chạy được với Claude, Qwen, OpenRouter,
> hay LLM nội bộ — chỉ đổi `base_url` và `_MODEL`. Linh hoạt và dễ chuyển đổi (liên quan trực tiếp tới câu A1)."

---

## C. ĐÁNH GIÁ / KIỂM THỬ

### C1. Em đánh giá độ chính xác của hệ thống thế nào? Metric gì?
> "Em đánh giá theo từng phần:
> - **Sàng lọc SXHD**: chạy các kịch bản chuẩn (test case trong `__main__` của tool) và đối chiếu kết quả với
>   phân độ của QĐ 2760 — vì là rule-based nên có thể kiểm tra khớp phác đồ.
> - **Phân quyền**: test bệnh nhân không truy cập được dữ liệu người khác.
> - **Trích dẫn**: đối chiếu từng nguồn trả về (ca cefuroxime).
> Hạn chế: chưa có bộ dữ liệu gắn nhãn lớn để tính accuracy/precision/recall toàn hệ thống — đây là hướng phát triển."

### C2. Model ML phân tích CBC: dataset bao nhiêu mẫu? accuracy? (xem bẫy ML)
> "Em train model tham khảo (Random Forest/Gradient Boosting) trên bộ Dengue Hematological ~1500 mẫu, dùng
> cross-validation. NHƯNG hệ thống chạy thật dùng **rule-based theo QĐ 2760**, không dùng model ML — vì trong
> y tế khả năng **giải thích được** (mỗi kết luận chỉ rõ ngưỡng/trang phác đồ) quan trọng hơn độ chính xác của
> mô hình hộp đen. Bác sĩ cần biết VÌ SAO máy kết luận để chịu trách nhiệm."
> ⚠ TUYỆT ĐỐI không nói cụt "em dùng Machine Learning để chẩn đoán" → mở code thấy if-else là mâu thuẫn.

### C3. Làm sao biết RAG gợi ý khoa đúng?
> "Em kiểm thử với các mô tả triệu chứng điển hình và đối chiếu khoa gợi ý. Cơ chế weighted-voting cộng điểm
> cosine qua nhiều câu mô tả nên ổn định hơn so 1-1. Hạn chế: chưa đo trên tập lớn có nhãn chuẩn."

---

## D. TÍNH MỚI / ĐÓNG GÓP

### D1. Khác gì ChatGPT? Tại sao không bảo bệnh nhân tự dùng ChatGPT?
> "ChatGPT trả lời kiến thức chung và CÓ THỂ bịa. Hệ thống của em: (1) thao tác THẬT trên hồ sơ bệnh viện
> chuẩn FHIR (đặt lịch, kê đơn, tra xét nghiệm); (2) dữ liệu thật + dẫn nguồn, không bịa; (3) theo phác đồ
> Bộ Y tế Việt Nam; (4) phân quyền bảo mật. ChatGPT không làm được những việc vận hành này."

### D2. Đóng góp mới/khoa học của đề tài là gì?
> "Đóng góp chính là **tích hợp LLM-agent vào quy trình HIS thật theo chuẩn FHIR**, với cơ chế an toàn lâm sàng
> (chặn dị ứng 4 lớp, sàng lọc theo phác đồ BYT) và **bắt buộc dẫn nguồn** để chống bịa. Đây là hướng áp dụng
> kỹ thuật agent vào ngữ cảnh y tế Việt Nam (tiếng Việt, văn bản BYT)."

### D3. So với các sản phẩm có sẵn (vd MedDeep AI)?
> "MedDeep tra cứu cho bác sĩ, không tích hợp HIS. Hệ thống của em phục vụ CẢ bệnh nhân lẫn bác sĩ và vận hành
> quy trình bệnh viện (FHIR), nguồn tri thức gắn văn bản BYT (QĐ 2760, 3192...) + WHO + HCDC + NCBI."

---

## E. TRIỂN KHAI THỰC TẾ

### E1. Đã thử trên bệnh viện thật chưa?
> "Chưa — đây là đồ án demo với dữ liệu mô phỏng trên Aidbox. Nhưng vì dùng chuẩn FHIR R5 nên về nguyên tắc có
> thể kết nối HIS thật hỗ trợ FHIR. Trước khi triển khai cần giải quyết: bảo mật dữ liệu (A1, A3), kiểm thử lâm
> sàng có giám sát, và phê duyệt của hội đồng y đức."

### E2. Hạn chế lớn nhất của đề tài?
> "(1) Dữ liệu gửi ra LLM bên thứ ba (cần LLM nội bộ); (2) Phụ thuộc chất lượng LLM — model nhỏ có thể chọn
> sai tool; (3) Cào web HCDC mong manh khi họ đổi giao diện; (4) Nguồn thuốc tiếng Anh, chưa theo Dược thư VN;
> (5) Chưa đánh giá định lượng trên tập dữ liệu lớn có nhãn. Tất cả đều có hướng khắc phục."

### E3. Hướng phát triển tiếp theo?
> "LLM nội bộ + ẩn danh hoá dữ liệu; bổ sung Dược thư Quốc gia VN; audit log + mã hoá; đánh giá định lượng trên
> tập lâm sàng có nhãn; mở rộng nguồn dịch tễ ra cả nước; thử nghiệm có giám sát tại cơ sở y tế."

---

## F. 5 CÂU SỐNG CÒN — HỌC THUỘC

1. **A1** — Dữ liệu ra LLom ngoài → "ý thức rõ, hướng khắc phục: LLM nội bộ / ẩn danh hoá; đổi LLM chỉ cần đổi base_url."
2. **A2** — Trách nhiệm → "công cụ hỗ trợ (CDS), bác sĩ quyết định cuối."
3. **B1** — Chống ảo giác → "grounding: tool lấy dữ liệu thật + bắt dẫn nguồn."
4. **C2** — Thuật toán SXHD → "rule-based theo QĐ 2760 vì giải thích được (KHÔNG nói 'em dùng ML')."
5. **B3** — Jailbreak → "chặn ở tầng code, ép patient_id, không chỉ prompt."
