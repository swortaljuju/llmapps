import os
from google.genai import Client, types
from .client_proxy import LlmClientProxy, LlmMessage, LlmMessageType, FunctionCallMessage, FunctionResponseMessage, EmbeddingTaskType
from pydantic import BaseModel
from collections.abc import Callable
from typing import Any
from .tracker import LlmTracker
from utils.logger import logger
class GeminiClientProxy(LlmClientProxy):
    __generation_model = "gemini-2.0-flash"
    __embedding_model = "text-embedding-004"

    def __init__(self):
        self.__client = Client(api_key=os.getenv("GEMINI_API_KEY", ""))

    def generate_content(self, 
        prompt: str | list[LlmMessage], 
        system_prompt: str | None = None, 
        tracker: LlmTracker  | None = None, 
        tools: list[Callable[..., Any]] = [], 
        output_object: BaseModel | list[BaseModel] | None = None,
        max_retry: int = 0) -> LlmMessage:        
        config = self.__setup_generation_config(system_prompt, tools, output_object)
        success = False
        retry_count = 0
        while not success and retry_count <= max_retry:
            try: 
                response: types.GenerateContentResponse = self.__client.models.generate_content(
                    model=self.__generation_model,
                    contents=self.__generate_contents(prompt, config),
                    config=config
                )
            except Exception as e:
                logger.error(f"Error generating content with Gemini: {e}")
                if retry_count < max_retry:
                    retry_count += 1
                    continue
                raise e
            self.__track_usage(response.usage_metadata, tracker)
            if self.__is_generation_output_unexpected(response, output_object):
                if retry_count < max_retry:
                    retry_count += 1
                    continue
                logger.error(f"Output object is specified but response does not contain parsed content. {response}.")
                raise ValueError("Output object is specified but response does not contain parsed content.")
            success = True
        
        return self.__from_response_to_llm_message(response)
    
    async def generate_content_async(self, 
        prompt: str | list[LlmMessage], 
        system_prompt: str | None = None, 
        tracker: LlmTracker  | None = None, 
        tools: list[Callable[..., Any]] = [], 
        output_object: BaseModel | list[BaseModel] | None = None,
        max_retry: int = 0) -> LlmMessage:   
        config = self.__setup_generation_config(system_prompt, tools, output_object)
        success = False
        retry_count = 0
        while not success and retry_count <= max_retry:
            try: 
                response: types.GenerateContentResponse = await self.__client.aio.models.generate_content(
                    model=self.__generation_model,
                    contents=self.__generate_contents(prompt, config),
                    config=config
                )
            except Exception as e:
                logger.error(f"Error generating content with Gemini: {e}")
                if retry_count < max_retry:
                    retry_count += 1
                    continue
                raise e
            self.__track_usage(response.usage_metadata, tracker)
            if self.__is_generation_output_unexpected(response, output_object):
                if retry_count < max_retry:
                    retry_count += 1
                    continue
                logger.error(f"Output object is specified but response does not contain parsed content. {response}.")
                raise ValueError("Output object is specified but response does not contain parsed content.")
            success = True
        
        return self.__from_response_to_llm_message(response)
    def __is_generation_output_unexpected(self, response: types.GenerateContentResponse,  output_object: BaseModel | list[BaseModel] | None = None) -> bool:
        """
        Check if the response contains valid content.
        This method checks if the response has parsed content or text.
        """
        return output_object and not response.parsed        

    def __track_usage(self, usage_metadata: types.GenerateContentResponseUsageMetadata | None, tracker: LlmTracker | None) -> None:
        if usage_metadata and tracker:
            tracker.log_usage(
                input_token_count=usage_metadata.prompt_token_count,
                output_token_count=usage_metadata.candidates_token_count
            ) 

    def __setup_generation_config(self, 
        system_prompt: str | None = None, 
        tools: list[Callable[..., Any]] = [], 
        output_object: BaseModel | list[BaseModel] | None = None) -> types.GenerateContentConfig:
        config = types.GenerateContentConfig(response_mime_type="text/plain")
        if output_object:
            config.response_mime_type = "application/json"
            config.response_schema = output_object
        elif tools:
            config.tools = tools
        if system_prompt:
            config.system_instruction = system_prompt
        return config
    
    def __from_response_to_llm_message(self, response: types.GenerateContentResponse) -> LlmMessage:
        if response.candidates[0].content.parts[0].function_call:
            function_call_list = []
            for part in response.candidates[0].content.parts:
                if part.function_call:
                    function_call_list.append(FunctionCallMessage(
                        id=part.function_call.id,
                        name=part.function_call.name,
                        args=part.function_call.args or {}
                    ))
            return LlmMessage(
                type=LlmMessageType.FUNCTION_CALL,
                function_call=function_call_list
            )
        elif response.parsed:
            return LlmMessage(
                type=LlmMessageType.STRUCTURED_OUTPUT,
                structured_output=response.parsed
            )
        elif response.text:
            return LlmMessage(
                type=LlmMessageType.AI,
                text_content=response.text
            )
        raise ValueError("Response does not contain valid content")

    def __generate_contents(self, prompt: str | list[LlmMessage], config: types.GenerateContentConfig) -> list[types.Content]:
        contents = []
        if isinstance(prompt, str):
            contents.append(types.Content(role="user", parts=[types.Part(text=prompt)]))
        elif isinstance(prompt, list):
            for message in prompt:
                if message.type == LlmMessageType.HUMAN:
                    contents.append(types.Content(role="user", parts=[types.Part(text=message.text_content or "")]))
                elif message.type == LlmMessageType.AI:
                    contents.append(types.Content(role="model", parts=[types.Part(text=message.text_content or "")]))
                elif message.type == LlmMessageType.SYSTEM:
                    config.system_instruction = message.text_content
                elif message.type == LlmMessageType.FUNCTION_CALL:
                    contents.append(types.Content(
                        role="model", 
                        parts=[types.Part(function_call=types.FunctionCall(
                            name=call.name,
                            args=call.args or {},
                            id=call.id or None
                        )) for call in message.function_call]
                    ))
                elif message.type == LlmMessageType.FUNCTION_RESPONSE:
                    contents.append(types.Content(
                        role="model", 
                        parts=[types.Part(function_response=types.FunctionResponse(
                            name=call.name,
                            response={"output": call.output or None, "error": call.error or None} if call.output or call.error else {},
                            id=call.id or None
                        )) for call in message.function_response]
                    ))
                elif message.type == LlmMessageType.STRUCTURED_OUTPUT:
                    if message.structured_output is not None:
                        contents.append(types.Content(role="model", parts=[types.Part(text=message.structured_output.model_dump_json())]))
                else:
                    raise ValueError("Unknown message type in prompt")
        return contents

    def embed_content(self, contents: list[str], task_type: EmbeddingTaskType) -> list[list[float]]:
        response = self.__client.models.embed_content(model=self.__embedding_model, contents=contents,
                config=types.EmbedContentConfig(task_type=self.__get_embedding_task_type(task_type)))
        return [ embd.values for embd in response.embeddings]
    
    def __get_embedding_task_type(self, task_type: EmbeddingTaskType) -> str:
        """
        Convert the EmbeddingTaskType to the string representation expected by the Gemini API.
        """
        if task_type == EmbeddingTaskType.CLUSTERING:
            return "CLUSTERING"
        elif task_type == EmbeddingTaskType.RETRIEVAL_DOCUMENT:
            return "RETRIEVAL_DOCUMENT"
        elif task_type == EmbeddingTaskType.RETRIEVAL_QUERY:
            return "RETRIEVAL_QUERY"
        else:
            raise ValueError(f"Unsupported embedding task type: {task_type}")
    
    def count_tokens(self,  tokens: str) -> int:
        """
        Count the number of tokens in a string.
        This is a placeholder implementation. Actual token counting logic should be implemented based on the model's tokenizer.
        """
        return self.__client.models.count_tokens(model=self.__generation_model, contents=tokens).total_tokens