

from enum import Enum
from .gemini_client_proxy import GeminiClientProxy
from .client_proxy import LlmClientProxy

class ModelType(Enum):
    GEMINI = "gemini"

__gemini_client_proxy = None

def get_default_client_proxy() -> LlmClientProxy:
    """
    Factory function to get the default LLM client proxy.
    Currently, it only supports Gemini.
    """
    return get_llm_client_proxy(ModelType.GEMINI)

def get_llm_client_proxy(model_type: ModelType) -> LlmClientProxy:
    """
    Factory function to get the appropriate LLM client proxy based on the model type.
    """
    if model_type == ModelType.GEMINI:
        global __gemini_client_proxy
        if __gemini_client_proxy is None:
            __gemini_client_proxy = GeminiClientProxy()
        return __gemini_client_proxy
    else:
        raise ValueError(f"Unsupported model type: {model_type}")