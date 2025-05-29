import os
from google import genai
from client_proxy import LlmClientProxy, LlmMessage

class GeminiClientProxy(LlmClientProxy):
    __generation_model = "gemini-2.0-flash"
    __embedding_model = "text-embedding-004"

    def __init__(self):
        self.__client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))

    def generate_content(self, prompt: str, chat_history: list[LlmMessage] = [], system_prompt: str | None = None, tools = [], output_object: dict = {}, usage_tracker: dict = {}) -> LlmMessage:
        response = self.__client.models.generate_content(
            model=self.__generation_model,
            prompt=prompt,
        )
        return response.candidates[0].content if response.candidates else ""

    def embed_content(self, content: str | list[str]) -> list[float]:
        if isinstance(content, str):
            content = [content]
        response = self.__client.models.embed_content(model=self.__embedding_model, content=content)
        return response