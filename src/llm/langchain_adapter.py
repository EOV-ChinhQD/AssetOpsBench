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
        if not model_id.startswith("watsonx/") and not model_id.startswith("openai/"):
            model_id = f"openai/{model_id}"
        super().__init__(model_id=model_id, backend=LiteLLMBackend(model_id), **kwargs)
        
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        import litellm

        # Convert LangChain messages to LiteLLM format
        llm_messages = []
        for m in messages:
            if m.type == "human": role = "user"
            elif m.type == "ai": role = "assistant"
            elif m.type == "system": role = "system"
            elif m.type == "tool": role = "tool"
            else: role = "user"
            llm_messages.append({"role": role, "content": m.content})
            
        kwargs_to_pass = {
            "model": self.model_id,
            "messages": llm_messages,
            "temperature": 0.0,
        }
        
        if self.model_id.startswith("watsonx/"):
            kwargs_to_pass["api_key"] = os.environ.get("WATSONX_APIKEY")
            kwargs_to_pass["project_id"] = os.environ.get("WATSONX_PROJECT_ID")
        else:
            kwargs_to_pass["api_key"] = os.environ.get("LITELLM_API_KEY")
            kwargs_to_pass["api_base"] = os.environ.get("LITELLM_BASE_URL")
        
        # Handle tools if they were bound via bind_tools
        if "tools" in self.__dict__:
             kwargs_to_pass["tools"] = self.__dict__["tools"]

        response = litellm.completion(**kwargs_to_pass)
        
        content = response.choices[0].message.content
        tool_calls = []
        if hasattr(response.choices[0].message, "tool_calls") and response.choices[0].message.tool_calls:
            for tc in response.choices[0].message.tool_calls:
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
