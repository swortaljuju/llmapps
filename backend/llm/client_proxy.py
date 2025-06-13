from pydantic import BaseModel
from enum import Enum
from collections.abc import Callable
from typing import Any
from .tracker import LlmTracker
class LlmMessageType(Enum):
    """
    Enum representing the type of message in a conversation.
    """
    HUMAN = "human"
    AI = "ai"
    SYSTEM = "system"
    FUNCTION_CALL = "function_call"
    FUNCTION_RESPONSE = "function_response"
    STRUCTURED_OUTPUT = "structured_output"  # output object
    UNKNOWN = "unknown"
    
class EmbeddingTaskType(Enum):
    """
    Enum representing the type of embedding task.
    """
    CLUSTERING = "clustering"  # embedding for clustering
    RETRIEVAL_DOCUMENT = "retrieval_document"  # embedding for document to be retrieved
    RETRIEVAL_QUERY = "retrieval_query"  # embedding for query to be retrieved
    QUESTION_ANSWERING = "question_answering"  # embedding for question answering

class FunctionCallMessage(BaseModel):
    """
    Represents a function call message in a conversation.
    """
    id: str | None = None  # Unique identifier for the function call from the LLM
    name: str | None = None  # Name of the function to be called
    args: dict[str, Any] | None = None  # Arguments for the function call, if any

class FunctionResponseMessage(BaseModel):
    """
    Represents a function response message in a conversation.
    """
    id: str | None = None  # Unique identifier for the function response from the LLM
    name: str | None = None  # Name of the function that was called
    output: str | None = None  # response from the function call, if any
    error: str | None = None  # error message if the function call failed

class LlmMessage(BaseModel):
    """
    Represents a message in a conversation with its type and content.
    """
    type: LlmMessageType
    text_content: str = None
    structured_output: BaseModel | list[BaseModel] | None = None
    function_call: FunctionCallMessage = None
    function_response: FunctionResponseMessage = None

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

    def generate_content(self, 
                        prompt: str | list[LlmMessage], 
                        system_prompt: str | None = None, 
                        tracker: LlmTracker  | None = None, 
                        tools: list[Callable[..., Any]] = [], 
                        tool_schemas: list[BaseModel] = [],
                        output_object: BaseModel | list[BaseModel] | None = None,
                        max_retry: int = 0 ) -> list[LlmMessage]:
        """
        Interface for generating content
        Args:
            prompt (str | list[LlmMessage]): single prompt or chat history where last message is the latest user message.
            system_prompt (str | None, optional): System prompt 
            tracker LlmTracker: llm tracker.
            tools (list, optional): functions to be called by the LLM. Defaults to [], Assume the function will be automatically executed.
            tool_schemas (list[BaseModel]): schemas for the tools defined as pydantic model.
            output_object (dict, optional): Output pydantic model to be returned by the LLM. Defaults to None.
            max_retry (int, optional): Maximum number of retries for the generation. Defaults to 0.
        Raises:
            NotImplementedError: _description_

        Returns:
            LlmMessage: _description_
        """
        raise NotImplementedError("This method should be implemented by subclasses.")
    
    async def generate_content_async(self, 
                        prompt: str | list[LlmMessage], 
                        system_prompt: str | None = None, 
                        tracker: LlmTracker  | None = None, 
                        tools: list[Callable[..., Any]] = [], 
                        tool_schemas: list[BaseModel] = [],
                        output_object: BaseModel | list[BaseModel] | None = None,
                        max_retry: int = 0) -> list[LlmMessage]:
        """
        Interface for generating content
        Args:
            prompt (str | list[LlmMessage]): single prompt or chat history where last message is the latest user message.
            system_prompt (str | None, optional): System prompt 
            tracker LlmTracker: llm tracker.
            tools (list, optional): functions to be called by the LLM. Defaults to [], Assume the function will be automatically executed.
            tool_schemas (list[BaseModel]): schemas for the tools defined as pydantic model.
            output_object (dict, optional): Output pydantic model to be returned by the LLM. Defaults to None.
            max_retry (int, optional): Maximum number of retries for the generation. Defaults to 0.
        Raises:
            NotImplementedError: _description_

        Returns:
            LlmMessage: _description_
        """
        raise NotImplementedError("This method should be implemented by subclasses.")
    
    def embed_content(self, contents: list[str], task_type: EmbeddingTaskType) -> list[list[float]]:
        """
        Generate embeddings for the given content.
        This method should be implemented by subclasses.
        """
        raise NotImplementedError("This method should be implemented by subclasses.")
    
    def count_tokens(self,  tokens: str) -> int:
        """
        Count the number of tokens in the given content.
        This method should be implemented by subclasses.
        """
        raise NotImplementedError("This method should be implemented by subclasses.")