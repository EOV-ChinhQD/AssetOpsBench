# benchmark_test_suite.py
# Định nghĩa các câu hỏi và ý định mong đợi để đo lường hiệu năng của Agent.

TEST_CASES = [
    # --- GLOBAL queries (Không cần lookup) ---
    {
        "id": "TC001",
        "question": "Hệ thống hiện tại có tổng cộng bao nhiêu mã DMA?",
        "expected_intent": "GLOBAL",
        "expected_tools": ["text_to_sql"]
    },
    {
        "id": "TC002",
        "question": "Vùng nào có lưu lượng tiêu thụ cao nhất tháng 1/2026?",
        "expected_intent": "GLOBAL",
        "expected_tools": ["text_to_sql"]
    },
    
    # --- SPECIFIC queries (BẮT BUỘC lookup-first) ---
    {
        "id": "TC003",
        "question": "DMA Cầu Giấy dự báo tháng tới tiêu thụ bao nhiêu?",
        "expected_intent": "SPECIFIC",
        "expected_tools": ["get_dma_info", "forecast"]
    },
    {
        "id": "TC004",
        "question": "So sánh lưu lượng DMA Hoàng Mai tháng này với tháng trước.",
        "expected_intent": "SPECIFIC",
        "expected_tools": ["get_dma_info", "compare_periods"]
    },
    {
        "id": "TC005",
        "question": "Vẽ biểu đồ tiêu thụ 3 tháng gần nhất của DMA 17-TL.",
        "expected_intent": "SPECIFIC",
        "expected_tools": ["get_dma_info", "historical", "plot"]
    },
    
    # --- HYBRID queries (Phối hợp nhiều nguồn/lọc) ---
    {
        "id": "TC006",
        "question": "Có DMA nào ở quận Hai Bà Trưng bị bất thường trong 7 ngày qua?",
        "expected_intent": "HYBRID",
        "expected_tools": ["text_to_sql"]
    },
    {
        "id": "TC007",
        "question": "Tính tổng dự báo tháng 3 cho toàn vùng Hà Nội Đông.",
        "expected_intent": "HYBRID",
        "expected_tools": ["text_to_sql"]
    }
]

def get_all_test_cases():
    return TEST_CASES
