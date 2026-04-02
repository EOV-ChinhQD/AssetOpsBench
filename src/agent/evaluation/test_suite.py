# 🟢 BỘ TEST CỐT LÕI (5 ATOMIC TOOLS)
# Mục tiêu: Xác nhận từng Tool hoạt động đúng với Database thật.

TEST_CASES = [
    {
        "id": "T1_GET_INFO",
        "question": "Xác thực mã hiệu và trạng thái của trạm 01-LB.",
        "expected_intent": "SPECIFIC",
        "required_tools": ["get_dma_info"]
    },
    {
        "id": "T2_GET_HISTORY",
        "question": "Cho tôi dữ liệu sản lượng lịch sử trong 6 tháng gần đây của trạm 01-LB.",
        "expected_intent": "SPECIFIC",
        "required_tools": ["get_history"]
    },
    {
        "id": "T3_GET_FORECAST",
        "question": "Dự báo sản lượng nước trong 3 tháng tới của trạm 01-LB là bao nhiêu?",
        "expected_intent": "SPECIFIC",
        "required_tools": ["get_forecast"]
    },
    {
        "id": "T4_PLOT_DMA",
        "question": "Vẽ biểu đồ sản lượng tiêu thụ cho trạm 01-LB.",
        "expected_intent": "SPECIFIC",
        "required_tools": ["plot_dma"]
    },
    {
        "id": "T5_TEXT_TO_SQL",
        "question": "Hiện tại toàn hệ thống đang quản lý bao nhiêu trạm DMA?",
        "expected_intent": "GLOBAL",
        "required_tools": ["text_to_sql"]
    }
]

def get_all_test_cases():
    return TEST_CASES

def get_minimal_test_suite():
    return TEST_CASES
