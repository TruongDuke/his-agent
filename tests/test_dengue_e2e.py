"""
Đánh giá độ chính xác module sàng lọc SXHD (Tầng 2 — E2E qua LLM).
LLM nhận mô tả tiếng Việt tự nhiên → extract triệu chứng → gọi tool → severity.
Chạy: python tests/test_dengue_e2e.py
"""
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI
from tools.dengue.dengue_symptom_assessment import run as dengue_run, ARGS_SCHEMA

_KEY  = os.getenv("ALIBABA_API_KEY", "")
_BASE = os.getenv("ALIBABA_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
_MODEL = os.getenv("ALIBABA_MODEL", "qwen3-vl-plus")
client = OpenAI(api_key=_KEY, base_url=_BASE)

TOOL_DEF = [{
    "type": "function",
    "function": {
        "name": "dengue_symptom_assessment",
        "description": (
            "Phân loại mức độ sốt xuất huyết Dengue dựa trên triệu chứng bệnh nhân. "
            "Gọi tool này khi đã thu thập đủ thông tin về triệu chứng."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "in_epidemic_area": {"type": "boolean", "description": ARGS_SCHEMA["in_epidemic_area"]},
                "fever_days":       {"type": "number",  "description": ARGS_SCHEMA["fever_days"]},
                "symptoms":         {"type": "array", "items": {"type": "string"},
                                     "description": ARGS_SCHEMA["symptoms"]},
                "warning_signs":    {"type": "array", "items": {"type": "string"},
                                     "description": ARGS_SCHEMA["warning_signs"]},
                "severe_signs":     {"type": "array", "items": {"type": "string"},
                                     "description": ARGS_SCHEMA["severe_signs"]},
            },
            "required": ["in_epidemic_area", "fever_days", "symptoms"],
        },
    },
}]

SYSTEM = (
    "Bạn là trợ lý sàng lọc sốt xuất huyết Dengue. "
    "Khi nhận mô tả triệu chứng, hãy phân tích và GỌI NGAY tool dengue_symptom_assessment "
    "với các tham số phù hợp. Không hỏi thêm — hãy suy luận từ thông tin đã có."
)

E2E_CASES = [
    # ── SEVERE ────────────────────────────────────────────────────────────────
    {
        "id": "E-S01", "expected": "severe",
        "description": (
            "Bệnh nhân nam 25 tuổi, sốt 5 ngày ở Đồng Nai (vùng dịch). "
            "Tay chân lạnh, huyết áp tụt, mệt lả không tỉnh táo. Có phát ban đỏ khắp người."
        ),
        "note": "shock_signs rõ ràng",
    },
    {
        "id": "E-S02", "expected": "severe",
        "description": (
            "Trẻ em 8 tuổi, sốt 4 ngày, đang ở TP.HCM. Hôm nay xuất huyết ồ ạt không cầm được, "
            "vàng da, co giật nhẹ. Gia đình rất lo."
        ),
        "note": "severe_bleeding + organ_failure",
    },
    {
        "id": "E-S03", "expected": "severe",
        "description": (
            "Bệnh nhân sốt 6 ngày, vùng Bình Dương. Lơ mơ, không nhận ra người thân, "
            "thở nhanh, môi tím, tay chân lạnh ngắt."
        ),
        "note": "shock + organ failure",
    },

    # ── WARNING ────────────────────────────────────────────────────────────────
    {
        "id": "E-W01", "expected": "warning",
        "description": (
            "Sốt 3 ngày, đang ở Hà Nội gần ổ dịch. Nổi ban đỏ, đau cơ. "
            "Hôm nay nôn liên tục 5-6 lần không dừng được, đau bụng vùng dưới sườn phải."
        ),
        "note": "persistent_vomiting + abdominal_pain",
    },
    {
        "id": "E-W02", "expected": "warning",
        "description": (
            "Tôi bị sốt 4 ngày rồi, sống ở Cần Thơ. Có nổi mẩn đỏ và chấm xuất huyết dưới da. "
            "Sáng nay đánh răng thấy chảy máu chân răng nhiều, nước tiểu cũng ít hơn bình thường."
        ),
        "note": "mucosal_bleeding + oliguria",
    },
    {
        "id": "E-W03", "expected": "warning",
        "description": (
            "Không rõ có vùng dịch không nhưng đang nôn ói liên tục từ tối qua đến giờ, "
            "mệt lả, lờ đờ, không muốn ăn uống gì."
        ),
        "note": "warning_signs bypass epi gate",
    },
    {
        "id": "E-W04", "expected": "warning",
        "description": (
            "Sốt 2 ngày, ở Đà Nẵng. Phát ban toàn thân, đau khắp người. "
            "Lờ đờ không tỉnh táo, bụng đau tức vùng gan."
        ),
        "note": "lethargy + abdominal_pain",
    },

    # ── MILD ──────────────────────────────────────────────────────────────────
    {
        "id": "E-M01", "expected": "mild",
        "description": (
            "Sốt 3 ngày, hiện đang ở Bình Dương. Nổi ban đỏ khắp người, "
            "đau nhức toàn thân, nhức hai hố mắt. Chưa có biểu hiện gì khác."
        ),
        "note": "rash + body_pain, không warning",
    },
    {
        "id": "E-M02", "expected": "mild",
        "description": (
            "Tôi bị sốt từ hôm qua (1 ngày), sống ở Long An gần chỗ có người bị sốt xuất huyết. "
            "Buồn nôn, nổi mẩn đỏ nhưng chưa có gì nặng."
        ),
        "note": "fever_days=1, nausea_vomiting + rash",
    },
    {
        "id": "E-M03", "expected": "mild",
        "description": (
            "Sốt đúng 7 ngày, ở Tiền Giang vùng đang có dịch. Có phát ban, chấm đỏ dưới da. "
            "Không nôn nhiều, không đau bụng, không chảy máu."
        ),
        "note": "fever=7 ranh giới, mild",
    },
    {
        "id": "E-M04", "expected": "mild",
        "description": (
            "Nam 30 tuổi vừa đi Campuchia về (vùng có dịch dengue). Sốt 4 ngày, "
            "buồn nôn, nổi mẩn đỏ ở tay và ngực. Không có dấu hiệu nguy hiểm."
        ),
        "note": "travel history = epi area",
    },

    # ── NONE ──────────────────────────────────────────────────────────────────
    {
        "id": "E-N01", "expected": "none",
        "description": (
            "Tôi bị sốt 3 ngày, đang ở Hà Nội quận Ba Đình, không có ai xung quanh bị sốt xuất huyết. "
            "Nổi mẩn đỏ và đau đầu. Không biết có bị dengue không."
        ),
        "note": "không rõ vùng dịch → none",
    },
    {
        "id": "E-N02", "expected": "none",
        "description": (
            "Hơi mệt, hơi sốt nhẹ khoảng 1 ngày, ở TP.HCM. Chỉ thấy đau đầu nhẹ thôi, "
            "không nổi ban, không nôn."
        ),
        "note": "chỉ 1 symptom (body_pain?), không đủ",
    },
    {
        "id": "E-N03", "expected": "none",
        "description": (
            "Sốt 10 ngày liên tục, ở Đồng Nai vùng dịch. Nổi ban đỏ, đau cơ. "
            "Đã đi khám chưa ra kết quả."
        ),
        "note": "fever > 7 ngày → không điển hình SXHD cấp",
    },
    {
        "id": "E-N04", "expected": "none",
        "description": (
            "Tôi không sốt, chỉ thấy hơi mệt và buồn nôn. Đang ở Bình Dương. "
            "Không biết có phải dengue không?"
        ),
        "note": "không sốt → none",
    },
]


def call_llm_and_get_severity(description: str) -> tuple[str, dict]:
    """Gửi mô tả tự nhiên → LLM extract → gọi tool → trả severity."""
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user",   "content": description},
    ]
    resp = client.chat.completions.create(
        model=_MODEL, messages=messages, tools=TOOL_DEF,
        max_tokens=512, timeout=30,
    )
    choice = resp.choices[0]
    if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
        tc = choice.message.tool_calls[0]
        args = json.loads(tc.function.arguments)
        result = dengue_run(args)
        return result.get("severity", "error"), args
    # LLM không gọi tool
    return "no_tool_call", {}


def run_e2e():
    print("=" * 72)
    print("TẦNG 2 — E2E Test qua LLM")
    print(f"Model: {_MODEL}")
    print("=" * 72)
    print(f"{'ID':<7} {'Expected':<10} {'Actual':<10} {'OK':<4}  Ghi chú")
    print("-" * 72)

    results = []
    by_class = {}

    for tc in E2E_CASES:
        try:
            actual, extracted_args = call_llm_and_get_severity(tc["description"])
        except Exception as e:
            actual, extracted_args = "error", {}
            print(f"  ERROR {tc['id']}: {e}")

        passed = actual == tc["expected"]
        results.append({**tc, "actual": actual, "args": extracted_args, "passed": passed})

        cls = tc["expected"]
        by_class.setdefault(cls, {"total": 0, "pass": 0})
        by_class[cls]["total"] += 1
        if passed:
            by_class[cls]["pass"] += 1

        mark = "✓" if passed else "✗"
        print(f"{tc['id']:<7} {tc['expected']:<10} {actual:<10} {mark:<4}  {tc['note']}")
        time.sleep(0.5)  # tránh rate limit

    total  = len(results)
    passed = sum(1 for r in results if r["passed"])

    print("=" * 72)
    print(f"\nTổng: {passed}/{total} — Accuracy: {passed/total*100:.1f}%\n")

    print("Theo mức độ:")
    for cls in ["severe", "warning", "mild", "none"]:
        s = by_class.get(cls, {"total": 0, "pass": 0})
        if s["total"] == 0:
            continue
        pct = s["pass"] / s["total"] * 100
        tp = s["pass"]
        fp = sum(1 for r in results if r["actual"] == cls and r["expected"] != cls)
        fn = s["total"] - tp
        prec = tp / (tp + fp) * 100 if (tp + fp) > 0 else 0
        rec  = tp / (tp + fn) * 100 if (tp + fn) > 0 else 0
        f1   = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
        print(f"  {cls:<10}: {tp}/{s['total']} ca đúng | Precision {prec:.0f}% | Recall {rec:.0f}% | F1 {f1:.2f}")

    failed = [r for r in results if not r["passed"]]
    if failed:
        print(f"\nPhân tích {len(failed)} ca sai:")
        for r in failed:
            print(f"\n  {r['id']} [{r['expected']} → {r['actual']}]")
            print(f"  Mô tả: {r['description'][:80]}...")
            if r["args"]:
                print(f"  LLM extract: epi={r['args'].get('in_epidemic_area')}, "
                      f"fever={r['args'].get('fever_days')}, "
                      f"symptoms={r['args'].get('symptoms')}, "
                      f"warning={r['args'].get('warning_signs')}, "
                      f"severe={r['args'].get('severe_signs')}")
            print(f"  Nguyên nhân: {r['note']}")

    return passed, total


if __name__ == "__main__":
    run_e2e()
