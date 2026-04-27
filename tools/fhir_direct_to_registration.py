"""Placeholder for new patient registration — directs to front-desk (for Sprint 1).

Sprint 2 will replace this with a real Patient resource creation tool
(fhir_register_new_patient) that collects name, DOB, phone, BHYT, address.
"""

TOOL_NAME = "fhir_direct_to_registration"
CATEGORY = "Healthcare"
DESCRIPTION = (
    "CHỈ dùng khi hệ thống gặp lỗi kỹ thuật không thể đăng ký được. "
    "KHÔNG dùng khi bệnh nhân chưa có hồ sơ — hãy dùng fhir_register_new_patient thay thế. "
    "Hệ thống hỗ trợ đăng ký bệnh nhân mới trực tuyến đầy đủ qua fhir_register_new_patient."
)
ARGS_SCHEMA = {}


def run(args: dict) -> dict:
    return {
        "action": "direct_to_registration",
        "message": (
            "Bạn chưa có hồ sơ tại bệnh viện. Vui lòng đến quầy ĐĂNG KÝ BỆNH NHÂN MỚI "
            "(tầng 1, cạnh cổng chính) để làm thủ tục. Mang theo:\n"
            "  - Thẻ BHYT (nếu có)\n"
            "  - CCCD/CMND\n"
            "  - Sổ khám sức khỏe cũ (nếu có)\n"
            "\n"
            "Sau khi đăng ký xong, bạn có thể đặt lịch khám qua trợ lý AI này hoặc trực tiếp tại quầy lễ tân."
        ),
        "location": "Quầy Đăng ký Bệnh nhân mới — Tầng 1, cạnh cổng chính",
        "required_documents": ["CCCD/CMND", "Thẻ BHYT (nếu có)", "Sổ khám cũ (nếu có)"],
    }
