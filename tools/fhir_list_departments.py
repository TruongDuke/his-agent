"""List hospital departments with their specialties."""

TOOL_NAME = "fhir_list_departments"
CATEGORY = "Healthcare"
DESCRIPTION = (
    "Danh sách các khoa khám của bệnh viện + chuyên môn. "
    "Dùng khi bệnh nhân hỏi 'bệnh viện có những khoa nào' hoặc khi cần biết "
    "mapping triệu chứng → khoa."
)
ARGS_SCHEMA = {}


_DEPARTMENTS = [
    {"code": "CARDIO",  "name": "Khoa Tim mạch",       "handles": ["đau ngực", "khó thở", "huyết áp cao", "đánh trống ngực", "nhồi máu cơ tim", "suy tim"]},
    {"code": "ENDO",    "name": "Khoa Nội tiết",       "handles": ["đái tháo đường", "tiểu đường", "khát nước nhiều", "tiểu nhiều", "tuyến giáp", "HbA1c cao"]},
    {"code": "ENT",     "name": "Khoa Tai Mũi Họng",   "handles": ["nghẹt mũi", "chảy dịch mũi", "viêm xoang", "đau họng", "ù tai", "viêm tai"]},
    {"code": "NEURO",   "name": "Khoa Thần kinh",      "handles": ["đau đầu kéo dài", "đau nửa đầu", "chóng mặt", "tê liệt", "co giật", "mất ngủ"]},
    {"code": "GASTRO",  "name": "Khoa Tiêu hóa",       "handles": ["đau bụng", "buồn nôn", "tiêu chảy", "táo bón", "viêm dạ dày", "trào ngược"]},
    {"code": "RHEUMA",  "name": "Khoa Cơ Xương Khớp",  "handles": ["đau khớp", "sưng khớp", "gout", "đau lưng", "viêm khớp", "thoái hóa khớp"]},
    {"code": "DERMA",   "name": "Khoa Da liễu",        "handles": ["mụn", "ngứa", "phát ban", "nấm da", "vảy nến", "dị ứng da"]},
    {"code": "OBGYN",   "name": "Khoa Sản Phụ khoa",   "handles": ["thai kỳ", "rong kinh", "kinh nguyệt bất thường", "đau bụng dưới nữ", "khám phụ khoa"]},
    {"code": "PEDIAT",  "name": "Khoa Nhi",            "handles": ["trẻ em", "sốt trẻ em", "tiêm chủng trẻ em", "còi xương"]},
    {"code": "OPHTHAL", "name": "Khoa Mắt",            "handles": ["mờ mắt", "đau mắt", "nhức mắt", "cườm mắt", "đục thủy tinh thể"]},
    {"code": "UROLOGY", "name": "Khoa Thận Tiết niệu", "handles": ["tiểu buốt", "tiểu rắt", "sỏi thận", "suy thận", "tiểu máu"]},
    {"code": "GENERAL", "name": "Khoa Nội tổng quát",  "handles": ["khám tổng quát", "mệt mỏi không rõ nguyên nhân", "kiểm tra sức khỏe định kỳ", "sốt kéo dài", "thiếu máu", "sụt cân", "phù chân"]},
    {"code": "SURGERY", "name": "Khoa Ngoại",           "handles": ["chấn thương", "vết thương", "phẫu thuật", "khối u", "bướu", "áp xe", "ruột thừa", "thoát vị"]},
    {"code": "DENTAL",  "name": "Khoa Răng Hàm Mặt",   "handles": ["đau răng", "sâu răng", "nướu", "hàm", "miệng", "nhổ răng", "viêm nướu", "chảy máu chân răng"]},
    {"code": "PULMO",   "name": "Khoa Hô hấp",         "handles": ["ho kéo dài", "hen suyễn", "viêm phổi", "khó thở mãn tính", "lao phổi", "tức ngực khi thở", "đờm"]},
    {"code": "ORTHO",   "name": "Khoa Chấn thương Chỉnh hình", "handles": ["gãy xương", "trật khớp", "đau cột sống", "thoát vị đĩa đệm", "chấn thương thể thao", "đau vai gáy"]},
    {"code": "EMERG",   "name": "Khoa Cấp cứu",        "handles": ["đau ngực dữ dội", "khó thở nặng", "mất ý thức", "chấn thương nặng", "xuất huyết", "ngộ độc"]},
]


def run(args: dict) -> dict:
    return {
        "count": len(_DEPARTMENTS),
        "departments": _DEPARTMENTS,
        "instruction_for_llm": "Trình bày ngay danh sách khoa cho người dùng. KHÔNG hỏi thêm thông tin bệnh nhân.",
    }
