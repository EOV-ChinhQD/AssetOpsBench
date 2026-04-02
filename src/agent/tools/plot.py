import json
import logging
import asyncio
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from typing import Union

from src.agent.plotting import build_plot_payload

logger = logging.getLogger(__name__)


async def plot_async(dma_id: Union[str, list], include_forecast: bool = False, question: str = "") -> str:
    try:
        payload = build_plot_payload(dma_id, include_forecast, question)
        return json.dumps(payload, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error in Plot Tool: {e}", exc_info=True)
        return f"Lỗi tạo biểu đồ: {str(e)}"

class PlotInput(BaseModel):
    dma_id: str = Field(description="Mã DMA chính xác, hoặc danh sách các mã cách nhau bằng dấu phẩy để vẽ biểu đồ so sánh (ví dụ: '17-TL, 12-PL, 05-BĐ')")
    include_forecast: bool = Field(default=False, description="Có bao gồm dữ liệu dự báo không?")
    question: str = Field(default="", description="Câu hỏi gốc (tùy chọn)")

def plot_sync(dma_id: str, include_forecast: bool = False, question: str = "") -> str:
    return asyncio.run(plot_async(dma_id, include_forecast, question))

plot_tool = StructuredTool.from_function(
    name="plot",
    description="Vẽ biểu đồ tiêu thụ (lịch sử/dự báo). Bắt buộc: dma_id từ get_dma_info. Hỗ trợ biểu đồ Cột (Bar Chart) tự động nếu truyền nhiều DMA.",
    func=plot_sync,
    coroutine=plot_async,
    args_schema=PlotInput
)
