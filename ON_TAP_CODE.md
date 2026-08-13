# ÔN CODE — Bản đồ "hỏi gì → mở đâu → nói gì"

> Mục tiêu: hội đồng hỏi câu code nào, bạn biết ngay **file + dòng** để mở và **1 câu** để nói.
> Chiến lược trả lời câu hỏi code (3 bước): **① gọi tên file → ② chỉ đúng dòng then chốt → ③ nói 1 câu ý nghĩa.** Đừng đọc code ra mồm.

---

## A. ĐƯỜNG ĐI MỘT REQUEST (khung xương)
```
Trình duyệt → api/routes/chat.py (xác thực, nạp history)
            → agent.py chat_stream() (VÒNG LẶP tool-calling)
                → tool fhir_*.py (run) → _aidbox_client (fhir_get/post) → Aidbox FHIR
            → stream SSE về trình duyệt
```

## B. LÕI AGENT (`agent.py`) — hay bị hỏi nhất
| Hỏi gì | Mở đâu | Nói gì (1 câu) |
|---|---|---|
| "Agent hoạt động thế nào / vòng lặp ở đâu?" | **agent.py:368** `while True` | LLM quyết gọi tool hay trả lời; lặp tới khi hết đòi tool |
| "LLM có nhớ không?" | agent.py:372 (gửi lại history) | LLM stateless; mỗi vòng gửi lại toàn bộ history |
| "Nạp tool kiểu gì?" | agent.py:32–106 `_load_tool_modules` | Quét thư mục, file có TOOL_NAME + run() thì tự nạp (plugin) |
| "Đổi LLM/nhà cung cấp?" | agent.py:149–169 | SDK chuẩn OpenAI; đổi base_url+api_key là xong (Alibaba/OpenRouter/Anthropic) |
| "Xử lý ảnh (vision)?" | agent.py:264 `_ocr_image` | OCR ảnh xét nghiệm bằng qwen-vl-ocr rồi đưa text cho LLM |
| "Chống tràn context?" | agent.py:222 `_trim_history` | Giữ 24 tin gần nhất, bỏ ảnh cũ |

## C. BẢO MẬT & PHÂN QUYỀN (câu bẫy hay hỏi)
| Hỏi gì | Mở đâu | Nói gì |
|---|---|---|
| "Cô lập dữ liệu bệnh nhân?" | **agent.py:412** `args["patient_id"]=patient_id` | Ép ID ở tầng code; jailbreak cũng không lộ. Tầng prompt: agent.py:345 |
| "Phân quyền tool theo vai trò?" | agent.py:109 `_TOOLS_BY_ROLE` + 139 lọc | Mỗi role chỉ thấy subset tool; LLM không thấy = không gọi được |
| "LLM gọi tool cấm thì sao?" | agent.py:391 guard | Chặn tool ngoài allow-list lúc thực thi |
| "Secret (Gmail) vào tool sao?" | agent.py:92–95 (`SETTINGS_KEYS`) | Agent tiêm secret vào `args["_settings"]` phía server, KHÔNG qua LLM |
| "Xác thực người dùng?" | api/routes/chat.py `_resolve_patient` | patient_id lấy từ token đăng nhập, không phải LLM bịa |

## D. STREAMING (SSE / producer–consumer)
| Hỏi gì | Mở đâu | Nói gì |
|---|---|---|
| "Sao dùng SSE/queue?" | chat.py:140–179 | Agent đồng bộ chạy thread riêng, đẩy qua asyncio.Queue; async đọc bằng await → không chặn event loop |
| "SSE là gì?" | chat.py:177 `text/event-stream` | Server đẩy dữ liệu 1 chiều, chữ chạy dần |

## E. HẠ TẦNG FHIR (`tools/shared/_aidbox_client.py`)
| Hỏi gì | Mở đâu | Nói gì |
|---|---|---|
| "Tool nói chuyện Aidbox thế nào?" | `fhir_get` / `fhir_post` (dòng 18/37) | REST FHIR; GET đọc, POST tạo. Lỗi trả dict `{"error"}`, không raise |
| "Cấu hình Aidbox ở đâu?" | _aidbox_client._config:11 | Đọc AIDBOX_URL/CLIENT_ID/SECRET từ env; 26/26 tool dùng chung |
| "GET trả 1 cái hay nhiều?" | có `/id`=1 resource; không id=search→Bundle | Bundle phải `extract_entries` bóc ra |
| "Cấu trúc 1 tool FHIR?" | bất kỳ fhir_*.py | 4 khai báo (TOOL_NAME/CATEGORY/DESCRIPTION/ARGS_SCHEMA) + `run(args)->dict` |

## F. MODULE LÂM SÀNG (rule-based — nhớ "giải thích được")
| Module | File | Điểm chỉ tay |
|---|---|---|
| Sàng lọc SXHD (triệu chứng) | dengue_symptom_assessment.py | 4 lớp: severe→warning→dịch tễ/sốt→≥2 triệu chứng |
| Sàng lọc SXHD (CBC) | dengue_cbc_predict.py | 2 điểm tách (176 vs 296), combo 328 — xem ON_TAP_CBC.md |
| Kiểm tra dị ứng 4 lớp | fhir_check_drug_allergy.py:113–168 | trùng tên→cùng nhóm→chéo→verdict nặng nhất (162) — xem ON_TAP_ALLERGY.md |
| Kê đơn + block/override | fhir_create_prescription.py | check 167 → block 193 → POST 221; override ghi note 120 |
| Triage | fhir_triage_assessment.py | single red flag 105 → combo 121 → urgency map 183 → booster 205 |
| Sinh hiệu (CDS) | fhir_create_vitals.py | 5 hàm `_interp_*`; ngưỡng người lớn, tham khảo NEWS2 (không tính điểm đầy đủ) |

## G. RAG (2 kiểu — phân biệt được là ăn điểm)
| Kiểu | File | Nói gì |
|---|---|---|
| RAG **vector** (gợi ý khoa) | _rag_departments.py:86–103 | embed 384 chiều → cosine → weighted voting; ngưỡng 0.30 |
| RAG **API-retrieval** (tra thuốc) | drug_info.py | Gọi NCBI, gắn nhãn `[n]`, grounding chống lệch trích dẫn |
| Bọc nghiệp vụ quanh RAG khoa | fhir_suggest_department.py | chặn cấp cứu + boost lịch sử BN + disclaimer |

## H. WORKFLOW LỊCH & KHÁM
| Hỏi gì | Mở đâu | Nói gì |
|---|---|---|
| "Đặt lịch — trạng thái gì?" | fhir_create_appointment.py:145 `status:"proposed"` | Chờ bác sĩ duyệt (human-in-loop) |
| "Xác nhận lịch?" | fhir_confirm_appointment.py:42,46 | Guard proposed→booked + email non-blocking (90) |
| "Kết thúc khám?" | api/routes/appointments.py:150 | fulfilled + ClinicalImpression + email; kế hoạch gắn `__plan__:` (175) |
| "Nút AI gợi ý?" | appointments.py:496 | One-shot JSON, KHÔNG agent loop; bản nháp bác sĩ sửa |
| "Agent chủ động nhắc?" | chat.py:81–99 (`__init__`) | Đọc kế hoạch `__plan__:` lần trước → nhắc lúc chào |

---

## I. CHIẾN LƯỢC KHI BỊ HỎI CODE (giảm sợ)
1. **Không cần thuộc từng dòng** — chỉ cần biết **file nào + dòng then chốt**. Bảng trên là đủ.
2. Nếu quên số dòng → nói **tên file + tên hàm** cũng được ("nằm trong `chat_stream` của `agent.py`").
3. Câu "walk me through" → đi theo **khung A** (chat.py → agent.py loop → tool → aidbox).
4. Gặp câu không chắc → **nói ý thiết kế** trước, rồi "chi tiết em ở trong file X". Đừng im.
5. **Chủ động nhận hạn chế** đã biết: chưa atomic (dùng transaction Bundle), N+1 vài chỗ, chưa nhất quán extract_entries → nhận + nêu hướng sửa = ghi điểm.

## J. 5 DÒNG CODE "THUỘC LÒNG" (nếu chỉ nhớ được 5)
1. **agent.py:368** `while True` — trái tim vòng lặp tool-calling.
2. **agent.py:412** `args["patient_id"]=patient_id` — cô lập dữ liệu tầng code.
3. **agent.py:109** `_TOOLS_BY_ROLE` — phân quyền tool.
4. **_aidbox_client.py:18/37** `fhir_get`/`fhir_post` — cửa ngõ FHIR, lỗi trả dict.
5. **fhir_create_prescription.py:167→193→221** — check dị ứng TRƯỚC khi POST đơn.
