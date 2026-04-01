import json
import os
from typing import Any, List, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage
from langchain_core.outputs import ChatResult, ChatGeneration
from pydantic import Field

from src.llm.litellm import LiteLLMBackend

class LangchainLiteLLM(BaseChatModel):
    """Adapter for LiteLLMBackend to work with LangChain/LangGraph."""
    
    model_id: str
    backend: LiteLLMBackend = Field(exclude=True)
    
    def __init__(self, model_id: str, **kwargs):
        # Always ensure openai/ prefix if calling a local OpenAI-compatible server
        if not model_id.startswith("watsonx/") and not model_id.startswith("openai/"):
             model_id = f"openai/{model_id}"
             
        super().__init__(model_id=model_id, backend=LiteLLMBackend(model_id), **kwargs)
        
    def _generate(self, messages: List[BaseMessage], **kwargs: Any) -> ChatResult:
        import litellm
        llm_messages = [{"role": m.type if m.type != "human" else "user", "content": str(m.content)} for m in messages]
        
        # Register if needed
        if self.model_id not in litellm.model_cost:
            litellm.model_cost[self.model_id] = {"max_tokens": 32768, "input_cost_per_token": 0, "output_cost_per_token": 0}

        kwargs_to_pass = {
            "model": self.model_id,
            "messages": llm_messages,
            "api_key": os.environ.get("LITELLM_API_KEY", "sk-local-vllm"),
            "api_base": os.environ.get("LITELLM_BASE_URL", "http://localhost:8001/v1"),
            "custom_llm_provider": "openai" if self.model_id.startswith("/") or "openai/" in self.model_id else None
        }
        
        if "tools" in self.__dict__ and self.__dict__["tools"]:
             kwargs_to_pass["tools"] = self.__dict__["tools"]

        response = litellm.completion(**kwargs_to_pass)
        return self._process_response(response)

    async def _agenerate(self, messages: List[BaseMessage], **kwargs: Any) -> ChatResult:
        import litellm
        llm_messages = [{"role": m.type if m.type != "human" else "user", "content": str(m.content)} for m in messages]
        
        # Register
        if self.model_id not in litellm.model_cost:
            litellm.model_cost[self.model_id] = {"max_tokens": 32768, "input_cost_per_token": 0, "output_cost_per_token": 0}

        kwargs_to_pass = {
            "model": self.model_id,
            "messages": llm_messages,
            "api_key": os.environ.get("LITELLM_API_KEY", "sk-local-vllm"),
            "api_base": os.environ.get("LITELLM_BASE_URL", "http://localhost:8001/v1"),
            "custom_llm_provider": "openai" if self.model_id.startswith("/") or "openai/" in self.model_id else None
        }
        
        if "tools" in self.__dict__ and self.__dict__["tools"]:
             kwargs_to_pass["tools"] = self.__dict__["tools"]

        response = await litellm.acompletion(**kwargs_to_pass)
        return self._process_response(response)

    def _process_response(self, response: Any) -> ChatResult:
        content = response.choices[0].message.content
        tool_calls = []
        msg = response.choices[0].message
        if hasattr(msg, "tool_calls") and msg.tool_calls is not None:
            for tc in msg.tool_calls:
                tool_calls.append({
                    "name": tc.function.name,
                    "args": json.loads(tc.function.arguments),
                    "id": tc.id
                })
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content or "", tool_calls=tool_calls))])

    @property
    def _llm_type(self) -> str:
        return "litellm_adapter"

    def bind_tools(self, tools: List[Any], **kwargs: Any) -> "LangchainLiteLLM":
        from langchain_core.utils.function_calling import convert_to_openai_tool

        formatted_tools = [convert_to_openai_tool(t) for t in tools]
        new_instance = LangchainLiteLLM(model_id=self.model_id)
        new_instance.__dict__["tools"] = formatted_tools
        return new_instance
