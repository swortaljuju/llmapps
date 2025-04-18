from sqlalchemy import Column, Integer, String, DateTime, Enum, UUID
from sqlalchemy.dialects.postgresql import  ARRAY
from datetime import datetime
import enum
from backend.db.models.base import Base

class UserStatus(enum.Enum):
    pending = "pending"
    active = "active"

class ChatMessageGeneratorRole(enum.Enum):
    user = "user"
    system = "system"
    unknown = "unknown"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String, unique=True, index=True)
    name = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    created_at = Column(DateTime, default=datetime.now())
    status = Column(Enum(UserStatus), default=UserStatus.pending)
    news_preference = Column(String)
    current_news_preference_version_id = Column(Integer)
    subscribed_rss_feeds_id = Column(ARRAY(Integer))
    
    
class ConversationHistory(Base):
    __tablename__ = "conversation_history"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer)
    thread_id = Column(String)
    message_id = Column(String)
    parent_message_id = Column(String, nullable=True)
    role = Column(Enum(ChatMessageGeneratorRole), default=ChatMessageGeneratorRole.unknown) 
    content =  Column(String)
