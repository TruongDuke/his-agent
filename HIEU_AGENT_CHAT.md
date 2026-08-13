# HIỂU TƯỜNG TẬN: `agent.py` & `api/routes/chat.py`

> Tài liệu ôn phản biện. Mô hình tư duy: **`chat.py` là lễ tân** (nhận khách, kiểm tra giấy tờ, ghi sổ), **`agent.py` là bộ não** (suy nghĩ, quyết định, làm việc). Lễ tân không suy nghĩ; bộ não không tiếp khách trực tiếp.

---

## MỤC LỤC
1. [Đường đi của một request](#1)
2. [chat.py — lớp web](#2)
3. [agent.py — bộ não](#3)
4. [ĐÀO SÂU 1 — Vòng lặp tool-calling (trái tim)](#4)
5. [ĐÀO SÂU 2 — Producer–Consumer & SSE streaming](#5)
6. [ĐÀO SÂU 3 — Tính năng chủ động (`__init__`)](#6)
7. [ĐÀO SÂU 4 — `_find_last_slot_id`](#7)
8. [3 dòng code phải thuộc](#8)
9. [Ngân hàng câu hỏi bẻ + trả lời](#9)

---

<a name="1"></a>
## 1. ĐƯỜNG ĐI CỦA MỘT REQUEST
```
Trình duyệt (React)
   │ POST /chat/stream
   ▼
chat.py  → xác thực token ra patient_id → nạp history → gọi agent trong thread riêng → đẩy SSE về
   │
   ▼
agent.py → nạp tool động → lọc tool theo quyền → VÒNG LẶP while:
            LLM quyết định (gọi tool? / trả lời?) → agent thực thi tool (ép patient_id, chặn tool cấm)
            → khi LLM ngừng gọi tool → stream câu trả lời
```

---

<a name="2"></a>
## 2. `api/routes/chat.py` — LỚP WEB (lễ tân)
Nhiệm vụ: nhận HTTP → xác thực → nạp lịch sử → gọi agent → trả kết quả. **Không có logic AI.**

### Khối 1 — Import (dòng 12)
`from agent import chat, chat_stream` — ranh giới giữa web và bộ não. `chat` trả 1 cục; `chat_stream` trả nhỏ giọt.

### Khối 2 — `_resolve_patient()` (dòng 30–37) ⭐ chốt bảo mật
Đổi `token` (chuỗi đăng nhập) → `patient_id` thật. Không token hợp lệ → rỗng (guest).
**Ý nghĩa:** `patient_id` sinh từ token đã xác thực, **không phải từ tin nhắn user, không phải từ LLM** → không mạo danh được.

### Khối 3 — `chat_stream_endpoint()` (dòng 124–179) ⭐ endpoint chính
- (a) Xác định session (126–134).
- (b) Nạp history + xác thực (135–136).
- (c) **Producer–consumer** (137–173) → xem [Đào sâu 2](#5).
- (d) Trả `StreamingResponse(media_type="text/event-stream")` (175–179) = **SSE**.

### Khối 4 — `chat_endpoint()` (dòng 40–121) — bản không stream
Cùng ý tưởng nhưng gọi `chat()`. Có thêm **tính năng chủ động `__init__`** (57–101) → xem [Đào sâu 3](#6).

### Khối 5 — endpoint quản lý session bác sĩ (182–268)
CRUD file JSON (liệt kê/đọc/xóa hội thoại). Không liên quan AI, lướt nhanh.

---

<a name="3"></a>
## 3. `agent.py` — BỘ NÃO
6 khối. Khối 5 (`chat_stream`) là trái tim.

### Khối 1 — Nạp tool động (32–106) ⭐ kiến trúc plugin
`_load_tool_modules` **quét thư mục** `tools/fhir`, `tools/dengue`...; file nào có `TOOL_NAME` + `run()` thì tự nạp (46). → Thêm tool mới = thả 1 file vào thư mục, **không sửa agent.py**.
- `_infer_param_schema` (51): đọc chữ đầu mô tả ("array"/"boolean"/"number") suy ra kiểu.
- `_build_openai_tools` (63): đổi `ARGS_SCHEMA` → format function-calling chuẩn OpenAI.
- `_execute_tool` (85): gọi `mod.run(args)` thật, bắt lỗi, trả JSON string.
- Dòng 105–106: chạy 1 lần lúc khởi động, **cache** lại.

### Khối 2 — Phân quyền tool theo vai trò (109–143) ⭐ bảo mật tầng 1
`_TOOLS_BY_ROLE`: mỗi role một danh sách tool (`"doctor": None` = full). `_get_tools_for_role` (139) lọc đúng bộ tool gửi cho LLM. → Bệnh nhân **về kỹ thuật không thể** gọi tool kê đơn vì nó không nằm trong danh sách.

### Khối 3 — Chọn nhà cung cấp LLM (145–169)
Ưu tiên Alibaba (Qwen) → OpenRouter → Anthropic. Cả 3 tương thích chuẩn OpenAI → đổi hãng chỉ sửa `api_key`+`base_url`+model. → Không vendor lock-in.

### Khối 4 — Hàm phụ trợ (172–306)
- `_TOOL_LABELS` (172): tên tool → câu tiếng Việt hiện trên UI.
- `_find_last_slot_id` (193): lục history lấy slot_id → xem [Đào sâu 4](#7).
- `_trim_history` (222): giữ 24 tin gần nhất + bỏ ảnh cũ → chống tràn context, tiết kiệm token.
- `_normalize_image`/`_ocr_image`/`_build_user_content` (237–306): OCR ảnh xét nghiệm thành text trước khi gửi (Flow CBC).

### Khối 5 — `chat_stream()` (309–473) ⭐⭐ TRÁI TIM
- (a) Dựng system prompt theo vai trò (322–360); BN đã đăng nhập → chèn khối cấm xem hồ sơ người khác (336–350).
- (b) Lọc tool + thêm tin user vào history (362–365).
- (c) **Vòng lặp tool-calling** (368–435) → xem [Đào sâu 1](#4).
- (d) Nhánh trả lời cuối: stream token (439–459), lọc `<think>` (456–470), lưu history (471).

### Khối 6 — `chat()` (476–564) — bản không stream
Gần như sao chép `chat_stream` nhưng `return reply, history` thay vì yield. Dùng cho `chat_endpoint`.
> Điểm yếu nên tự nhận: 2 hàm lặp code nhiều; refactor sẽ tách phần dựng prompt + vòng lặp ra hàm chung.

---

<a name="4"></a>
## 4. ĐÀO SÂU 1 — VÒNG LẶP TOOL-CALLING (dòng 368–435)

### Ý cốt lõi: LLM KHÔNG có trí nhớ — `history` mới là trí nhớ
Mỗi lần gọi LLM là một lần "mất trí nhớ hoàn toàn". Nó biết kết quả tool vì mỗi vòng code **gửi lại TOÀN BỘ history** (dòng 372). `history` lớn dần qua mỗi vòng. **Vòng lặp = bồi đắp history tới khi đủ để trả lời.**

### Vì sao `while True`
Không biết trước cần bao nhiêu tool (0 → nhiều). Lặp đến khi LLM ngừng đòi tool.
```python
while True:
    response = LLM(...)                    # hỏi LLM
    if finish_reason == "tool_calls":      # NHÁNH 1: còn đòi tool
        ... chạy tool, nhét kết quả vào history ...   # KHÔNG return → lặp lại
    else:                                  # NHÁNH 2: trả lời chữ
        ... stream ...; return             # ← lối ra DUY NHẤT
```

### Một vòng nhánh tool làm gì
1. **Lưu ý định gọi tool** vào history (379–387) — luật giao thức OpenAI: phải có tin "assistant đòi tool" (kèm `id`) trước khi đưa kết quả.
2. **Duyệt từng tool** (389) — LLM có thể đòi nhiều tool/vòng.
3. **Cổng kiểm soát trước khi chạy:**
   - Chặn tool sai quyền (391) → trả lỗi, `continue`.
   - Ép `patient_id` (406–412) → ghi đè ID bằng ID đã đăng nhập (bảo mật tầng 2).
   - Tiêm `practitioner_id`/`slot_id` cho bác sĩ (415–422).
4. **Chạy tool + lưu kết quả** (424–426) với `tool_call_id` khớp `id` ở bước 1.
5. **Báo status, quay lại đầu vòng** (435) — không return.

### Hình dung Flow A (4 vòng)
```
Vòng 1: [câu user]            → đòi gợi_ý_khoa  → history += khoa
Vòng 2: [user + khoa]         → đòi tìm_slot    → history += slot
Vòng 3: [user + khoa + slot]  → đòi đặt_lịch    → history += lịch
Vòng 4: [tất cả]              → đủ → TRẢ LỜI    → thoát
```
**Code không định trước thứ tự/số lượng tool — LLM tự suy luận. Đó chính là "agent".**

### Tool nối tiếp trong 1 lượt, hay dừng hỏi user?
- Trong **một lượt**: các tool **tự nối tiếp** qua vòng lặp, user chỉ nhận câu trả lời sau khi tool cuối xong.
- LLM **dừng giữa chừng để hỏi** (vd chọn khoa, xin email) khi thiếu thông tin → trả lời chữ → thoát → tool sau nằm ở **lượt hội thoại kế tiếp**.

---

<a name="5"></a>
## 5. ĐÀO SÂU 2 — PRODUCER–CONSUMER & SSE (chat.py 137–179)

### Vấn đề gốc: 2 thế giới
- **Agent** = generator **đồng bộ**, phải **chặn** chờ LLM vài giây (blocking).
- **FastAPI** = **event loop bất đồng bộ**, phục vụ nhiều user, **không được chặn** (chặn = cả server đứng hình).

### Ví dụ quán ăn
- Đầu bếp = agent (nấu chậm). Phục vụ = event loop (lo nhiều bàn). Quầy chuyển món = `queue`.
- **Sai:** phục vụ tự vào bếp đứng nấu → cả quán đứng hình (blocking event loop).
- **Đúng:** phục vụ đưa order vào **bếp riêng** (thread), đi lo bàn khác; bếp nấu xong đặt lên quầy; phục vụ ghé quầy bưng ra.

### Map code
| Quán ăn | Kỹ thuật | Dòng |
|---|---|---|
| Đầu bếp | Agent generator đồng bộ | `chat_stream()` agent.py |
| Bếp riêng | Thread (ThreadPoolExecutor) | `executor.submit(producer)` :163 |
| Quầy | asyncio.Queue | :138 |
| Đặt món qua quầy | cầu nối thread → loop | `call_soon_threadsafe` :152 |
| Phục vụ ghé quầy | await — nhường lượt khi rỗng | `await queue.get()` :166 |
| Chuông hết món | sentinel kết thúc | `None` :159 / :167 |
| Bưng ra cho khách | Server-Sent Events | `StreamingResponse` :175 |

### Cơ chế này phục vụ chức năng gì cho dự án
1. **Chat "chạy chữ" realtime** — chữ hiện dần, không chờ màn hình trống (`yield text` agent.py:459).
2. **Status chip** — "Đang gợi ý khoa...", "Đang đặt lịch..." (`yield tool_call` agent.py:397) → minh bạch, không tưởng treo.
3. **Phục vụ nhiều user song song** — event loop không nghẽn.

### SSE là gì
Streaming = ý tưởng (gửi nhỏ giọt). SSE = kỹ thuật cụ thể (server → client 1 chiều trên HTTP).
Dấu hiệu: `media_type="text/event-stream"` (:177) + mỗi mẩu `data: {...}\n\n` (`sse()` agent.py:319).
**Vì sao SSE không WebSocket:** chat chỉ cần 1 chiều (server đẩy); tin user gửi bằng request riêng. SSE nhẹ, chạy thẳng HTTP, tự reconnect. WebSocket 2 chiều là thừa.

---

<a name="6"></a>
## 6. ĐÀO SÂU 3 — TÍNH NĂNG CHỦ ĐỘNG (`__init__`, chat.py 54–101)

Khi mở phòng chat mới, frontend gửi tín hiệu `"__init__"` (sentinel) để agent **mở lời trước**.

- **Kích hoạt (57–58):** `is_init` VÀ `not history` → chỉ chạy 1 lần lúc phòng còn rỗng.
- **Nhánh bác sĩ (61–80):** gọi API lấy **kế hoạch theo dõi BN chưa làm** → nhét vào `extra_system`.
- **Nhánh bệnh nhân (81–99):** lấy **ClinicalImpression gần nhất có kế hoạch tái khám** → nhét vào `extra_system`.
- **`extra_system` đi đâu:** nối vào system prompt (agent.py:352) → agent được "mớm" thông tin + lệnh "hãy chủ động nhắc".
- **Đổi `__init__` → "Xin chào" (105):** LLM không thấy chuỗi `__init__`, có cớ tự nhiên để chào + nhắc.
- **Bọc try/except (59,100):** lỗi API thì chat vẫn chạy, chỉ không nhắc.

**Ý nghĩa:** nâng từ "chatbot bị động chờ hỏi" lên "trợ lý chủ động bám kế hoạch điều trị".

---

<a name="7"></a>
## 7. ĐÀO SÂU 4 — `_find_last_slot_id` (agent.py 193–205)

**Vấn đề:** đặt lịch cần 2 tool: `get_next_available_slot` (ra `slot_id` UUID dài) → `create_appointment` (cần đúng `slot_id`). LLM **hay chép sai UUID dài**.

**Giải pháp:** code tự truy ngược history lấy `slot_id`, không tin LLM:
```python
for msg in reversed(history):       # duyệt ngược, lấy cái gần nhất
    if msg["role"] != "tool": continue
    r = json.loads(msg["content"])
    if r.get("found") and r.get("slot_id"): return r["slot_id"]
```
Gọi ở nhánh bác sĩ (419–422): `args.setdefault("slot_id", _find_last_slot_id(history))` — LLM có thì dùng, không thì code lấp.

**Nguyên tắc khoe được:** *việc gì máy làm chắc chắn thì đừng giao LLM* (LLM giỏi suy luận, dở copy chuỗi dài).

---

<a name="8"></a>
## 8. BA DÒNG CODE PHẢI THUỘC
| Dòng | Code | Nói gì |
|---|---|---|
| agent.py:368 | `while True:` | "Đây là vòng lặp tool-calling" |
| agent.py:412 | `args["patient_id"] = patient_id` | "Ép ID ở tầng code, LLM bị dụ cũng không lộ" |
| chat.py:166 | `item = await queue.get()` | "await này giữ server không đứng hình" |

---

<a name="9"></a>
## 9. NGÂN HÀNG CÂU HỎI BẺ

**Vòng lặp nằm ở đâu? Sơ đồ vẽ mũi tên rời rạc mà?**
→ Sơ đồ là bản đơn giản hóa; thực tế mọi tool call đi qua cùng một `while True` ở agent.py:368, lặp 4 lần.

**Bệnh nhân A không xem được hồ sơ B bằng cách nào?**
→ 2 lớp: prompt cấm (agent.py:345) + code ép `args['patient_id']` (agent.py:412).

**LLM gọi tool không được phép thì sao?**
→ Chặn ở agent.py:391, trả lỗi, không thực thi.

**Lỡ vòng lặp gọi tool vô hạn?**
→ Thực tế model luôn hội tụ; có `max_tokens` + `_trim_history` (24 tin). Hướng cải tiến: thêm bộ đếm số vòng tối đa. *(điểm yếu, nhận trước)*

**Gửi lại cả history mỗi vòng, tốn token không?**
→ Có; bản chất LLM stateless. Giảm bằng `_trim_history` (agent.py:222). Đánh đổi ngữ cảnh ↔ chi phí.

**Sao phải queue/thread, không trả 1 cục cho xong?**
→ Agent đồng bộ phải chặn; FastAPI async không được chặn. Producer–consumer: agent ở thread riêng, đẩy qua asyncio.Queue, hàm async đọc bằng `await` nên không chặn. `call_soon_threadsafe` là cầu nối an toàn; `None` báo kết thúc.

**Có nhất thiết streaming không?**
→ Không. Có sẵn `chat()` trả 1 cục cho `/chat`. Chọn streaming cho luồng chính để chữ chạy + thấy agent làm gì. Đánh đổi độ phức tạp ↔ trải nghiệm.

**Sao đặt lịch BN và bác sĩ logic khác nhau?**
→ Bác sĩ chọn slot cụ thể đã xem → dùng `slot_id`. BN mô tả mong muốn (khoa/ngày/giờ) → tool tự tìm slot. Có thể hợp nhất nhưng giữ 2 đường cho khớp ngữ cảnh.

**Vì sao tách `_rag_departments` và `fhir_suggest_department`?**
→ Tách thuật toán (RAG thuần) khỏi nghiệp vụ (cấp cứu, lịch sử BN, disclaimer). Lợi: test RAG độc lập không cần Aidbox; tái sử dụng; đổi model embedding chỉ sửa 1 file.
