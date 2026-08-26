"""Bảng khoa chuẩn của bệnh viện + chuẩn hóa tên/mã khoa về mã.

Vì sao có file này:

Các tool đặt lịch tra Schedule bằng `service-type=urn:vn:department|<MÃ>`, nên chỉ
chấp nhận MÃ khoa. Nhưng LLM nói chuyện với bệnh nhân bằng TÊN khoa, và
fhir_triage_assessment lại cấm hiển thị mã mà không đưa tên thay thế — kết quả là
LLM tự nghĩ ra tên ("Khoa Chấn Thương – Xương Khớp", ghép ORTHO với RHEUMA) rồi
truyền chính cái tên bịa đó vào tool tìm slot. Tool không tìm ra Schedule, báo lỗi
chung chung, LLM không tự sửa được và xin lỗi bệnh nhân.

File này là nguồn sự thật duy nhất cho cặp mã ↔ tên, cộng resolve() nhận cả hai
dạng. Khi không chắc thì trả về ambiguous kèm danh sách ứng viên, KHÔNG đoán —
đẩy bệnh nhân gãy xương sang khoa Cơ Xương Khớp còn tệ hơn là hỏi lại.

Tên khoa lấy theo `display` phổ biến nhất trên Aidbox, khớp với
tools/knowledge_base/symptoms_departments.json (nguồn RAG).
"""
from __future__ import annotations

import unicodedata

# Mã khoa → tên hiển thị cho bệnh nhân.
DEPARTMENTS: dict[str, str] = {
    "EMERG":   "Khoa Cấp cứu",
    "CARDIO":  "Khoa Tim Mạch",
    "ENDO":    "Khoa Nội Tiết",
    "NEURO":   "Khoa Thần Kinh",
    "GASTRO":  "Khoa Tiêu Hóa",
    "RHEUMA":  "Khoa Cơ Xương Khớp",
    "DERMA":   "Khoa Da Liễu",
    "OBGYN":   "Khoa Sản Phụ Khoa",
    "PEDIAT":  "Khoa Nhi",
    "OPHTHAL": "Khoa Mắt",
    "ENT":     "Khoa Tai Mũi Họng",
    "UROLOGY": "Khoa Thận Tiết Niệu",
    "GENERAL": "Khoa Nội Tổng Quát",
    "SURGERY": "Khoa Ngoại",
    "DENTAL":  "Khoa Răng Hàm Mặt",
    "PULMO":   "Khoa Hô Hấp",
    "ORTHO":   "Khoa Chấn Thương Chỉnh Hình",
    "INFECT":  "Khoa Truyền Nhiễm",
}

# Cách gọi khác mà bệnh nhân/LLM hay dùng, không suy ra được từ tên chuẩn.
_ALIASES: dict[str, str] = {
    "cap cuu": "EMERG",
    "cuu thuong": "EMERG",
    "chinh hinh": "ORTHO",
    "chan thuong chinh hinh": "ORTHO",
    "co xuong khop": "RHEUMA",
    "xuong khop": "RHEUMA",
    "khop": "RHEUMA",
    "noi tong quat": "GENERAL",
    "noi khoa": "GENERAL",
    "tong quat": "GENERAL",
    "ngoai khoa": "SURGERY",
    "san phu khoa": "OBGYN",
    "phu khoa": "OBGYN",
    "tai mui hong": "ENT",
    "rang ham mat": "DENTAL",
    "nha khoa": "DENTAL",
    "than tiet nieu": "UROLOGY",
    "tiet nieu": "UROLOGY",
    "ho hap": "PULMO",
    "phoi": "PULMO",
    "tim mach": "CARDIO",
    "noi tiet": "ENDO",
    "than kinh": "NEURO",
    "tieu hoa": "GASTRO",
    "da lieu": "DERMA",
    "mat": "OPHTHAL",
    "nhi": "PEDIAT",
    "nhi khoa": "PEDIAT",
    "truyen nhiem": "INFECT",

    # Tên tiếng Anh / viết tắt LLM hay dùng. Gom về đây từ bảng alias cục bộ
    # trong fhir_get_available_slots — bảng đó chỉ một tool có, và map sai
    # "orthopedics" -> RHEUMA (đẩy ca gãy xương sang khoa Cơ Xương Khớp).
    "pediatrics": "PEDIAT", "pediatric": "PEDIAT",
    "cardiology": "CARDIO", "timm": "CARDIO",
    "endocrinology": "ENDO", "endocrine": "ENDO",
    "otolaryngology": "ENT", "tmh": "ENT",
    "neurology": "NEURO", "neuroscience": "NEURO",
    "gastroenterology": "GASTRO", "gi": "GASTRO",
    "rheumatology": "RHEUMA",
    "dermatology": "DERMA",
    "obstetrics": "OBGYN", "gynecology": "OBGYN", "ob": "OBGYN",
    "ophthalmology": "OPHTHAL",
    "nephrology": "UROLOGY", "urol": "UROLOGY", "urology": "UROLOGY",
    "internal": "GENERAL", "noitonquat": "GENERAL",
    "surgical": "SURGERY", "surgery": "SURGERY",
    "dentistry": "DENTAL", "dental oral": "DENTAL",
    "pulmonology": "PULMO", "respiratory": "PULMO",
    "orthopedic": "ORTHO", "orthopedics": "ORTHO", "orthopaedics": "ORTHO",
    "traumatology": "ORTHO",
    "emergency": "EMERG", "er": "EMERG",
    "infectious": "INFECT",
}

_STOPWORDS = {"khoa", "phong", "ban", "bo", "mon"}


def _fold(s: str) -> str:
    """Bỏ dấu, hạ chữ thường, gom mọi ký tự không phải chữ/số thành một space.

    Gom cả dấu gạch nối lẫn en-dash: LLM viết "Chấn Thương – Xương Khớp" với en-dash,
    tách bằng split() thường sẽ dính dấu vào token.
    """
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("đ", "d").replace("Đ", "D")
    out = []
    for ch in s.lower():
        out.append(ch if ch.isalnum() else " ")
    return " ".join("".join(out).split())


def _tokens(s: str) -> set[str]:
    return {t for t in _fold(s).split() if t not in _STOPWORDS}


# Dựng sẵn để resolve() không phải tính lại mỗi lần gọi.
_BY_FOLDED_NAME = {_fold(name): code for code, name in DEPARTMENTS.items()}
_NAME_TOKENS = {code: _tokens(name) for code, name in DEPARTMENTS.items()}


def valid_codes() -> str:
    """Chuỗi 'MÃ (Tên)' để nhét vào thông báo lỗi cho LLM tự sửa."""
    return ", ".join(f"{code} ({name})" for code, name in DEPARTMENTS.items())


def resolve(raw: str) -> dict:
    """Chuẩn hóa mã hoặc tên khoa về mã.

    Trả một trong ba dạng:
      {"code": "ORTHO", "name": "Khoa Chấn Thương Chỉnh Hình"}
      {"ambiguous": ["ORTHO", "RHEUMA"]}   — khớp mơ hồ, phải hỏi lại
      {"unknown": "<chuỗi gốc>"}           — không khớp gì
    """
    raw = str(raw or "").strip()
    if not raw:
        return {"unknown": raw}

    # 1. Đúng mã khoa
    code = raw.upper()
    if code in DEPARTMENTS:
        return {"code": code, "name": DEPARTMENTS[code]}

    folded = _fold(raw)

    # 2. Đúng tên khoa (không phân biệt hoa thường/dấu)
    if folded in _BY_FOLDED_NAME:
        c = _BY_FOLDED_NAME[folded]
        return {"code": c, "name": DEPARTMENTS[c]}

    # 3. Cách gọi quen
    if folded in _ALIASES:
        c = _ALIASES[folded]
        return {"code": c, "name": DEPARTMENTS[c]}
    stripped = " ".join(t for t in folded.split() if t not in _STOPWORDS)
    if stripped in _ALIASES:
        c = _ALIASES[stripped]
        return {"code": c, "name": DEPARTMENTS[c]}

    # 4. Khớp một phần theo token. Chỉ nhận khi có duy nhất một khoa trùng nhiều
    #    token nhất — trùng ngang nhau nghĩa là tên đầu vào nằm giữa hai khoa
    #    (đúng ca "Chấn Thương – Xương Khớp" đứng giữa ORTHO và RHEUMA).
    want = _tokens(raw)
    if not want:
        return {"unknown": raw}

    scored: dict[str, int] = {}
    for c, toks in _NAME_TOKENS.items():
        overlap = len(want & toks)
        if overlap:
            scored[c] = overlap
    if not scored:
        return {"unknown": raw}

    best = max(scored.values())
    winners = [c for c, n in scored.items() if n == best]

    # Trùng 1 token thì quá yếu để đoán, trừ khi tên khoa vốn chỉ có 1 token
    # ("Khoa Mắt", "Khoa Nhi", "Khoa Ngoại").
    if len(winners) == 1:
        c = winners[0]
        if best >= 2 or len(_NAME_TOKENS[c]) == 1:
            return {"code": c, "name": DEPARTMENTS[c]}
        return {"unknown": raw}

    return {"ambiguous": sorted(winners)}


def resolve_or_error(raw: str, arg_name: str = "department") -> tuple[str, str, dict | None]:
    """Bọc resolve() thành dạng tool dùng trực tiếp.

    Trả (code, name, error_dict). error_dict là None khi thành công; ngược lại là
    dict trả thẳng về cho LLM, kèm hướng dẫn sửa để nó gọi lại đúng ngay lượt sau
    thay vì xin lỗi bệnh nhân.
    """
    r = resolve(raw)

    if "code" in r:
        return r["code"], r["name"], None

    if "ambiguous" in r:
        cands = ", ".join(f"{c} ({DEPARTMENTS[c]})" for c in r["ambiguous"])
        return "", "", {
            "error": "ambiguous_department",
            "received": str(raw),
            "candidates": r["ambiguous"],
            "message": (
                f"Tên khoa '{raw}' khớp với nhiều khoa: {cands}. "
                "KHÔNG được tự chọn — hỏi lại bệnh nhân muốn khoa nào, rồi gọi lại "
                f"tool với {arg_name} là MÃ khoa."
            ),
        }

    return "", "", {
        "error": "unknown_department",
        "received": str(raw),
        "message": (
            f"Không có khoa nào tên/mã là '{raw}'. Gọi lại tool với {arg_name} là MÃ khoa "
            f"trong danh sách sau: {valid_codes()}. "
            "TUYỆT ĐỐI KHÔNG tự nghĩ ra tên khoa — nếu chưa biết khoa nào thì gọi "
            "fhir_suggest_department trước."
        ),
    }
