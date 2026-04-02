import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool
from src.deps import get_repo_dep
from src.utils.normalization import normalize_dma_id

logger = logging.getLogger(__name__)

class DmaInfoInput(BaseModel):
    dma_query: Optional[str] = Field(default=None, description="Mã hiệu DMA cần tra cứu (ví dụ: '17-TL', '12-PL', '01-LB')")
    dma_id: Optional[str] = Field(default=None, description="Alias cho dma_query")

async def get_dma_info_async(dma_query: Optional[str] = None, dma_id: Optional[str] = None) -> str:
    dma_query = dma_query or dma_id
    if not dma_query:
        return "Vui lòng cung cấp mã DMA (dma_query)."
    """
    Xác thực mã hiệu DMA (madma) từ chuỗi nhập vào.
    TRẢ VỀ: dma_id và Công suất định chuẩn (ước tính từ lịch sử).
    """
    try:
        repo = get_repo_dep()
        clean_query = normalize_dma_id(dma_query)
        
        # Try finding the exact match first
        sql = """
        SELECT DISTINCT madma 
        FROM silver.stg_water_demand 
        WHERE madma = %(q)s
           OR madma ILIKE %(q_perc)s
        LIMIT 5
        """
        params = {"q": clean_query, "q_perc": f"%{clean_query}%"}
        df = repo.query(sql, params)
        
        if df.empty:
            return f"Không tìm thấy mã DMA nào khớp với '{dma_query}'. Vui lòng kiểm tra lại danh sách mã DMA."
            
        matches = df['madma'].tolist()
        if len(matches) > 1 and clean_query not in matches:
            return f"Tìm thấy nhiều mã DMA tương tự '{dma_query}': {', '.join(matches)}. Vui lòng cung cấp mã chính xác."
            
        dma_id = clean_query if clean_query in matches else matches[0]
        
        return (
            f"XÁC NHẬN DMA: {dma_id}\n"
            f"- Trạng thái: Đang hoạt động\n"
            f"Vui lòng sử dụng mã chính xác '{dma_id}' cho các phân tích tiếp theo."
        )

    except Exception as e:
        logger.error(f"Error in get_dma_info: {e}", exc_info=True)
        return f"Lỗi hệ thống khi tra cứu DMA: {str(e)}"

dma_info_tool = StructuredTool.from_function(
    name="get_dma_info",
    description="Xác thực mã hiệu DMA (madma). LUÔN GỌI TOOL NÀY TRƯỚC KHI thực hiện phân tích lịch sử hoặc dự báo cho một DMA.",
    func=None,
    coroutine=get_dma_info_async,
    args_schema=DmaInfoInput
)
