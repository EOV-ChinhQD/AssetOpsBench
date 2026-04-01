import logging
import json
import requests
import os
import time
from typing import Any, List, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langchain_core.outputs import ChatResult, ChatGeneration
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

class LangchainLiteLLM(BaseChatModel):
    model_id: str = "cloudflare/@cf/qwen/qwen3-30b-a3b-fp8"

    def __init__(self, model_id: Optional[str] = None, **kwargs):
        if not model_id:
             model_id = os.environ.get("LLM_MODEL_NAME", self.model_id)
        super().__init__(model_id=model_id, **kwargs)

    @property
    def _llm_type(self) -> str:
        return "vllm_local"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _llm_call(self, messages: List[dict]) -> str:
        if "cloudflare" in self.model_id.lower():
             return self._cloudflare_call(messages)
        else:
             return self._vllm_call(messages)

    def _vllm_call(self, messages: List[dict]) -> str:
        url = os.environ.get("LOCAL_LLM_URL", "http://localhost:8001/v1/chat/completions")
        payload = {
            "model": self.model_id,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 4096
        }
        try:
            resp = requests.post(url, json=payload, timeout=300)
            result = resp.json()
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"vLLM Local Error: {e}")
            # Try once more with model="default"
            payload["model"] = "default"
            try:
                resp = requests.post(url, json=payload, timeout=240)
                return resp.json()["choices"][0]["message"]["content"]
            except:
                return f"Error Local LLM: {str(e)}"

    def _cloudflare_call(self, messages: List[dict]) -> str:
        account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        api_key = os.environ.get("LITELLM_API_KEY")
        pure_model_id = self.model_id.replace("cloudflare/", "")
        
        url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{pure_model_id}"
        payload = {"messages": messages}
        try:
            resp = requests.post(url, headers={"Authorization": f"Bearer {api_key}"}, json=payload, timeout=300)
            res_json = resp.json()
            if res_json.get("success"):
                 inner = res_json["result"]
                 if isinstance(inner, str): return inner
                 return inner.get("response") or inner.get("choices", [{}])[0].get("message", {}).get("content", "")
            return f"Error Cloudflare: {res_json.get('errors')}"
        except Exception as e:
            return f"Error Cloudflare: {str(e)}"

    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, **kwargs: Any) -> ChatResult:
        formatted_messages = []
        for msg in messages:
            role = "user"
            if isinstance(msg, SystemMessage): role = "system"
            elif isinstance(msg, AIMessage): role = "assistant"
            formatted_messages.append({"role": role, "content": msg.content})
            
        content = self._llm_call(formatted_messages)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])

    async def _agenerate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, **kwargs: Any) -> ChatResult:
        import asyncio
        return await asyncio.to_thread(self._generate, messages, stop, **kwargs)
