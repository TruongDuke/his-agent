"""Bộ ca kiểm thử RAG gợi ý khoa khám (vector + cosine + weighted voting).

Đánh giá tools/shared/_rag_departments.py bằng 2 chỉ số chuẩn của hệ thống truy hồi:
  - Top-1 accuracy: khoa đúng có phải gợi ý đầu tiên không.
  - Top-3 accuracy: khoa đúng có nằm trong 3 gợi ý không.

Mỗi ca là một câu mô tả triệu chứng kiểu người dùng thật gõ (KHÔNG trùng y
nguyên câu trong knowledge base) → kiểm tra khả năng KHÁI QUÁT của embedding.

Chạy:  python3 tests/test_department_suggestion.py
(Lần đầu sẽ tải model paraphrase-multilingual-MiniLM-L12-v2 ~470MB.)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.shared._rag_departments import retrieve_departments

# (Câu người dùng mô tả, mã khoa đúng kỳ vọng)
CASES = [
    ("tôi hay bị tức ngực và hồi hộp đánh trống ngực khi leo cầu thang", "CARDIO"),
    ("dạo này khát nước liên tục, tiểu nhiều về đêm, sụt cân", "ENDO"),
    ("đau nửa đầu dữ dội kèm chóng mặt mất thăng bằng", "NEURO"),
    ("đau vùng thượng vị, hay ợ chua trào ngược sau khi ăn", "GASTRO"),
    ("khớp gối sưng đau, buổi sáng cứng khớp khó co duỗi", "RHEUMA"),
    ("da nổi mẩn đỏ ngứa nhiều, mọc mụn khắp mặt", "DERMA"),
    ("tôi đang mang thai cần khám thai định kỳ", "OBGYN"),
    ("con tôi 3 tuổi bị sốt cao và quấy khóc", "PEDIAT"),
    ("mắt mờ dần, nhìn xa không rõ và hay nhức mắt", "OPHTHAL"),
    ("đau họng kéo dài, ù tai và nghẹt mũi", "ENT"),
    ("tiểu buốt tiểu rắt, nước tiểu đục", "UROLOGY"),
    ("ho khan kéo dài mấy tuần kèm khó thở", "PULMO"),
    ("sâu răng đau nhức, lợi sưng chảy máu khi đánh răng", "DENTAL"),
    ("bị ngã xe gãy tay, sưng đau biến dạng cổ tay", "ORTHO"),
    ("đột ngột đau ngực dữ dội, vã mồ hôi, khó thở nặng", "EMERG"),
]


def main():
    top1 = top3 = 0
    print("=" * 78)
    print("BỘ KIỂM THỬ — RAG gợi ý khoa khám (vector embedding + cosine)")
    print("=" * 78)
    for i, (query, expected) in enumerate(CASES, 1):
        results = retrieve_departments(query, top_k=3)
        codes = [r["code"] for r in results]
        is_top1 = bool(codes) and codes[0] == expected
        is_top3 = expected in codes
        top1 += is_top1
        top3 += is_top3
        mark = "OK " if is_top3 else "MISS"
        shown = ", ".join(f"{r['code']}({r['score']:.2f})" for r in results) or "(rỗng)"
        print(f"[{mark}] Ca {i:>2}: \"{query[:48]}...\"")
        print(f"        kỳ vọng={expected:<8} top1={'Y' if is_top1 else 'N'}  | gợi ý: {shown}")
    print("-" * 78)
    n = len(CASES)
    print(f"Top-1 accuracy: {top1}/{n}  ({top1/n*100:.1f}%)")
    print(f"Top-3 accuracy: {top3}/{n}  ({top3/n*100:.1f}%)")
    print("=" * 78)


if __name__ == "__main__":
    main()
