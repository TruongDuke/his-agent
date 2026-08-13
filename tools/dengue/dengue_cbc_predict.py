"""UC-D2 Sàng lọc Sốt Xuất Huyết Dengue dựa trên kết quả CBC.

ĐÂY LÀ TOOL SÀNG LỌC (screening), KHÔNG phải tool phân độ.
Mục tiêu: từ kết quả xét nghiệm máu (CBC + tùy chọn AST/ALT), đánh giá
khả năng bệnh nhân bị SXHD và gợi ý các xét nghiệm tiếp theo.

═══════════════════════════════════════════════════════════════════════
CƠ SỞ LÝ THUYẾT — TẤT CẢ RULES ĐỀU CÓ DẪN NGUỒN
═══════════════════════════════════════════════════════════════════════

[1] QĐ 2760/QĐ-BYT ngày 04/7/2023 — Hướng dẫn chẩn đoán, điều trị SXHD
    (thay thế QĐ 3705/QĐ-BYT 2019)
    - Trang 4-5: Diễn biến lâm sàng (3 giai đoạn) + cận lâm sàng
    - Trang 6 :  Chẩn đoán căn nguyên (NS1, IgM/IgG, PCR)
    - Trang 7 :  Khuyến cáo điều trị, CẤM aspirin/ibuprofen/analgin
    - Trang 23:  Phụ lục 2 — Bảng phân độ 3 cột (SXHD / cảnh báo / nặng)
    - Trang 28:  Giá trị Hct TB theo giới: nam 43%, nữ 38%

[2] WHO 2009 — Dengue: Guidelines for diagnosis, treatment, prevention
    and control
    - PDF page 23 (printed p.11): Figure 1.4 — Probable dengue criteria
    - PDF page 38 (printed p.26): Critical phase days 3-7
    - PDF page 114 (printed p.102): Haematological tests (PLT, Hct)

Mỗi ngưỡng & rule đều ghi rõ trong comment là từ văn bản hay từ
quy ước thực hành lâm sàng.
"""

from __future__ import annotations

TOOL_NAME = "dengue_cbc_predict"
CATEGORY = "Healthcare"
DESCRIPTION = (
    "Sàng lọc Sốt Xuất Huyết Dengue (SXHD) dựa trên kết quả CBC. "
    "Đầu vào: chỉ số xét nghiệm máu (PLT, WBC, HCT, tùy chọn AST/ALT, Hgb, "
    "Hct baseline, giới tính, PLT lần trước, ngày sốt). "
    "Đầu ra: dengue_likelihood (very_likely/likely/possible/unlikely), các "
    "dấu hiệu phát hiện, khuyến nghị xét nghiệm tiếp theo (NS1/IgM/IgG), "
    "mức độ khẩn cấp, và trích dẫn nguồn cho từng rule. "
    "Áp dụng QĐ 2760/QĐ-BYT 2023 + WHO 2009. "
    "KHÔNG dùng để chẩn đoán xác định hay phân độ SXHD."
)

ARGS_SCHEMA = {
    "plt": (
        "number — Tiểu cầu (Platelet count), đơn vị K/μL (= ×10³/μL). "
        "Ví dụ: 85. Nếu ghi 85,000/μL thì chia 1000 = 85. BẮT BUỘC."
    ),
    "wbc":          "number — Bạch cầu (WBC), K/μL. Ví dụ: 3.2. Tùy chọn (khuyến nghị).",
    "hct":          "number — Hematocrit hiện tại, %. Ví dụ: 45.2. Tùy chọn.",
    "hct_baseline": (
        "number — Hct nền của bệnh nhân (lần đo đầu hoặc trước bệnh), %. Tùy chọn. "
        "Nếu thiếu, dùng giá trị TB theo giới (QĐ 2760 trang 28: nam 43%, nữ 38%)."
    ),
    "gender": (
        "string — Giới tính: 'male' hoặc 'female'. Dùng để chọn Hct baseline dân số "
        "khi không có baseline thực của BN (QĐ 2760 trang 28: nam 43%, nữ 38%). Tùy chọn."
    ),
    "ast":          "number — AST (SGOT), U/L. Tùy chọn.",
    "alt":          "number — ALT (SGPT), U/L. Tùy chọn.",
    "hgb":          "number — Hemoglobin, g/dL. Tùy chọn.",
    "plt_previous": "number — PLT lần xét nghiệm trước (K/μL), để phát hiện 'tiểu cầu giảm nhanh'. Tùy chọn.",
    "fever_day":    "number — Ngày sốt thứ mấy. Tùy chọn (khuyến nghị).",
}

# ─────────────────────── NGƯỠNG (THRESHOLDS) ───────────────────────

# PLT < 100.000/mm³ — QĐ 2760 trang 5 mục II.2.2:
# "Số lượng tiểu cầu giảm (< 100.000/mm³)"
_PLT_DENGUE_THRESHOLD = 100.0   # K/μL — THEO QĐ 2760

# PLT < 50, < 20 — QUY ƯỚC THỰC HÀNH LÂM SÀNG (không có trong QĐ 2760).
_PLT_WARNING_THRESHOLD  = 50.0  # K/μL — thực hành (ngưỡng cân nhắc nhập viện)
_PLT_CRITICAL_THRESHOLD = 20.0  # K/μL — thực hành (ngưỡng truyền tiểu cầu)
_PLT_NORMAL_LOW         = 150.0 # ngưỡng dưới của bình thường

# WBC giảm — QĐ 2760 trang 5 + trang 23 chỉ ghi "bạch cầu giảm", không
# định lượng ngưỡng. Dùng ngưỡng thực hành phổ biến:
_WBC_LOW_THRESHOLD = 4.0  # K/μL — thực hành (leukopenia)
_WBC_NORMAL_LOW    = 5.0  # K/μL — biên giới dưới

# Hct tăng > 20% so với baseline — QĐ 2760 trang 5 mục II.2.2:
# "Cô đặc máu khi Hematocrit tăng > 20% so với giá trị ban đầu"
_HCT_WARNING_RELATIVE_INCREASE = 20.0  # % — THEO QĐ 2760
_HCT_EARLY_RELATIVE_INCREASE   = 10.0  # % — thực hành (theo dõi sớm xu hướng)

# Hct baseline theo giới — QĐ 2760 trang 28:
# "Hct TB: nam 15-40 tuổi = 43%, nữ 15-40 tuổi = 38%"
_HCT_BASELINE_MALE    = 43.0  # % — THEO QĐ 2760 trang 28
_HCT_BASELINE_FEMALE  = 38.0  # % — THEO QĐ 2760 trang 28
_HCT_BASELINE_UNKNOWN = 40.5  # % — TB hai giới khi không biết giới tính

# AST/ALT — QĐ 2760 trang 23 Phụ lục 2 + C.1.5 phân độ tổn thương gan:
_AST_ALT_MILD_THRESHOLD    = 120.0   # U/L — tổn thương gan nhẹ
_AST_ALT_WARNING_THRESHOLD = 400.0   # U/L — SXHD CÓ DẤU HIỆU CẢNH BÁO
_AST_ALT_SEVERE_THRESHOLD  = 1000.0  # U/L — SXHD NẶNG (suy gan)

# Tiểu cầu giảm nhanh — QĐ 2760 trang 23 chỉ ghi "giảm nhanh" không
# định lượng. Ngưỡng thực hành: ≥ 30% trong lần đo gần nhất.
_PLT_RAPID_DROP_PCT = 30.0  # % — thực hành


# ─────────────────────── HELPERS ───────────────────────

def _safe_float(val, default=None):
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


# ─────────────────────── MAIN ───────────────────────
#
# TỔNG HỢP LOGIC CHẤM ĐIỂM (diễn giải các if/else bên dưới thành lời)
# ---------------------------------------------------------------------------
# Có 3 biến trạng thái:
#   cbc_score     — "CÓ GIỐNG SXHD không?" (nhận diện cận lâm sàng)
#   warning_score — "CÓ NGUY HIỂM không?"  (dấu hiệu pha nguy hiểm, có quyền phủ quyết)
#   severe_flag   — cờ nặng (suy gan / nghi xuất huyết nội) → đẩy thẳng lên mức nặng nhất
#
# 1) PLT (tiểu cầu, bắt buộc):
#      < 20  → +cbc +warning, red flag "cực thấp"       (ngưỡng thực hành)
#      < 50  → +cbc +warning, red flag "giảm nặng"      (PLT<100 theo QĐ 2760; <50 thực hành)
#      < 100 → +cbc            "giảm, hợp tiêu chí SXHD" (QĐ 2760 tr.5 II.2.2)
#      < 150 → chỉ ghi nhận (thấp-bình thường)
#      còn lại → bình thường
#
# 2) WBC (bạch cầu, tùy chọn):
#      < 4.0 → +cbc "bạch cầu giảm (leukopenia)"        (QĐ 2760 tr.5 II.1.2; ngưỡng thực hành)
#      < 5.0 → ghi nhận thấp-bình thường; còn lại bình thường
#
# 3) HCT (so với baseline; baseline = của BN nếu có, không thì TB theo giới nam43/nữ38 QĐ 2760 tr.28):
#      Có baseline thực:
#        tăng ≥20% → +cbc +2warning, red flag "cô đặc máu" (QĐ 2760 tr.5 II.2.2)
#        tăng ≥10% → +cbc +warning "cần theo dõi sát"
#        Hct < 30  → +warning, red flag "nghi xuất huyết"
#      Baseline ước tính (theo giới):
#        tăng ≥20% → +cbc +warning (nhẹ hơn vì baseline không thực)
#        Hct ≥ 50  → +cbc +warning (cao tuyệt đối, cần baseline thực để xác nhận)
#        Hct < 30  → ghi nhận nghi thiếu máu
#
# 4) AST/ALT (men gan, tùy chọn) — chỉ nạp warning, KHÔNG nạp cbc:
#      ≥ 1000 → severe_flag (suy gan, SXHD nặng)          (QĐ 2760 tr.23 / C.1.5)
#      ≥ 400  → +2warning "dấu hiệu cảnh báo"
#      ≥ 120  → ghi nhận tổn thương gan nhẹ
#
# 5) COMBO hiệp đồng: PLT giảm nhanh (≥30% so plt_previous) VÀ Hct đang tăng
#      → +2warning, red flag "combo Hct↑ + PLT↓" (thoát huyết tương = pha nguy hiểm, QĐ 2760 tr.23)
#
# 6) HGB < 10 kèm (warning_score≥2 hoặc đã có red flag):
#      → severe_flag +2warning "nghi xuất huyết nội"
#
# 7) Ngày sốt: 3–7 = giai đoạn nguy hiểm; <3 = sớm (CBC chưa điển hình); >7 = hồi phục.
#
# KẾT LUẬN (xét theo thứ tự, dừng ở điều kiện đầu tiên đúng):
#      severe_flag                       → very_likely  (NẶNG)        → cấp cứu ngay
#      warning_score ≥ 2                 → very_likely  (cảnh báo)    → nhập viện vài giờ
#      cbc_score ≥ 2 và (pha nguy hiểm   → likely                     → khám trong ngày + NS1
#                        hoặc chưa rõ ngày sốt)
#      cbc_score ≥ 1                     → possible                   → làm NS1 test nhanh
#      còn lại                           → unlikely                   → theo dõi tại nhà
#
# → warning_score có quyền PHỦ QUYẾT: dù cbc_score thấp, nguy hiểm vẫn đẩy lên nhập viện.
#   Mỗi lần cộng điểm đều kèm findings[] (mô tả) + citations[] (nguồn) để truy vết.
# ---------------------------------------------------------------------------

def run(args: dict) -> dict:
    plt          = _safe_float(args.get("plt"))
    wbc          = _safe_float(args.get("wbc"))
    hct          = _safe_float(args.get("hct"))
    user_baseline = args.get("hct_baseline")
    ast          = _safe_float(args.get("ast"))
    alt          = _safe_float(args.get("alt"))
    hgb          = _safe_float(args.get("hgb"))
    plt_prev     = _safe_float(args.get("plt_previous"))
    fever_day    = _safe_float(args.get("fever_day"))
    gender       = str(args.get("gender", "")).strip().lower()

    # Chọn Hct baseline: ưu tiên baseline thực của BN, sau đó theo giới, cuối cùng TB hai giới
    has_real_baseline = (user_baseline is not None)
    if has_real_baseline:
        hct_baseline = _safe_float(user_baseline, default=_HCT_BASELINE_UNKNOWN)
        baseline_note = None
    elif gender == "male":
        hct_baseline = _HCT_BASELINE_MALE
        baseline_note = f"Dùng Hct baseline TB nam giới: {_HCT_BASELINE_MALE}% (QĐ 2760 trang 28)"
    elif gender == "female":
        hct_baseline = _HCT_BASELINE_FEMALE
        baseline_note = f"Dùng Hct baseline TB nữ giới: {_HCT_BASELINE_FEMALE}% (QĐ 2760 trang 28)"
    else:
        hct_baseline = _HCT_BASELINE_UNKNOWN
        baseline_note = (
            f"Không có baseline thực và không biết giới tính — dùng TB hai giới "
            f"{_HCT_BASELINE_UNKNOWN}%. Cung cấp 'gender' hoặc 'hct_baseline' để chính xác hơn."
        )

    if plt is None:
        return {
            "error": "Thiếu chỉ số tiểu cầu (plt). Đây là tiêu chí bắt buộc.",
            "dengue_likelihood": "unknown",
        }

    findings: list[str] = []
    citations: dict[str, str] = {}
    red_flags: list[str] = []

    # THIẾT KẾ: tách 2 điểm vì SXHD diễn biến theo pha, cần trả lời 2 câu hỏi khác nhau:
    #   cbc_score     = "CÓ GIỐNG SXHD không?" (nhận diện cận lâm sàng)      -> quyết mức "likely/possible"
    #   warning_score = "CÓ NGUY HIỂM không?"  (dấu hiệu pha nguy hiểm)      -> có quyền phủ quyết, đẩy lên "very_likely" (nhập viện)
    # Một tiêu chí nạp vào điểm nào chính là tri thức lâm sàng được mã hoá (vd men gan cao chỉ +warning, không +cbc).
    cbc_score = 0      # 0-3: số tiêu chí CBC bất thường (theo QĐ 2760 trang 23) (có giống SXHD ko)
    warning_score = 0  # cờ "dấu hiệu cảnh báo" Có NGUY HIỂM không
    severe_flag = False

    # ── 1. PLT — Tiểu cầu ──
    # Nguồn chính: QĐ 2760 trang 5 mục II.2.2 (< 100); trang 23 Phụ lục 2
    if plt < _PLT_CRITICAL_THRESHOLD:
        cbc_score += 1
        warning_score += 1
        msg = f"⛔ Tiểu cầu CỰC THẤP: {plt} K/μL (< 20) — nguy cơ xuất huyết cao"
        findings.append(msg)
        citations[msg] = "Ngưỡng < 20: quy ước thực hành (không có trong QĐ 2760)"
        red_flags.append("Tiểu cầu cực thấp")
    elif plt < _PLT_WARNING_THRESHOLD:
        cbc_score += 1
        warning_score += 1
        msg = f"🔴 Tiểu cầu GIẢM NẶNG: {plt} K/μL (< 50)"
        findings.append(msg)
        citations[msg] = "PLT < 100 theo QĐ 2760 trang 5; ngưỡng < 50 là thực hành"
        red_flags.append("Tiểu cầu giảm nặng")
    elif plt < _PLT_DENGUE_THRESHOLD:
        cbc_score += 1
        msg = f"🟡 Tiểu cầu giảm: {plt} K/μL (< 100) — phù hợp tiêu chí cận lâm sàng SXHD"
        findings.append(msg)
        citations[msg] = "QĐ 2760 trang 5 mục II.2.2"
    elif plt < _PLT_NORMAL_LOW:
        findings.append(f"🟢 Tiểu cầu thấp-bình thường: {plt} K/μL (100–150)")
    else:
        findings.append(f"✅ Tiểu cầu bình thường: {plt} K/μL")

    # ── 2. WBC — Bạch cầu ──
    # Nguồn: QĐ 2760 trang 5 mục II.1.2 ("bạch cầu thường giảm") + trang 23
    if wbc is not None:
        if wbc < _WBC_LOW_THRESHOLD:
            cbc_score += 1
            msg = f"🟡 Bạch cầu giảm: {wbc} K/μL — leukopenia, dấu hiệu sớm điển hình của SXHD"
            findings.append(msg)
            citations[msg] = "QĐ 2760 trang 5 mục II.1.2; ngưỡng số là thực hành"
        elif wbc < _WBC_NORMAL_LOW:
            findings.append(f"🟢 Bạch cầu thấp-bình thường: {wbc} K/μL")
        else:
            findings.append(f"✅ Bạch cầu bình thường: {wbc} K/μL")

    # ── 3. HCT — Hematocrit (so với baseline) ──
    # Nguồn: QĐ 2760 trang 5 mục II.2.2 — "Hct tăng > 20% so với baseline"
    # Baseline: ưu tiên baseline thực của BN; nếu không có, dùng TB theo giới
    # (QĐ 2760 trang 28: nam 43%, nữ 38%)
    hct_relative_change = None
    if hct is not None and hct_baseline > 0:
        hct_relative_change = (hct - hct_baseline) / hct_baseline * 100.0
        if has_real_baseline:
            if hct_relative_change >= _HCT_WARNING_RELATIVE_INCREASE:
                cbc_score += 1
                warning_score += 2  # cô đặc máu là cờ cảnh báo MẠNH
                msg = (
                    f"⛔ Hematocrit TĂNG {hct_relative_change:.1f}% so với baseline "
                    f"({hct}% vs {hct_baseline}%) — CÔ ĐẶC MÁU, nghi thoát huyết tương"
                )
                findings.append(msg)
                citations[msg] = "QĐ 2760 trang 5 mục II.2.2 (>20% baseline = cô đặc máu)"
                red_flags.append("Cô đặc máu (Hct tăng >20% baseline)")
            elif hct_relative_change >= _HCT_EARLY_RELATIVE_INCREASE:
                cbc_score += 1
                warning_score += 1
                msg = (
                    f"🟡 Hematocrit tăng {hct_relative_change:.1f}% so với baseline "
                    f"({hct}% vs {hct_baseline}%) — cần theo dõi sát"
                )
                findings.append(msg)
                citations[msg] = "Theo dõi sớm xu hướng cô đặc máu (QĐ 2760 trang 5)"
            elif hct < 30:
                warning_score += 1
                msg = f"🟡 Hematocrit THẤP: {hct}% — nghi thiếu máu/xuất huyết"
                findings.append(msg)
                citations[msg] = "Suy luận lâm sàng"
                red_flags.append("Hct thấp – nghi xuất huyết")
            else:
                findings.append(
                    f"✅ Hematocrit: {hct}% (thay đổi {hct_relative_change:+.1f}% so với baseline)"
                )
        else:
            # Baseline dân số theo giới (QĐ 2760 trang 28) hoặc TB hai giới
            if baseline_note:
                findings.append(f"ℹ️ {baseline_note}")
            if hct_relative_change >= _HCT_WARNING_RELATIVE_INCREASE:
                cbc_score += 1
                warning_score += 1  # một mức thấp hơn vì baseline ước tính, không thực
                msg = (
                    f"🟡 Hematocrit TĂNG {hct_relative_change:.1f}% so với baseline dân số "
                    f"({hct}% vs {hct_baseline}%) — gợi ý cô đặc máu. "
                    f"Cần baseline thực của BN để xác nhận (QĐ 2760)."
                )
                findings.append(msg)
                citations[msg] = (
                    "QĐ 2760 trang 5 (>20% baseline = cô đặc máu); "
                    "baseline dùng TB theo giới (QĐ 2760 trang 28)"
                )
            elif hct >= 50:
                cbc_score += 1
                warning_score += 1
                msg = (
                    f"🟡 Hematocrit: {hct}% — cao (≥ 50%). "
                    f"Không có baseline thực → không thể xác nhận cô đặc máu theo QĐ 2760."
                )
                findings.append(msg)
                citations[msg] = "Ngưỡng tuyệt đối là thực hành; QĐ 2760 yêu cầu so baseline"
            elif hct < 30:
                msg = f"🟡 Hematocrit THẤP: {hct}% — nghi thiếu máu."
                findings.append(msg)
                citations[msg] = "Suy luận lâm sàng"
            else:
                findings.append(
                    f"ℹ️ Hematocrit: {hct}% — không có baseline thực để đánh giá xu hướng."
                )

    # ── 4. AST / ALT — Men gan ──
    # Nguồn: QĐ 2760 trang 23 Phụ lục 2 + C.1.5 phân độ tổn thương gan:
    # - 120–400 U/L: nhẹ (ghi nhận, không raise score)
    # - 400–1000 U/L: cảnh báo (dấu hiệu cảnh báo)
    # - ≥ 1000 U/L:  nặng (SXHD nặng, suy gan)
    ast_alt_max = None
    if ast is not None and alt is not None:
        ast_alt_max = max(ast, alt)
    elif ast is not None:
        ast_alt_max = ast
    elif alt is not None:
        ast_alt_max = alt

    if ast_alt_max is not None:
        label = "AST" if (ast is not None and (alt is None or ast >= alt)) else "ALT"
        if ast_alt_max >= _AST_ALT_SEVERE_THRESHOLD:
            severe_flag = True
            warning_score += 3
            msg = (
                f"⛔ {label} cực cao: {ast_alt_max} U/L (≥ 1000) — "
                f"TỔN THƯƠNG GAN NẶNG, tiêu chí SXHD NẶNG"
            )
            findings.append(msg)
            citations[msg] = "QĐ 2760 trang 5 + trang 23 (AST/ALT ≥ 1000 = SXHD nặng)"
            red_flags.append("Suy gan nặng (AST/ALT ≥ 1000)")
        elif ast_alt_max >= _AST_ALT_WARNING_THRESHOLD:
            warning_score += 2
            msg = f"🔴 {label} cao: {ast_alt_max} U/L (400–1000) — DẤU HIỆU CẢNH BÁO SXHD"
            findings.append(msg)
            citations[msg] = "QĐ 2760 trang 23 Phụ lục 2 (AST/ALT 400–1000 = cảnh báo)"
            red_flags.append("Tăng men gan (≥ 400)")
        elif ast_alt_max >= _AST_ALT_MILD_THRESHOLD:
            msg = f"🟡 {label} tăng nhẹ: {ast_alt_max} U/L (120–400) — tổn thương gan NHẸ"
            findings.append(msg)
            citations[msg] = "QĐ 2760 trang 23 C.1.5: AST/ALT 120–<400 = tổn thương gan nhẹ"
            # Không tăng warning_score — chỉ ghi nhận thông tin
        else:
            findings.append(f"✅ AST/ALT bình thường: {ast_alt_max} U/L (< 120)")

    # ── 5. COMBO: Hct tăng + Tiểu cầu giảm nhanh ──
    # Nguồn: QĐ 2760 trang 23 Phụ lục 2 — "Hct tăng kèm tiểu cầu giảm nhanh"
    plt_rapid_drop = False
    if plt_prev is not None and plt_prev > 0:
        drop_pct = (plt_prev - plt) / plt_prev * 100.0
        if drop_pct >= _PLT_RAPID_DROP_PCT:
            plt_rapid_drop = True
            msg = (
                f"⚠️ Tiểu cầu GIẢM NHANH: {plt_prev} → {plt} K/μL "
                f"(giảm {drop_pct:.1f}% so với lần trước)"
            )
            findings.append(msg)
            citations[msg] = "QĐ 2760 trang 23 dùng cụm 'giảm nhanh'; ngưỡng 30% là thực hành"

    hct_is_rising = (
        hct_relative_change is not None
        and hct_relative_change >= _HCT_EARLY_RELATIVE_INCREASE
    )
    # COMBO hiệp đồng: mỗi dấu hiệu riêng lẻ MƠ HỒ (HCT tăng có thể do mất nước; PLT giảm gặp ở
    # nhiều nhiễm trùng), nhưng CÙNG LÚC = thoát huyết tương = pha nguy hiểm SXHD -> cộng điểm nặng.
    # Cần plt_previous (xu hướng), không chỉ giá trị 1 lần -> fhir_create_cbc tự truy CBC cũ cấp vào.
    if plt_rapid_drop and hct_is_rising:
        warning_score += 2
        msg = (
            "⛔ COMBO CẢNH BÁO: Hct tăng đồng thời với tiểu cầu giảm nhanh — "
            "đây là DẤU HIỆU CẢNH BÁO chính theo QĐ 2760"
        )
        findings.append(msg)
        citations[msg] = "QĐ 2760 trang 23 Phụ lục 2 — dấu hiệu cảnh báo chính"
        red_flags.append("Combo Hct↑ + PLT↓ nhanh")

    # ── 6. Hgb thấp — nghi xuất huyết nội (chỉ khi đã có warning) ──
    if hgb is not None and hgb < 10:
        if warning_score >= 2 or red_flags:
            severe_flag = True
            warning_score += 2
            msg = (
                f"⛔ Hemoglobin THẤP: {hgb} g/dL kèm dấu hiệu cảnh báo — "
                f"NGHI XUẤT HUYẾT NỘI, cần đánh giá khẩn"
            )
            findings.append(msg)
            citations[msg] = "Suy luận lâm sàng (không có ngưỡng cụ thể trong QĐ)"
            red_flags.append("Nghi xuất huyết nội")
        else:
            findings.append(f"🟡 Hemoglobin thấp: {hgb} g/dL — nghi thiếu máu (cần đánh giá)")

    # ── 7. Ngày sốt ──
    # Nguồn: QĐ 2760 trang 5 — "Giai đoạn nguy hiểm: ngày thứ 3-7"
    dangerous_phase = False
    fever_phase = None
    if fever_day is not None:
        if 3 <= fever_day <= 7:
            dangerous_phase = True
            fever_phase = "dangerous"
            msg = (
                f"⚠️ Ngày sốt thứ {int(fever_day)} — GIAI ĐOẠN NGUY HIỂM "
                f"(ngày 3–7), cần theo dõi sát"
            )
            findings.append(msg)
            citations[msg] = "QĐ 2760 trang 5 mục II.2"
        elif fever_day < 3:
            fever_phase = "early"
            msg = (
                f"ℹ️ Ngày sốt thứ {int(fever_day)} — giai đoạn sốt; biến đổi CBC "
                f"điển hình của SXHD thường xuất hiện từ ngày 3"
            )
            findings.append(msg)
            citations[msg] = "QĐ 2760 trang 5 mục II.1"
        else:
            fever_phase = "recovery"
            msg = f"ℹ️ Ngày sốt thứ {int(fever_day)} — giai đoạn hồi phục (ngày 7–10)"
            findings.append(msg)
            citations[msg] = "QĐ 2760 trang 5 mục II.3"

    # ── XÁC ĐỊNH LIKELIHOOD ──
    if severe_flag:
        likelihood = "very_likely"
        likelihood_label = "Rất nhiều khả năng SXHD có biến chứng NẶNG"
        color = "red"
        next_action = "🚨 ĐI CẤP CỨU NGAY — không tự theo dõi tại nhà"
    elif warning_score >= 2:
        likelihood = "very_likely"
        likelihood_label = "Rất nhiều khả năng SXHD CÓ DẤU HIỆU CẢNH BÁO"
        color = "red"
        next_action = "🚨 Nhập viện trong vài giờ tới để theo dõi 24/24"
    elif cbc_score >= 2 and (dangerous_phase or fever_day is None):
        likelihood = "likely"
        likelihood_label = "Khả năng cao là Sốt Xuất Huyết Dengue"
        color = "orange"
        next_action = "Khám bác sĩ trong ngày, làm NS1/IgM để xác chẩn"
    elif cbc_score >= 1:
        likelihood = "possible"
        likelihood_label = "Có thể là SXHD — cần xác chẩn"
        color = "yellow"
        next_action = "Đến phòng khám làm NS1 (test nhanh) trong ngày"
    else:
        likelihood = "unlikely"
        likelihood_label = "CBC chưa gợi ý SXHD"
        color = "green"
        if fever_phase == "early":
            next_action = (
                "Theo dõi tại nhà. Nếu vẫn sốt sau 24–48 giờ, làm lại CBC + NS1 "
                "(biến đổi CBC điển hình thường xuất hiện từ ngày 3)"
            )
        else:
            next_action = "Theo dõi triệu chứng; tái khám nếu xuất hiện dấu hiệu mới"

    # ── KHUYẾN NGHỊ XÉT NGHIỆM TIẾP THEO ──
    # Nguồn: QĐ 2760 trang 6 mục III.1.1
    recommended_tests = []
    if fever_day is None or fever_day <= 5:
        recommended_tests.append(
            "🔬 NS1 (test nhanh) — ưu tiên trong 5 ngày đầu của sốt "
            "(QĐ 2760 trang 6)"
        )
    elif fever_day <= 7:
        recommended_tests.append(
            "🔬 NS1 — vẫn có thể làm trong vòng 7 ngày đầu nhưng độ nhạy giảm"
        )
    if fever_day is None or fever_day >= 5:
        recommended_tests.append(
            "🔬 IgM/IgG (ELISA hoặc test nhanh) — từ ngày 5 trở đi, đặc biệt "
            "nếu NS1 âm tính (QĐ 2760 trang 6)"
        )
    if likelihood in ("likely", "very_likely"):
        recommended_tests.append("🔬 Lặp lại CBC sau 12–24 giờ để theo dõi xu hướng")
    if warning_score >= 1:
        recommended_tests.append("🔬 Đông máu (PT, aPTT, fibrinogen) nếu nghi xuất huyết")
        recommended_tests.append("🔬 Siêu âm bụng tìm tràn dịch màng phổi/màng bụng")

    # ── DIỄN GIẢI (interpretation) ──
    parts = []
    criteria_met = []
    if plt < _PLT_DENGUE_THRESHOLD:
        criteria_met.append("tiểu cầu giảm")
    if wbc is not None and wbc < _WBC_LOW_THRESHOLD:
        criteria_met.append("bạch cầu giảm")
    if hct_relative_change is not None and hct_relative_change >= _HCT_EARLY_RELATIVE_INCREASE:
        if has_real_baseline:
            criteria_met.append("Hct tăng so với baseline thực")
        else:
            criteria_met.append("Hct tăng so với baseline dân số")
    elif not has_real_baseline and hct is not None and hct >= 50:
        criteria_met.append("Hct cao (không có baseline)")
    if criteria_met:
        parts.append(
            f"Phát hiện {len(criteria_met)}/3 tiêu chí cận lâm sàng SXHD theo "
            f"QĐ 2760 (Phụ lục 2 trang 23): {', '.join(criteria_met)}."
        )
    if dangerous_phase:
        parts.append(
            "Bệnh nhân đang trong giai đoạn nguy hiểm (ngày 3–7) — "
            "cửa sổ thoát huyết tương và sốc có thể xảy ra."
        )
    if red_flags:
        parts.append(f"Có {len(red_flags)} dấu hiệu cảnh báo: {', '.join(red_flags)}.")
    if not parts:
        parts.append("CBC chưa có dấu hiệu nào gợi ý SXHD theo tiêu chí của QĐ 2760.")
    interpretation = " ".join(parts)

    # ── KHUYẾN CÁO BẮT BUỘC ──
    # Nguồn: QĐ 2760 trang 7 mục IV.A.1
    aspirin_warning = (
        "⛔ KHÔNG dùng aspirin (acetylsalicylic acid), analgin, ibuprofen "
        "để hạ sốt vì có thể gây xuất huyết, toan máu (QĐ 2760 trang 7). "
        "Chỉ dùng paracetamol đơn chất, 10–15 mg/kg/lần, cách 4–6 giờ, "
        "tối đa 60 mg/kg/ngày."
    )

    return {
        "dengue_likelihood":      likelihood,
        "likelihood_label":       likelihood_label,
        "color":                  color,
        "cbc_score":              cbc_score,
        "warning_score":          warning_score,
        "input": {
            "plt":          plt,
            "wbc":          wbc,
            "hct":          hct,
            "hct_baseline": hct_baseline,
            "gender":       gender or None,
            "ast":          ast,
            "alt":          alt,
            "hgb":          hgb,
            "plt_previous": plt_prev,
            "fever_day":    fever_day,
        },
        "findings":               findings,
        "citations":              citations,
        "clinical_red_flags":     red_flags,
        "interpretation":         interpretation,
        "recommended_next_tests": recommended_tests,
        "next_action":            next_action,
        "aspirin_warning":        aspirin_warning,
        "dangerous_phase":        dangerous_phase,
        "fever_phase":            fever_phase,
        "disclaimer": (
            "Đây là TOOL SÀNG LỌC dựa trên CBC theo WHO 2009 và "
            "QĐ 2760/QĐ-BYT ngày 04/7/2023. KHÔNG thay thế khám lâm sàng. "
            "Chẩn đoán xác định SXHD CHỈ qua xét nghiệm NS1/IgM/IgG/PCR "
            "(QĐ 2760 trang 6)."
        ),
        "source_references": {
            "QĐ_2760_QD_BYT_2023": {
                "trang_5":  "Giai đoạn lâm sàng & cận lâm sàng (PLT<100, Hct>20% baseline, BC giảm)",
                "trang_6":  "Chẩn đoán căn nguyên: NS1, IgM/IgG, PCR",
                "trang_7":  "Khuyến cáo điều trị, cấm aspirin/ibuprofen/analgin",
                "trang_23": "Phụ lục 2 — Phân độ SXHD (Hct↑+PLT↓, AST/ALT≥400 = cảnh báo; ≥1000 = nặng); C.1.5 tổn thương gan nhẹ (120–400)",
                "trang_28": "Giá trị Hct TB theo giới: nam 43%, nữ 38%",
            },
            "WHO_2009": {
                "page_23_pdf":  "Figure 1.4 — Probable dengue criteria",
                "page_38_pdf":  "Section 2.1.2 — Critical phase days 3–7",
                "page_114_pdf": "Section 4.3.5 — Haematological tests",
            },
        },
        "_citation": "QĐ 2760/QĐ-BYT 2023 · Bộ Y tế Việt Nam · WHO Dengue Guidelines 2009",
    }


# ─────────────────────── SELF-TEST ───────────────────────
if __name__ == "__main__":
    test_cases = [
        ("Kịch bản 1 - SXHD cổ điển",
         {"plt": 85, "wbc": 3.2, "hct": 44, "fever_day": 4}),
        ("Kịch bản 2 - SXHD cảnh báo (có baseline thực)",
         {"plt": 45, "wbc": 2.8, "hct": 52, "hct_baseline": 38,
          "ast": 520, "fever_day": 5, "plt_previous": 90}),
        ("Kịch bản 3 - CBC bình thường, sốt ngày 2",
         {"plt": 240, "wbc": 6.5, "hct": 42, "fever_day": 2}),
        ("Kịch bản 4 - PLT thấp đơn lẻ",
         {"plt": 72, "wbc": 6.8, "hct": 41, "fever_day": 3}),
        ("Kịch bản 5 - SXHD nặng (suy gan)",
         {"plt": 30, "wbc": 2.0, "hct": 50, "hct_baseline": 38,
          "ast": 1200, "alt": 1500, "fever_day": 6}),
        ("Kịch bản 6 - Nam giới không có baseline",
         {"plt": 65, "wbc": 3.5, "hct": 53, "gender": "male", "fever_day": 5}),
        ("Kịch bản 7 - Nữ giới không có baseline",
         {"plt": 65, "wbc": 3.5, "hct": 48, "gender": "female", "fever_day": 5}),
        ("Kịch bản 8 - Men gan tăng nhẹ (120-400)",
         {"plt": 80, "wbc": 3.8, "ast": 250, "alt": 180, "fever_day": 4}),
    ]
    for name, args in test_cases:
        print("=" * 70)
        print(name)
        print("=" * 70)
        result = run(args)
        print(f"  Likelihood: {result['dengue_likelihood']} ({result['color']})")
        print(f"  Label:      {result['likelihood_label']}")
        print(f"  Next:       {result['next_action']}")
        print(f"  Red flags:  {result['clinical_red_flags']}")
        print(f"  CBC score:  {result['cbc_score']}, Warning: {result['warning_score']}")
        print(f"  Findings:")
        for f in result['findings']:
            print(f"    {f}")
        print()
