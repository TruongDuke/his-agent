"""Bộ ca kiểm thử module sàng lọc Sốt Xuất Huyết Dengue (rule-based).

Đối chiếu output của tools/dengue/dengue_symptom_assessment.py với phân độ
theo QĐ 2760/QĐ-BYT 2023 (Phụ lục 2) + WHO Dengue Guidelines 2009.

Vì module là RULE-BASED nên kết quả XÁC ĐỊNH và LẶP LẠI ĐƯỢC:
mỗi ca có đầu vào rõ ràng và mức độ kỳ vọng rõ ràng → tính được độ chính xác.

Chạy:  python3 tests/test_dengue_screening.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.dengue.dengue_symptom_assessment import run

# (Tên ca, đầu vào, severity kỳ vọng, lý do/căn cứ phác đồ)
CASES = [
    # ── Lớp 4: Dấu hiệu NẶNG → severe (chặn ngay, bỏ qua mọi lớp dưới) ──
    ("Sốc — bỏ qua mọi điều kiện khác",
     {"severe_signs": ["shock_signs"]},
     "severe", "Bất kỳ dấu hiệu nặng → cấp cứu (QĐ2760 mục SXHD nặng)"),
    ("Nặng đè cảnh báo (có cả hai)",
     {"in_epidemic_area": True, "fever_days": 3, "symptoms": ["body_pain", "rash"],
      "warning_signs": ["abdominal_pain"], "severe_signs": ["organ_failure"]},
     "severe", "Nặng ưu tiên cao nhất, đè lên cảnh báo"),

    # ── Lớp 3: Dấu hiệu CẢNH BÁO → warning (vượt cả cổng dịch tễ/sốt) ──
    ("Cảnh báo vượt cổng dịch tễ (không vùng dịch, không sốt)",
     {"in_epidemic_area": False, "fever_days": 0, "warning_signs": ["mucosal_bleeding"]},
     "warning", "Dấu hiệu cảnh báo lâm sàng nguy hiểm bất kể dịch tễ"),
    ("Đủ tiêu chí + 1 dấu hiệu cảnh báo",
     {"in_epidemic_area": True, "fever_days": 3, "symptoms": ["body_pain", "nausea_vomiting"],
      "warning_signs": ["lethargy"]},
     "warning", "SXHD thường + ≥1 cảnh báo → đến viện trong ngày"),

    # ── Lớp 1: Cổng dịch tễ ──
    ("Không vùng dịch, không cảnh báo → none",
     {"in_epidemic_area": False, "fever_days": 3, "symptoms": ["body_pain", "rash"]},
     "none", "Không đủ điều kiện dịch tễ → dừng sớm"),
    ("Vùng dịch nhưng không sốt → none",
     {"in_epidemic_area": True, "fever_days": 0, "symptoms": ["body_pain", "rash"]},
     "none", "Không sốt → không nghi SXHD cấp"),
    ("Sốt 9 ngày (>7) → none",
     {"in_epidemic_area": True, "fever_days": 9, "symptoms": ["body_pain", "rash"]},
     "none", "Sốt >7 ngày không điển hình SXHD cấp"),

    # ── Lớp 2: Triệu chứng cơ bản (cần ≥2) ──
    ("Chỉ 1 triệu chứng cơ bản → none",
     {"in_epidemic_area": True, "fever_days": 3, "symptoms": ["body_pain"]},
     "none", "Chỉ 1/4 triệu chứng (cần ≥2)"),
    ("Đủ 2 triệu chứng, không cảnh báo → mild",
     {"in_epidemic_area": True, "fever_days": 3, "symptoms": ["body_pain", "rash"]},
     "mild", "SXHD thông thường → xét nghiệm CBC"),
    ("3 triệu chứng, không cảnh báo → mild",
     {"in_epidemic_area": True, "fever_days": 2,
      "symptoms": ["body_pain", "rash", "nausea_vomiting"]},
     "mild", "Vẫn mild khi chưa có dấu hiệu cảnh báo"),

    # ── Biên: ranh giới sốt = 7 ngày (≤7 hợp lệ) ──
    ("Sốt đúng 7 ngày (biên ≤7) → mild",
     {"in_epidemic_area": True, "fever_days": 7, "symptoms": ["body_pain", "rash"]},
     "mild", "Ngưỡng ≤7 ngày vẫn nằm trong giai đoạn cấp"),

    # ── Robustness: nhận chuỗi 'true' và đầu vào rác bị lọc ──
    ("Đầu vào dạng chuỗi 'true' + triệu chứng không hợp lệ bị lọc",
     {"in_epidemic_area": "true", "fever_days": "3",
      "symptoms": ["body_pain", "rash", "khong_hop_le"]},
     "mild", "Parser nhận 'true'/'3', loại triệu chứng sai → còn 2 hợp lệ"),
]


def main():
    passed = 0
    print("=" * 72)
    print("BỘ KIỂM THỬ — Sàng lọc Sốt Xuất Huyết (rule-based, QĐ 2760/QĐ-BYT)")
    print("=" * 72)
    for i, (name, args, expected, basis) in enumerate(CASES, 1):
        got = run(args).get("severity")
        ok = got == expected
        passed += ok
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] Ca {i:>2}: {name}")
        print(f"        kỳ vọng={expected:<8} thực tế={got:<8} | {basis}")
        if not ok:
            print(f"        !!! SAI — kiểm tra lại luật")
    print("-" * 72)
    total = len(CASES)
    print(f"KẾT QUẢ: {passed}/{total} ca đạt  ({passed/total*100:.1f}%)")
    print("=" * 72)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
