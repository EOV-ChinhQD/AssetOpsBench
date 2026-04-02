from functools import lru_cache
from typing import Optional

from src.llm.langchain_adapter import LangchainLiteLLM
from src.config.settings import settings


@lru_cache(maxsize=None)
def _cached_llm(model_id: str) -> LangchainLiteLLM:
    return LangchainLiteLLM(model_id=model_id)


def get_llm_for_purpose(purpose: Optional[str] = "default") -> LangchainLiteLLM:
    model_id = settings.LLM_MODEL_NAME
    if purpose == "helper" and getattr(settings, "LLM_AUX_MODEL_NAME", None):
        model_id = settings.LLM_AUX_MODEL_NAME
    return _cached_llm(model_id)
