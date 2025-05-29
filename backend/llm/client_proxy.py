from pydantic import BaseModel
from enum import Enum

class LlmMessageType(Enum):
    """
    Enum representing the type of message in a conversation.
    """
    HUMAN = "human"
    AI = "ai"
    SYSTEM = "system"
    TOOL = "tool"
    UNKNOWN = "unknown"  # not a langchain message

class LlmMessage(BaseModel):
    """
    Represents a message in a conversation with its type and content.
    """
    type: LlmMessageType
    text_content: str = ""
    output_object: dict = {}
    tool_calls: list = []
    
class SafeDict(dict):
    def __missing__(self, key):
        return '{' + key + '}'

class LlmClientProxy:
    """
    A proxy class for LLM client to handle requests and responses.
    This class is designed to be extended by specific LLM client implementations.
    """
    def __init__(self, model: str):
        self.model = model

    def generate_content(self, prompt: str, chat_history: list[LlmMessage] = [], system_prompt: str | None = None, tools = [], output_object: dict = {}, usage_tracker: dict = {}) -> LlmMessage:
        raise NotImplementedError("This method should be implemented by subclasses.")
    
    def _inject_chat_history(self, prompt: str, chat_history: list[LlmMessage]) -> str:
        """
        Inject chat history into the prompt.
        This method can be overridden by subclasses to customize how chat history is injected.
        """
        if not chat_history:
            return prompt
        # Check if the prompt contains a placeholder for chat history
        if "{chat_history}" in prompt:
            # Replace the placeholder with the formatted chat history
            history = "\n".join(f"{msg.type.value}: {msg.text_content}" for msg in chat_history)
            return prompt.format_map(SafeDict({'chat_history': history}))
        history = "\n".join(f"{msg.type.value}: {msg.text_content}" for msg in chat_history)
        return f"{history}\n{prompt}"
    
    def embed_content(self, content: str | list[str]) -> list[float]:
        """
        Generate embeddings for the given content.
        This method should be implemented by subclasses.
        """
        raise NotImplementedError("This method should be implemented by subclasses.")