import os
from langchain_google_genai import ChatGoogleGenerativeAI

langchain_gemini_client = ChatGoogleGenerativeAI(
    model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
    google_api_key=os.getenv("GEMINI_API_KEY", ""),
)
