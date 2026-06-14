"""
Đánh giá độ chính xác module sàng lọc SXHD (Tầng 1 — Unit test logic).
Chạy: python tests/test_dengue_symptom.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tools.dengue.dengue_symptom_assessment import run

TEST_CASES = [
    # ── SEVERE (4 ca) ──────────────────────────────────────────────────────────
    {
        "id": "S01", "label": "Sốc rõ ràng — severe",
        "input": {"in_epidemic_area": True, "fever_days": 4,
                  "symptoms": ["rash", "body_pain"],
                  "severe_signs": ["shock_signs"]},
        "expected": "severe",
        "note": "shock_signs → severe ngay, bypass warning check",
    },
    {
        "id": "S02", "label": "Suy tạng — severe",
        "input": {"in_epidemic_area": True, "fever_days": 5,
                  "symptoms": ["rash", "skin_bleeding"],
                  "severe_signs": ["organ_failure"]},
        "expected": "severe",
        "note": "organ_failure → severe",
    },
    {
        "id": "S03", "label": "Xuất huyết ồ ạt — severe",
        "input": {"in_epidemic_area": False, "fever_days": 0,
                  "symptoms": [],
                  "severe_signs": ["severe_bleeding"]},
        "expected": "severe",
        "note": "severe_signs bypass tất cả gate kể cả epi và fever",
    },
    {
        "id": "S04", "label": "Đa dấu hiệu nặng — severe",
        "input": {"in_epidemic_area": True, "fever_days": 6,
                  "symptoms": ["rash", "skin_bleeding", "nausea_vomiting"],
                  "warning_signs": ["abdominal_pain", "persistent_vomiting"],
                  "severe_signs": ["shock_signs", "organ_failure"]},
        "expected": "severe",
        "note": "severe trumps warning",
    },

    # ── WARNING (5 ca) ─────────────────────────────────────────────────────────
    {
        "id": "W01", "label": "Warning có dịch tễ — warning",
        "input": {"in_epidemic_area": True, "fever_days": 4,
                  "symptoms": ["rash", "skin_bleeding"],
                  "warning_signs": ["persistent_vomiting"]},
        "expected": "warning",
        "note": "đủ điều kiện epi + fever + symptoms + warning_sign",
    },
    {
        "id": "W02", "label": "Warning bypass epi — warning",
        "input": {"in_epidemic_area": False, "fever_days": 2,
                  "symptoms": ["rash"],
                  "warning_signs": ["mucosal_bleeding"]},
        "expected": "warning",
        "note": "warning_signs bypass epi gate theo QĐ 2760",
    },
    {
        "id": "W03", "label": "Chảy máu niêm mạc + đau bụng — warning",
        "input": {"in_epidemic_area": True, "fever_days": 3,
                  "symptoms": ["rash", "body_pain"],
                  "warning_signs": ["mucosal_bleeding", "abdominal_pain"]},
        "expected": "warning",
        "note": "2 warning signs",
    },
    {
        "id": "W04", "label": "Lờ đờ + tiểu ít — warning",
        "input": {"in_epidemic_area": True, "fever_days": 5,
                  "symptoms": ["nausea_vomiting", "skin_bleeding"],
                  "warning_signs": ["lethargy", "oliguria"]},
        "expected": "warning",
        "note": "lethargy + oliguria = warning nghiêm trọng",
    },
    {
        "id": "W05", "label": "Warning không sốt nhưng có warning sign — warning",
        "input": {"in_epidemic_area": True, "fever_days": 0,
                  "symptoms": [],
                  "warning_signs": ["persistent_vomiting", "mucosal_bleeding"]},
        "expected": "warning",
        "note": "warning_signs bypass fever gate",
    },

    # ── MILD (5 ca) ────────────────────────────────────────────────────────────
    {
        "id": "M01", "label": "SXHD nhẹ điển hình — mild",
        "input": {"in_epidemic_area": True, "fever_days": 3,
                  "symptoms": ["rash", "body_pain"]},
        "expected": "mild",
        "note": "đủ epi + fever + ≥2 symptoms, không warning",
    },
    {
        "id": "M02", "label": "Đủ 4 triệu chứng cơ bản, không warning — mild",
        "input": {"in_epidemic_area": True, "fever_days": 2,
                  "symptoms": ["rash", "body_pain", "nausea_vomiting", "skin_bleeding"]},
        "expected": "mild",
        "note": "4/4 symptoms nhưng không có warning_signs",
    },
    {
        "id": "M03", "label": "Sốt ngày 7 (ranh giới) — mild",
        "input": {"in_epidemic_area": True, "fever_days": 7,
                  "symptoms": ["nausea_vomiting", "rash"]},
        "expected": "mild",
        "note": "fever_days=7 vẫn hợp lệ (≤7), không phải none",
    },
    {
        "id": "M04", "label": "Đúng 2 triệu chứng (ranh giới) — mild",
        "input": {"in_epidemic_area": True, "fever_days": 4,
                  "symptoms": ["skin_bleeding", "rash"]},
        "expected": "mild",
        "note": "đúng ngưỡng tối thiểu ≥2 symptoms",
    },
    {
        "id": "M05", "label": "Sốt ngày 1 — mild",
        "input": {"in_epidemic_area": True, "fever_days": 1,
                  "symptoms": ["rash", "nausea_vomiting"]},
        "expected": "mild",
        "note": "sốt ngày đầu, đủ điều kiện mild",
    },

    # ── NONE (6 ca) ────────────────────────────────────────────────────────────
    {
        "id": "N01", "label": "Không ở vùng dịch — none",
        "input": {"in_epidemic_area": False, "fever_days": 3,
                  "symptoms": ["rash", "body_pain"]},
        "expected": "none",
        "note": "fail epi gate",
    },
    {
        "id": "N02", "label": "Không sốt — none",
        "input": {"in_epidemic_area": True, "fever_days": 0,
                  "symptoms": ["rash", "body_pain"]},
        "expected": "none",
        "note": "fever_days=0 → fail fever gate",
    },
    {
        "id": "N03", "label": "Sốt quá 7 ngày — none",
        "input": {"in_epidemic_area": True, "fever_days": 8,
                  "symptoms": ["rash", "body_pain"]},
        "expected": "none",
        "note": "fever_days>7 không điển hình SXHD cấp",
    },
    {
        "id": "N04", "label": "Chỉ 1 triệu chứng — none",
        "input": {"in_epidemic_area": True, "fever_days": 4,
                  "symptoms": ["rash"]},
        "expected": "none",
        "note": "chỉ 1/4 symptoms (cần ≥2)",
    },
    {
        "id": "N05", "label": "Không triệu chứng — none",
        "input": {"in_epidemic_area": True, "fever_days": 3,
                  "symptoms": []},
        "expected": "none",
        "note": "0 symptoms",
    },
    {
        "id": "N06", "label": "Không dịch tễ, không sốt, không triệu chứng — none",
        "input": {"in_epidemic_area": False, "fever_days": 0,
                  "symptoms": []},
        "expected": "none",
        "note": "fail tất cả gate",
    },
]


def run_tests():
    results = []
    for tc in TEST_CASES:
        output = run(tc["input"])
        actual = output.get("severity")
        passed = actual == tc["expected"]
        results.append({**tc, "actual": actual, "passed": passed})

    # ── In kết quả ──
    print("=" * 70)
    print(f"{'ID':<5} {'Label':<40} {'Expected':<10} {'Actual':<10} {'OK'}")
    print("-" * 70)

    by_class = {}
    for r in results:
        cls = r["expected"]
        by_class.setdefault(cls, {"total": 0, "pass": 0})
        by_class[cls]["total"] += 1
        mark = "✓" if r["passed"] else "✗"
        if r["passed"]:
            by_class[cls]["pass"] += 1
        print(f"{r['id']:<5} {r['label']:<40} {r['expected']:<10} {r['actual']:<10} {mark}")

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    print("=" * 70)
    print(f"\nTổng: {passed}/{total} ca đúng — Accuracy: {passed/total*100:.1f}%\n")

    print("Theo mức độ:")
    for cls in ["severe", "warning", "mild", "none"]:
        s = by_class.get(cls, {"total": 0, "pass": 0})
        pct = s["pass"] / s["total"] * 100 if s["total"] else 0
        print(f"  {cls:<10}: {s['pass']}/{s['total']} ({pct:.0f}%)")

    failed = [r for r in results if not r["passed"]]
    if failed:
        print("\nCa sai:")
        for r in failed:
            print(f"  {r['id']} — {r['label']}")
            print(f"    Expected: {r['expected']}, Actual: {r['actual']}")
            print(f"    Note: {r['note']}")

    return passed, total


if __name__ == "__main__":
    run_tests()
