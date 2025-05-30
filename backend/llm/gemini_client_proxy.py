import os
from google.genai import Client, types
from client_proxy import LlmClientProxy, LlmMessage, LlmMessageType, FunctionCallMessage, FunctionResponseMessage
from pydantic import BaseModel
from collections.abc import Callable
from typing import Any
from llm.tracker import LlmTracker
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
        output_object: BaseModel | list[BaseModel] | None = None ) -> LlmMessage:        
        config = types.GenerateContentConfig(response_mime_type="text/plain")
        if output_object:
            config.response_mime_type = "application/json"
            config.response_schema = output_object
        elif tools:
            config.tools = tools
        
        try: 
            response: types.GenerateContentResponse = self.__client.models.generate_content(
                model=self.__generation_model,
                system_prompt=system_prompt,
                contents=self.__generate_contents(prompt, system_prompt),
                config=config
            )
        except Exception as e:
            logger.error(f"Error generating content with Gemini: {e}")
            raise e

        if response.usage_metadata and tracker:
            tracker.log_usage(
                input_token_count=response.usage_metadata.prompt_token_count,
                output_token_count=response.usage_metadata.candidates_token_count
            ) 
        
        return self.__from_response_to_llm_message(response)

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

    def __generate_contents(self, prompt: str | list[LlmMessage], system_prompt: str | None = None) -> list[types.Content]:
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
                    system_prompt = message.text_content or system_prompt
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

    def embed_content(self, contents: list[str]) -> list[list[float]]:
        response = self.__client.models.embed_content(model=self.__embedding_model, contents=contents)
        return response.embeddings