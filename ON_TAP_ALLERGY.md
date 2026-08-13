# ÔN TẬP — Kiểm tra dị ứng thuốc (4 lớp + 3 tầng cảnh báo)

> File: `tools/fhir/fhir_check_drug_allergy.py` (tool) + `tools/shared/_drug_allergy_rules.py` (luật).
> Gọi TRƯỚC `fhir_create_prescription` (kê đơn).

---

## 0. Làm rõ "tầng/lớp" (đừng lẫn)
- **4 LỚP phát hiện** (cách *tìm* xung đột): trùng tên → cùng nhóm → phản ứng chéo → tổng hợp.
- **3 TẦNG kết luận** (verdict): **block** (cấm) / **warn** (cảnh báo) / **clear** (an toàn).
- (UI kê đơn cũng có "3-tier alert": banner dị ứng sẵn có → check realtime khi chọn thuốc → chặn khi submit.)

## 1. BẢN CHẤT (1 câu)
Đối chiếu thuốc định kê với danh sách dị ứng đã ghi nhận của BN (từ FHIR), trả về **block/warn/clear** + lý do + thuốc thay thế. **Rule-based, có dẫn nguồn.**

## 2. CƠ CHẾ 4 LỚP
| Lớp | Logic | Mức | Ví dụ |
|---|---|---|---|
| 1. Trùng tên trực tiếp | substance == tên thuốc | **critical** | dị ứng "Amoxicillin" + kê Amoxicillin |
| 2. Cùng nhóm dược lý | alias→class, class == drug_class | **critical** | dị ứng "Penicillin" + kê Amoxicillin |
| 3. Phản ứng chéo | tra bảng CROSS_REACTIVITY | **warning** (vài cái critical) | dị ứng Penicillin + kê Cephalosporin |
| 4. Tổng hợp verdict | lấy mức **nặng nhất** | block/warn/clear | — |

## 3. HAI CẤU TRÚC DỮ LIỆU (`_drug_allergy_rules.py`)
- **`ALLERGY_ALIASES`**: chữ BN nói → nhóm dược lý. VD "Bactrim"→sulfonamide, "Augmentin"→penicillin, "Aspirin"→[salicylate, nsaid].
- **`CROSS_REACTIVITY`**: cặp (nhóm dị ứng, nhóm kê) → {severity, message, alternatives}. Chỉ chứa **cặp KHÁC nhóm**; cùng nhóm tự sinh trong code.

## 4. BẢNG 7 CẶP PHẢN ỨNG CHÉO (nhớ mức)
| Cặp | Mức | Ghi chú |
|---|---|---|
| Penicillin ↔ Cephalosporin | warning | chéo β-lactam 5–10% (Stockley's tr.234) |
| **NSAID ↔ Aspirin** | **critical** | AERD — co thắt phế quản nặng |
| NSAID ↔ COX-2 | warning | ~7% |
| Aspirin ↔ COX-2 | warning | ~5% |
| Sulfa ↔ Thiazide (HCTZ) | warning | cùng nhóm sulfa |
| Sulfa ↔ Loop (Furosemide) | warning | cùng nhóm sulfa |
| ACE-inhibitor → ARB | warning | phù mạch (thấp hơn ACE-I) |
| (Macrolide ↔ Macrolide) | critical | same-class, để rõ ràng |

## 5. ĐIỂM THIẾT KẾ "ĂN ĐIỂM"
**a) Map tên → NHÓM dược lý:** BN nói "Penicillin" nhưng bác sĩ kê "Amoxicillin" (một penicillin). So tên thì trượt; map về **nhóm** mới bắt được cả họ thuốc.

**b) Tách "cùng nhóm" (critical/block) vs "phản ứng chéo" (warning/warn):**
- Cùng nhóm = **chắc chắn** phản ứng → chặn.
- Khác nhóm chéo = **có nguy cơ** (vd Pen→Ceph 5–10%) → cảnh báo, cho qua nếu bác sĩ xác nhận.
- Rủi ro khác → hành động khác.
- Ngoại lệ: **NSAID↔Aspirin = critical** vì AERD đe dọa tính mạng (không phải warning thường).

**c) Same-class tự sinh trong code** (`allergy_class == drug_class → critical`) → không phải hardcode 50+ nhóm; bảng chỉ chứa cặp khác nhóm.

**d) Ưu tiên an toàn:** verdict lấy **mức nặng nhất** (any critical → block; any warning → warn; else clear).

## 6. CÁC TRƯỜNG HỢP BIÊN (xử lý an toàn)
- Thuốc **không có trong catalog** → verdict `warn` "unknown_drug, verify thủ công".
- Dị ứng **không phân loại được nhóm** → `warning` "unmatched_allergy, verify thủ công".
- BN **chưa có dị ứng** → `clear`.
- **Chỉ xét dị ứng category=medication** (bỏ qua food/environment).

## 7. GỢI Ý THUỐC THAY THẾ
Khi có xung đột, gợi ý tối đa 5 thuốc **cùng category nhưng khác drug_class** (vd dị ứng penicillin → gợi ý macrolide/quinolone). Lấy từ `alternatives` của rule.

## 8. NGUỒN
Stockley's Drug Interactions 13th ed (2022) · BNF 86 · WHO Pharmacovigilance · QĐ 1088/QĐ-BYT 2013.

## 9. CÂU HỎI BẪY + ĐÁP
- *"Hardcode luật, không mở rộng được?"* → cross-class hardcode 7 cặp (có nguồn); **same-class tự sinh** trong code nên không cần liệt kê 50+ nhóm.
- *"Bác sĩ có override được block không?"* → CÓ, khi kê đơn truyền `override_reason` → ghi vào `note` của MedicationRequest (human-in-the-loop, có vết).
- *"Sao NSAID↔Aspirin là critical mà Pen↔Ceph chỉ warning?"* → AERD (NSAID/Aspirin) gây co thắt phế quản nặng, đe dọa tính mạng; chéo β-lactam chỉ 5–10% và thường nhẹ.
- *"Dùng AI/ML không?"* → KHÔNG, rule-based + bảng tra có dẫn nguồn → giải thích được từng cảnh báo.

## 10. CÂU CHỐT (học thuộc)
> *"Kiểm tra dị ứng theo 4 lớp: trùng tên, cùng nhóm dược lý, phản ứng chéo, rồi tổng hợp lấy mức nặng nhất ra verdict block/warn/clear. Em map tên thuốc BN nói về nhóm dược lý để bắt cả họ thuốc, và tách 'cùng nhóm' (chặn) khỏi 'phản ứng chéo' (cảnh báo) vì rủi ro khác nhau. Tất cả rule-based, dẫn nguồn Stockley's/BNF/WHO, bác sĩ override được nhưng phải ghi lý do."*

---

# BẢN ĐỒ DÒNG CODE

## `fhir_check_drug_allergy.py`
| Mục | Dòng |
|---|---|
| Docstring "Cơ chế 4 lớp" + nguồn | 1–13 |
| `_find_drug` (khớp catalog theo id/tên) | 37–52 |
| Parse + thuốc không trong catalog → warn | 65–88 |
| Lấy dị ứng BN từ FHIR (`fhir_get_allergies`) | 91–94 |
| Không có dị ứng → clear | 96–105 |
| Vòng lặp từng dị ứng | 113–160 |
| ├ chỉ xét `category == medication` | 115 |
| ├ **Lớp 1: trùng tên** → critical | 121–131 |
| ├ map alias→class; không match → warning | 134–144 |
| └ **Lớp 2+3: cross_reactivity** | 146–160 |
| **Lớp 4: tổng hợp verdict** (nặng nhất) | 162–168 |
| Gợi ý thuốc thay thế (cùng category, khác class) | 170–180 |
| Return (verdict, checks, alternatives, _citation) | 182–194 |

## `_drug_allergy_rules.py`
| Mục | Dòng |
|---|---|
| `ALLERGY_ALIASES` (tên → nhóm) | 23–100 |
| `CROSS_REACTIVITY` (7 cặp khác nhóm) | 110–177 |
| ├ Penicillin↔Cephalosporin (warning) | 114–123 |
| ├ NSAID↔Aspirin (critical, AERD) | 127–136 |
| ├ NSAID/Aspirin↔COX-2 (warning) | 138–147 |
| ├ Sulfa↔Thiazide/Loop (warning) | 152–161 |
| ├ ACE→ARB (warning) | 165–169 |
| └ Macrolide same-class | 172–176 |
| `match_allergy_classes` (exact → substring) | 189–205 |
| **`check_cross_reactivity`** (same-class auto + tra bảng) | 208–217 |

## 3 DÒNG "CHỈ TAY" KHI BỊ HỎI
- **Map tên→nhóm:** `match_allergy_classes` (rules **189**).
- **Tách critical/warning:** `check_cross_reactivity` same-class auto (rules **211**) vs bảng cross (rules **110**).
- **Ưu tiên an toàn (verdict nặng nhất):** tool **162–168**.
