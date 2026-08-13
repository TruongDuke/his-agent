# KỊCH BẢN DIỄN — Flow A: Đặt lịch khám qua hội thoại

> Mục tiêu: vừa trả lời mạch lạc, vừa mở đúng file/dòng code. Mỗi bước có **[NÓI]** và **[MỞ/CHỈ]**.
> Mở sẵn 4 tab trước khi vào: `api/routes/chat.py`, `agent.py`, `tools/fhir/fhir_create_appointment.py`, sơ đồ Flow A trong thesis.

---

## MỞ ĐẦU (khung 20 giây — nói trước khi đụng code)

**[NÓI]**
> "Em xin trình bày Flow A — luồng bệnh nhân đặt lịch khám bằng hội thoại tự nhiên. Toàn hệ thống chia 3 lớp: **FastAPI** nhận request và xác thực, **Agent** chạy vòng lặp gọi công cụ, **LLM** đóng vai bộ não quyết định. Em sẽ đi theo sơ đồ tuần tự và chỉ ra từng phần nằm ở đâu trong mã nguồn."

**[MỞ/CHỈ]** Sơ đồ Flow A trong thesis (Hình tuần tự Flow A).

---

## BƯỚC 1 — Request vào, xác thực (FastAPI)

**[NÓI]**
> "Khi bệnh nhân gõ 'đặt lịch khám', frontend React gọi `POST /chat/stream`, vào endpoint này. Hai việc quan trọng nhất ở đây: nạp lịch sử hội thoại, và **xác thực bệnh nhân từ token** để ra `patient_id`. Em nhấn mạnh: ID này lấy từ token đăng nhập, **không phải do LLM tự bịa** — đây là nền của cơ chế cô lập dữ liệu."

**[MỞ/CHỈ]** `api/routes/chat.py`
- dòng **124** — `chat_stream_endpoint`
- dòng **135** — `_load_session(...)` (nạp lịch sử)
- dòng **136** — `_resolve_patient(...)` (xác thực ra patient_id)

---

## BƯỚC 2 — Vào Agent, dựng system prompt theo vai trò

**[NÓI]**
> "Endpoint gọi sang `chat_stream` trong agent. Đầu hàm, hệ thống dựng system prompt theo vai trò. Vì là bệnh nhân đã đăng nhập, nó chèn một khối ưu tiên ép agent dùng đúng `patient_id` và **cấm xem hồ sơ người khác** — đây là lớp bảo vệ thứ nhất, ở tầng prompt."

**[MỞ/CHỈ]** `agent.py`
- dòng **142** (`chat.py`) — `chat_stream(...)` được gọi trong thread `producer`
- dòng **328–350** — chọn prompt theo role + khối "BỆNH NHÂN ĐÃ ĐĂNG NHẬP"
- dòng **364** — thêm câu người dùng vào history

---

## BƯỚC 3 — TRÁI TIM: vòng lặp tool-calling

**[NÓI]** (đây là phần ăn điểm nhất — nói chậm)
> "Đây là phần cốt lõi: vòng lặp `while True`. Mỗi vòng, agent gửi cho LLM ba thứ: system prompt, lịch sử hội thoại, và **danh sách công cụ mà vai trò này được phép dùng**. Rồi LLM trả về một trong hai: hoặc 'tôi muốn gọi công cụ X', hoặc câu trả lời cuối. Điểm mấu chốt em muốn nhấn mạnh: **LLM chỉ quyết định, Agent mới là bên thực thi** — LLM không tự chạm vào dữ liệu."

**[MỞ/CHỈ]** `agent.py`
- dòng **362** — `_get_tools_for_role(role)` (lọc tool theo quyền)
- dòng **109** — bảng `_TOOLS_BY_ROLE` (chỉ vào danh sách của `"patient"`)
- dòng **368** — `while True:` ← **dừng lại, nói "đây là vòng lặp"**
- dòng **369–374** — gọi LLM
- dòng **378** — `if choice.finish_reason == "tool_calls"` (LLM đòi gọi tool)

---

## BƯỚC 4 — Agent thực thi tool (3 lần lặp)

**[NÓI]**
> "Khi LLM đòi gọi tool, agent duyệt từng yêu cầu và thực thi qua `_execute_tool`, hàm này gọi `run()` của module tool tương ứng rồi nhét kết quả lại vào lịch sử với vai trò 'tool'. Sau đó quay lại đầu vòng lặp. Trong Flow A, vòng lặp chạy đúng như sơ đồ: lần 1 gọi **gợi ý khoa**, lần 2 gọi **tìm slot trống**, lần 3 gọi **đặt lịch**."

**[MỞ/CHỈ]** `agent.py`
- dòng **389** — `for tc in msg.tool_calls`
- dòng **412** — `args["patient_id"] = patient_id` ← **lớp bảo vệ thứ 2 (tầng code), chỉ vào dòng này và nói "kể cả LLM có bị dụ, ID vẫn bị ép cứng ở đây"**
- dòng **424** — `_execute_tool(...)` (thực thi thật)
- dòng **426** — nhét kết quả vào history → quay lại vòng lặp

---

## BƯỚC 5 — Tool đặt lịch làm việc thật với FHIR

**[NÓI]**
> "Em mở tool đặt lịch để thấy nó thao tác thật trên dữ liệu chuẩn FHIR, không phải LLM tưởng tượng. Tool làm 6 bước: tìm slot khớp khoa-ngày-giờ, kiểm tra slot còn trống, lấy bác sĩ từ Schedule, xác minh bệnh nhân, **tạo Appointment ở trạng thái 'proposed' — tức chờ bác sĩ duyệt**, rồi đánh dấu slot bận. Em nhấn mạnh trạng thái 'proposed': hệ thống **không tự xác nhận**, bác sĩ là người quyết định cuối — human-in-the-loop."

**[MỞ/CHỈ]** `tools/fhir/fhir_create_appointment.py`
- dòng **70** — `run(args)`
- dòng **98** — `_resolve_slot_by_time` (tự tìm slot)
- dòng **145–157** — tạo Appointment, chỉ vào `"status": "proposed"`
- dòng **176–178** — đánh dấu slot `busy`

---

## BƯỚC 6 — Trả lời stream về (SSE)

**[NÓI]**
> "Khi LLM thấy đã đủ thông tin, nó không gọi tool nữa, rơi vào nhánh trả lời cuối. Agent bật chế độ stream, đẩy từng đoạn chữ ra ngoài bằng Server-Sent Events, nên người dùng thấy câu trả lời chạy dần theo thời gian thực thay vì chờ trọn. Cuối cùng lịch sử hội thoại được lưu lại."

**[MỞ/CHỈ]**
- `agent.py` dòng **436** — nhánh `else` (phản hồi cuối)
- `agent.py` dòng **439–445** — gọi LLM ở chế độ `stream=True`
- `agent.py` dòng **459** — `yield sse({"type": "text", ...})`
- `api/routes/chat.py` dòng **161–179** — `generate()` + `StreamingResponse`
- `api/routes/chat.py` dòng **172** — `_save_session`

---

## CÂU CHỐT (nói khi kết thúc)
> "Tóm lại, Flow A đi qua đúng một vòng lặp tool-calling lặp 4 lần: ba lần gọi công cụ và một lần trả lời. LLM điều phối, công cụ Python thao tác thật trên FHIR, dữ liệu bệnh nhân được ép đúng ID ở tầng code, và lịch đặt ra phải chờ bác sĩ duyệt."

---

## XỬ LÝ CÂU HỎI BẺ (chuẩn bị sẵn)

**Hỏi: "Vòng lặp nằm ở đâu? Sơ đồ vẽ các mũi tên rời rạc mà?"**
> "Sơ đồ là bản đơn giản hóa cho dễ nhìn. Thực tế mọi lần gọi tool đều đi qua cùng một vòng `while True` ở agent.py dòng 368, lặp lại 4 lần." → chỉ dòng 368.

**Hỏi: "Làm sao bệnh nhân A không xem được hồ sơ bệnh nhân B?"**
> "Hai lớp. Lớp prompt ở dòng 345 cấm thao tác trên ID khác. Lớp code ở dòng 412 ép `args['patient_id']` bằng đúng ID đã đăng nhập, kể cả LLM có gọi sai." → chỉ 2 dòng.

**Hỏi: "Nếu LLM gọi một tool không được phép thì sao?"**
> "Có chặn ở dòng 391: tool ngoài danh sách của vai trò sẽ bị trả lỗi, không được thực thi." → chỉ dòng 388–394.

**Hỏi: "slot_id ở đâu ra, sơ đồ ghi truyền slot_id?"**
> "Cách gọi chuẩn là truyền khoa + ngày + giờ, tool tự tìm slot trong Aidbox; slot_id chỉ là tùy chọn." → chỉ mô tả tool dòng 8–11 + hàm `_resolve_slot_by_time` dòng 32.

**Hỏi: "Đặt xong là có lịch luôn à?"**
> "Không. Lịch tạo ở trạng thái 'proposed', phải bác sĩ duyệt mới thành 'booked' và mới gửi email xác nhận." → chỉ dòng 145 (`"status": "proposed"`).
