# ÔN TẬP — Module phân tích CBC (`dengue_cbc_predict.py`)

> Tờ ôn nhanh + bản đồ dòng code cho Flow E (phân tích CBC từ ảnh, Doctor only).
> File: `tools/dengue/dengue_cbc_predict.py`. Lưu CBC: `tools/fhir/fhir_create_cbc.py`.

---

## 1. BẢN CHẤT (1 câu)
Tool **sàng lọc** SXHD từ xét nghiệm máu — trả lời *"có khả năng SXHD không + nguy hiểm tới đâu"*.
**Không** chẩn đoán xác định, **không** phân độ. **Rule-based, KHÔNG ML** (không import joblib/sklearn).

## 2. THIẾT KẾ LÕI: 2 điểm + 1 cờ
- **`cbc_score`** = "giống SXHD tới đâu" (đếm chỉ số cận lâm sàng bất thường).
- **`warning_score`** = "nguy hiểm tới đâu" (cờ pha nguy hiểm).
- **`severe_flag`** = nặng (suy gan ≥1000, nghi xuất huyết nội).
- → Tách vì SXHD **diễn biến theo pha**: "giống SXHD" và "đang nguy hiểm" là 2 câu hỏi khác nhau → xử trí khác nhau.
  - Giống nhưng chưa nguy (cbc cao, warning thấp) → khám ngoại trú.
  - Đang nguy (warning cao) → nhập viện ngay, bất kể cbc.

## 3. NGƯỠNG + NGUỒN (con số phải nhớ)
| Chỉ số | Ngưỡng | Điểm | Nguồn |
|---|---|---|---|
| PLT <100 | giảm | +cbc | **QĐ 2760 tr.5** |
| PLT <50 | giảm nặng | +cbc +warning | thực hành |
| PLT <20 | cực thấp | +cbc +warning + redflag | thực hành |
| WBC <4 | leukopenia | +cbc | QĐ 2760 tr.5 (định tính) |
| HCT ↑≥20% baseline | cô đặc máu | +cbc +warning(2) | **QĐ 2760 tr.5** |
| AST/ALT 400–1000 | cảnh báo | +warning(2) | **QĐ 2760 tr.23** |
| AST/ALT ≥1000 | suy gan | **severe** +warning(3) | QĐ 2760 tr.23 |
| Ngày sốt 3–7 | pha nguy hiểm | (ghi nhận) | QĐ 2760 tr.5 |

## 4. HCT baseline chọn 3 tầng (HCT phải so nền mới biết cô đặc máu)
baseline **thật của BN** → theo **giới** (nam 43%, nữ 38% — QĐ 2760 tr.28) → TB 40.5%.
Dùng baseline ước tính thì **giảm trọng số cảnh báo** (cẩn thận độ tin cậy).

## 5. COMBO PLT↓ + HCT↑ (dấu hiệu cảnh báo CHÍNH)
PLT giảm ≥30% (so lần trước) **VÀ** HCT tăng ≥10% → `warning_score += 2`.
- Ý nghĩa: **thoát huyết tương** = pha nguy hiểm SXHD.
- Mỗi cái riêng mơ hồ (HCT↑ = mất nước; PLT↓ = nhiều bệnh) → **cùng lúc mới chắc** (tín hiệu hiệp đồng).
- Cần `plt_previous` → đo **xu hướng**, không phải ảnh chụp tĩnh. `fhir_create_cbc` tự lấy CBC cũ cùng đợt cấp vào.

## 6. TỔNG HỢP → 4 mức
```
severe_flag       → very_likely (đỏ)  CẤP CỨU NGAY
warning_score ≥2  → very_likely (đỏ)  NHẬP VIỆN     ← warning có quyền phủ quyết
cbc_score ≥2 + ngày 3-7 → likely (cam) khám trong ngày, làm NS1/IgM
cbc_score ≥1      → possible
còn lại           → unlikely
```

## 7. ⭐ ĐIỂM "VÀNG" KHI PHẢN BIỆN
1. **Mỗi finding kèm `citations`** — phân biệt rõ ngưỡng *theo văn bản* (QĐ 2760 tr.X) vs *thực hành lâm sàng*. → nghiêm túc, giải thích được.
2. **Rule-based mô phỏng cách bác sĩ suy luận theo phác đồ** → ánh xạ trực tiếp QĐ 2760, bảo vệ được từng kết luận. Đây là lý do chọn rule-based thay vì ML.

## 8. CÂU HỎI BẪY + ĐÁP
- *"Dùng ML phân tích CBC à?"* → **KHÔNG**, rule-based theo QĐ 2760. File `.joblib` trong repo là thử nghiệm, **không import ở đâu**.
- *"Sao tự đặt ngưỡng <50, <20?"* → **quy ước thực hành**, code ghi rõ "không có trong QĐ 2760". Ngưỡng pháp lý (PLT<100, HCT>20%) theo đúng văn bản.
- *"Một lần xét nghiệm sao biết giảm nhanh?"* → cần `plt_previous`; `fhir_create_cbc` truy CBC cũ cùng đợt bệnh.
- *"OCR đọc sai số thì sao?"* → lưu CBC vào FHIR + hiển thị lại cho bác sĩ xác nhận; OCR chỉ nhập liệu nhanh, bác sĩ quyết định cuối.
- *"Có thay bác sĩ không?"* → không, **sàng lọc** có disclaimer.

## 9. CÂU CHỐT (học thuộc 1 câu)
> *"`dengue_cbc_predict` chấm song song `cbc_score` (mức giống SXHD) và `warning_score` (mức nguy hiểm) qua 7 tiêu chí theo QĐ 2760 + WHO 2009, mỗi ngưỡng dẫn nguồn và ghi rõ văn bản hay thực hành. Có luật combo HCT↑+PLT↓ nhận diện thoát huyết tương. Hoàn toàn rule-based, giải thích được — không ML."*

---

# BẢN ĐỒ DÒNG CODE (`dengue_cbc_predict.py`)

## A. Khai báo & nguồn
| Mục | Dòng |
|---|---|
| Docstring dẫn nguồn (QĐ 2760 + WHO 2009, ghi rõ trang) | 1–30 |
| `DESCRIPTION` (nêu "sàng lọc, không chẩn đoán") | 38–50 |
| Hằng số ngưỡng (comment văn bản vs thực hành) | 66–100 |

## B. Thiết kế lõi (2 điểm + cờ)
| Mục | Dòng |
|---|---|
| Parse tham số | 117–126 |
| Chọn HCT baseline 3 tầng (thật → giới → TB) | 128–144 |
| PLT bắt buộc (thiếu → unknown) | 146–150 |
| Khởi tạo `cbc_score`, `warning_score`, `severe_flag` | 156–158 |

## C. 7 bước chấm điểm
| # | Mục | Dòng | Chốt |
|---|---|---|---|
| 1 | PLT (tiểu cầu) | 160–184 | `<20`:162 · `<50`:169 · `<100`:176 |
| 2 | WBC (bạch cầu) | 186–197 | `<4`:189 |
| 3 | HCT vs baseline | 199–269 | baseline thật:206 · baseline dân số:236 |
| 4 | AST/ALT (men gan) | 271–308 | ≥1000:286 · 400–1000:296 · 120–400:302 |
| 5 | COMBO PLT↓+HCT↑ | 310–336 | giảm nhanh:313 · combo:328 |
| 6 | Hgb (chỉ khi đã có cảnh báo) | 338–351 | `<10`:339 |
| 7 | Ngày sốt (pha nguy hiểm 3–7) | 353–379 | ngày 3–7:358 |

## D. Tổng hợp kết luận
| Mục | Dòng |
|---|---|
| Xác định likelihood (4 mức) | 381–~410 |
| `severe→very_likely`:382 · `warning≥2→very_likely`:387 · `cbc≥2→likely`:392 · `cbc≥1→possible`:397 |

## 3 DÒNG "CHỈ TAY" KHI BỊ HỎI
- **Tách 2 điểm:** dòng **176** (PLT<100 chỉ +cbc) vs dòng **296–297** (AST/ALT chỉ +warning).
- **Combo thoát huyết tương:** dòng **328**.
- **Trung thực nguồn:** dòng `citations[...]="...thực hành..."` (vd **167**, **174**).

---

# LIÊN QUAN: `fhir_create_cbc.py` (lưu CBC vào FHIR)
- Lưu Observation kiểu **"CBC panel"** (LOINC `58410-2`), mỗi chỉ số là 1 `component` có **mã LOINC + đơn vị UCUM**:
  PLT `777-3` (bắt buộc) · WBC `6690-2` · HCT `4544-3` · HGB `718-7` · AST `1920-8` · ALT `1742-6`.
- Chỉ số không cung cấp → không lưu.
- Metadata: `status=final`, `category=laboratory`, `subject=Patient/{id}`, `effectiveDateTime`.
- `fever_day`, `gender` KHÔNG lưu vào FHIR — chỉ truyền sang sàng lọc (gender đọc ngược từ Patient).
- Tự truy **CBC cũ cùng đợt** lấy `plt_previous` (dòng 139–182) → cấp cho combo xu hướng.
- Điểm khoe: dùng **LOINC + UCUM chuẩn quốc tế** → tích hợp được LIS/HIS thật.

---

# FLOW E (toàn cảnh — phân tích CBC từ ảnh, Doctor only)
1. Bác sĩ upload ảnh phiếu CBC + "phân tích giúp tôi" (`role=doctor_cbc`).
2. **Vision/OCR**: `_normalize_image` (resize ≤512px, PDF→PNG) → `_ocr_image` (model `qwen-vl-ocr`) đọc số → ghép text cho LLM. (`agent.py:237/264/293`)
3. Vòng lặp gọi **3 tool nối tiếp**: `fhir_search_patient` → `fhir_create_cbc` (lưu FHIR) → `dengue_cbc_predict` (chấm điểm).
4. Stream kết quả về bác sĩ. Flow chậm nhất (~4.5s) vì vision inference.
- **Doctor only**: `dengue_cbc_predict` không có trong toolset bệnh nhân; nút upload ẩn ở `role=patient`.
