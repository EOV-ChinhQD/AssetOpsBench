import logging
from typing import Optional, List, Dict
from pydantic import BaseModel
from langchain_core.tools import StructuredTool

logger = logging.getLogger(__name__)

class ToolMetadata(BaseModel):
    name: str
    is_concurrency_safe: bool = True
    category: str = "FETCH"  # FETCH, SEARCH, WRITE, DANGEROUS
    requires_permission: bool = False
    max_concurrent: Optional[int] = None

class WaterToolRegistry:
    """Central registry to manage water-specific tools and their metadata."""
    def __init__(self):
        self.tools: Dict[str, StructuredTool] = {}
        self.metadata: Dict[str, ToolMetadata] = {}
    
    def register(self, tool: StructuredTool, is_safe: bool = True, category: str = "FETCH"):
        self.tools[tool.name] = tool
        self.metadata[tool.name] = ToolMetadata(
            name=tool.name, 
            is_concurrency_safe=is_safe,
            category=category,
            requires_permission=(category == "DANGEROUS")
        )
    
    def get_tool(self, name: str) -> Optional[StructuredTool]:
        return self.tools.get(name)
    
    def get_metadata(self, name: str) -> Optional[ToolMetadata]:
        return self.metadata.get(name)

    def list_tools(self) -> List[StructuredTool]:
        return list(self.tools.values())

# Global registry instance
registry = WaterToolRegistry()
