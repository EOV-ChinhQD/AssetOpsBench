from langchain_core.tools import Tool

def rag_search(query: str) -> str:
    """Mock RAG search tool"""
    # TODO: Connect to actual RAG pipeline
    return f"Kết quả từ tài liệu nội bộ cho truy vấn: {query}"

from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool

class RagInput(BaseModel):
    query: str = Field(description="Câu hỏi tìm kiếm tài liệu vận hành")

rag_tool = StructuredTool.from_function(
    name="search_documents",
    description=(
        "Tìm kiếm quy trình vận hành, ngưỡng kỹ thuật, SOP trong tài liệu nội bộ. "
        "Dùng khi câu hỏi liên quan đến quy định, tiêu chuẩn, hướng dẫn vận hành, "
        "mức áp suất cho phép, quy trình xử lý sự cố. "
        "Input: câu hỏi dạng text tiếng Việt."
    ),
    func=rag_search,
    args_schema=RagInput
)
