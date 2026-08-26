"""Biến câu trả lời của agent thành chữ đọc được thành tiếng.

Câu trả lời hiển thị trên màn hình có markdown, emoji, ký hiệu, trích dẫn [1] —
đưa thẳng vào TTS thì nó đọc thành rác. Đo thực tế: chuỗi "**Sàng lọc SXHD:**"
được đọc thành "ASTERIS đồng tham sáng hoạch", và chỗ có ký hiệu thì model bịa chữ.

Hàm này bóc sạch phần trang trí và đổi ký hiệu sang chữ đọc được.
"""

import re

# Viết tắt y khoa — TTS đọc từng chữ cái thành âm vô nghĩa ("SXHD" → "SS Hitale"),
# nên thay bằng cách đọc tiếng Việt trước khi gửi đi.
_ACRONYMS = [
    (r"\bSXHD\b", "sốt xuất huyết"),
    (r"\bSXH\b", "sốt xuất huyết"),
    (r"\bCBC\b", "xét nghiệm công thức máu"),
    (r"\bNS1\b", "en ét một"),
    (r"\bPLT\b", "tiểu cầu"),
    (r"\bWBC\b", "bạch cầu"),
    (r"\bHGB\b", "huyết sắc tố"),
    (r"\bHCT\b", "hematocrit"),
    (r"\bBHYT\b", "bảo hiểm y tế"),
    (r"\bCCCD\b", "căn cước công dân"),
    (r"\bBS\.", "bác sĩ"),
    (r"\bBN\b", "bệnh nhân"),
    (r"\bESI\b", "e ét ai"),
    (r"\bIgM\b", "ai gờ em"),
    (r"\bIgG\b", "ai gờ giê"),
]

# Ký hiệu hay gặp trong câu trả lời y tế → cách đọc
_SYMBOLS = [
    (r"(\d)\s*[–-]\s*(\d)", r"\1 đến \2"),   # 12–24 giờ → 12 đến 24 giờ
    (r"<\s*(\d)", r"dưới \1"),
    (r">\s*(\d)", r"trên \1"),
    (r"≤\s*(\d)", r"tối đa \1"),
    (r"≥\s*(\d)", r"từ \1"),
    (r"\bK/[µμ]L\b", "nghìn trên microlit"),
    (r"\bg/dL\b", "gam trên decilit"),
    (r"\bmg\b", "miligam"),
    (r"\b10\^9/L\b", "nghìn trên microlit"),
    (r"%", " phần trăm"),
    (r"&", " và "),
]


def to_speech(md: str) -> str:
    """Markdown → chữ thuần để TTS đọc."""
    t = md or ""

    t = re.sub(r"```.*?```", " ", t, flags=re.DOTALL)      # khối code
    t = re.sub(r"`([^`]*)`", r"\1", t)                     # code inline
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)            # ảnh
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)         # link → giữ chữ
    t = re.sub(r"\[\d+(?:\s*,\s*\d+)*\]", " ", t)          # trích dẫn [1], [2,3]
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.M)    # tiêu đề
    t = re.sub(r"^\s{0,3}[-*+]\s+", "", t, flags=re.M)     # gạch đầu dòng
    t = re.sub(r"^\s{0,3}>\s?", "", t, flags=re.M)         # trích dẫn khối
    t = re.sub(r"^\s{0,3}[-*_]{3,}\s*$", " ", t, flags=re.M)  # đường kẻ
    t = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", t)         # **đậm** *nghiêng*
    t = re.sub(r"_{2}([^_]+)_{2}", r"\1", t)
    t = re.sub(r"\|", " ", t)                              # bảng

    for pat, rep in _ACRONYMS:
        t = re.sub(pat, rep, t)
    for pat, rep in _SYMBOLS:
        t = re.sub(pat, rep, t)

    # Emoji và ký hiệu linh tinh — TTS đọc bừa hoặc nuốt luôn câu
    t = re.sub(
        "["
        "\U0001F300-\U0001FAFF"   # emoji
        "☀-➿"           # ký hiệu khác
        "️‍"            # bổ trợ emoji
        "]+", " ", t)

    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{2,}", "\n", t)
    return t.strip()


# Kết câu tiếng Việt. Tách để đọc từng câu, phát câu đầu ngay thay vì chờ sinh hết —
# đo được: 1 câu ~0.6-1s, cả đoạn 300 ký tự mất 5.5s.
# KHÔNG cắt ở dấu hai chấm: "Sàng lọc sốt xuất huyết:" tách riêng thành một mẩu cụt,
# đọc lên nghe khựng. Để nó dính vào vế sau thành một câu trọn nghĩa.
_SENT_END = re.compile(r"(?<=[.!?…])\s+|\n+")


def split_sentences(text: str, max_len: int = 180) -> list[str]:
    """Cắt thành từng câu để đọc nối tiếp. Câu quá dài thì cắt tiếp ở dấu phẩy."""
    out: list[str] = []
    for part in _SENT_END.split(text):
        part = part.strip()
        if not part:
            continue
        while len(part) > max_len:
            cut = part.rfind(",", 0, max_len)
            if cut < max_len // 2:
                cut = max_len
            out.append(part[:cut].strip())
            part = part[cut:].lstrip(", ")
        if part:
            out.append(part)
    return out
