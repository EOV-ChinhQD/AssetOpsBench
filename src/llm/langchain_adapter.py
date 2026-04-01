import logging
from typing import Any, List, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langchain_core.outputs import ChatResult, ChatGeneration
from src.llm.unified_client import UnifiedLLMClient
from src.config.settings import settings

logger = logging.getLogger(__name__)

class LangchainLiteLLM(BaseChatModel):
    model_id: str = settings.LLM_MODEL_NAME

    def __init__(self, model_id: Optional[str] = None, **kwargs):
        if not model_id:
             model_id = settings.LLM_MODEL_NAME
        super().__init__(model_id=model_id, **kwargs)
        self._client = UnifiedLLMClient(model_id=model_id)

    @property
    def _llm_type(self) -> str:
        return "unified_llm"

    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, **kwargs: Any) -> ChatResult:
        formatted_messages = []
        for msg in messages:
            role = "user"
            if isinstance(msg, SystemMessage): role = "system"
            elif isinstance(msg, AIMessage): role = "assistant"
            formatted_messages.append({"role": role, "content": msg.content})
            
        content = self._client.generate(formatted_messages)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])

    async def _agenerate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, **kwargs: Any) -> ChatResult:
        import asyncio
        return await asyncio.to_thread(self._generate, messages, stop, **kwargs)
