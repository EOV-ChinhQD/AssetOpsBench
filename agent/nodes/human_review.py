import logging
from ..state import AgentState

logger = logging.getLogger(__name__)

async def human_review(state: AgentState) -> dict:
    """
    Node này chuẩn bị dữ liệu SQL để hiển thị cho người dùng phê duyệt.
    Hiện tại tạm thời bỏ qua bước sinh SQL trước để đơn giản hóa flow không dùng Vanna.
    """
    # Simply pass through for now to avoid Vanna dependency
    return state
