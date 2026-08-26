"""List hospital departments with their specialties."""

TOOL_NAME = "fhir_list_departments"
CATEGORY = "Healthcare"
DESCRIPTION = (
    "Danh sách các khoa khám của bệnh viện + chuyên môn. "
    "Dùng khi bệnh nhân hỏi 'bệnh viện có những khoa nào' hoặc khi cần biết "
    "mapping triệu chứng → khoa."
)
ARGS_SCHEMA = {}


# Chỉ giữ phần triệu chứng ở đây. TÊN khoa lấy từ tools/shared/_departments.py để
# không tồn tại hai bản tên lệch nhau — trước đây file này ghi "Khoa Chấn thương
# Chỉnh hình" còn KB RAG ghi "Khoa Chấn Thương Chỉnh Hình".
_HANDLES = {
    "CARDIO":  ["đau ngực", "khó thở", "huyết áp cao", "đánh trống ngực", "nhồi máu cơ tim", "suy tim"],
    "ENDO":    ["đái tháo đường", "tiểu đường", "khát nước nhiều", "tiểu nhiều", "tuyến giáp", "HbA1c cao"],
    "ENT":     ["nghẹt mũi", "chảy dịch mũi", "viêm xoang", "đau họng", "ù tai", "viêm tai"],
    "NEURO":   ["đau đầu kéo dài", "đau nửa đầu", "chóng mặt", "tê liệt", "co giật", "mất ngủ"],
    "GASTRO":  ["đau bụng", "buồn nôn", "tiêu chảy", "táo bón", "viêm dạ dày", "trào ngược"],
    "RHEUMA":  ["đau khớp", "sưng khớp", "gout", "đau lưng", "viêm khớp", "thoái hóa khớp"],
    "DERMA":   ["mụn", "ngứa", "phát ban", "nấm da", "vảy nến", "dị ứng da"],
    "OBGYN":   ["thai kỳ", "rong kinh", "kinh nguyệt bất thường", "đau bụng dưới nữ", "khám phụ khoa"],
    "PEDIAT":  ["trẻ em", "sốt trẻ em", "tiêm chủng trẻ em", "còi xương"],
    "OPHTHAL": ["mờ mắt", "đau mắt", "nhức mắt", "cườm mắt", "đục thủy tinh thể"],
    "UROLOGY": ["tiểu buốt", "tiểu rắt", "sỏi thận", "suy thận", "tiểu máu"],
    "GENERAL": ["khám tổng quát", "mệt mỏi không rõ nguyên nhân", "kiểm tra sức khỏe định kỳ",
                "sốt kéo dài", "thiếu máu", "sụt cân", "phù chân"],
    "SURGERY": ["chấn thương", "vết thương", "phẫu thuật", "khối u", "bướu", "áp xe", "ruột thừa", "thoát vị"],
    "DENTAL":  ["đau răng", "sâu răng", "nướu", "hàm", "miệng", "nhổ răng", "viêm nướu", "chảy máu chân răng"],
    "PULMO":   ["ho kéo dài", "hen suyễn", "viêm phổi", "khó thở mãn tính", "lao phổi", "tức ngực khi thở", "đờm"],
    "ORTHO":   ["gãy xương", "trật khớp", "đau cột sống", "thoát vị đĩa đệm", "chấn thương thể thao", "đau vai gáy"],
    "INFECT":  ["sốt xuất huyết", "sốt siêu vi", "tay chân miệng", "thủy đậu", "cúm", "bệnh truyền nhiễm"],
    "EMERG":   ["đau ngực dữ dội", "khó thở nặng", "mất ý thức", "chấn thương nặng", "xuất huyết", "ngộ độc"],
}


def _build() -> list[dict]:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
    from _departments import DEPARTMENTS
    return [
        {"code": code, "name": DEPARTMENTS[code], "handles": handles}
        for code, handles in _HANDLES.items()
        if code in DEPARTMENTS
    ]



def run(args: dict) -> dict:
    departments = _build()
    return {
        "count": len(departments),
        "departments": departments,
        "instruction_for_llm": "Trình bày ngay danh sách khoa cho người dùng. KHÔNG hỏi thêm thông tin bệnh nhân.",
    }
