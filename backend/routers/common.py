from pydantic import BaseModel
from enum import Enum

class ChatAuthorType(Enum):
    """
    Enum representing the type of chat author.
    """
    USER = "user"
    AI = "ai"

class ChatMessage(BaseModel):
    """
    Represents a chat message in the conversation history.
    """
    thread_id: str
    message_id: str
    parent_message_id: str | None = None
    content: str
    author: ChatAuthorType