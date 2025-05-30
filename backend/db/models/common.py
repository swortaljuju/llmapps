from sqlalchemy import Column, Integer, String, DateTime, Enum, UUID
from sqlalchemy.dialects.postgresql import  ARRAY
from datetime import datetime
import enum
from .base import Base
from .experiment import NewsChunkingExperiment, NewsPreferenceApplicationExperiment
class UserStatus(enum.Enum):
    pending = "pending"
    active = "active"
class MessageType(enum.Enum):
    HUMAN = "human"
    AI = "ai"
    UNKNOWN = "unknown" # not a langchain message

class UserTier(enum.Enum):
    UNLIMITED = "unlimited"
    FULL_EXPERIMENTATION = "full_experimentation"
    BASIC = "basic"
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
    user_tier = Column(Enum(UserTier), default=UserTier.BASIC)
    preferred_news_chunking_experiment = Column(Enum(NewsChunkingExperiment), default=NewsChunkingExperiment.AGGREGATE_DAILY)
    preferred_news_preference_application_experiment = Column(Enum(NewsPreferenceApplicationExperiment), default=NewsPreferenceApplicationExperiment.APPLY_PREFERENCE)
    
class ConversationType(enum.Enum):
    news_preference_survey = "news_preference_survey"  
    
# Only record ai and human conversation history. It won't record system messages or tool calls.
class ConversationHistory(Base):
    __tablename__ = "conversation_history"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, index=True)
    thread_id = Column(String)
    message_id = Column(String)
    parent_message_id = Column(String, nullable=True)
    content =  Column(String) # text content of the message
    message_type = Column(Enum(MessageType), default=MessageType.UNKNOWN)
    created_at = Column(DateTime, default=datetime.now())
    conversation_type = Column(Enum(ConversationType), default=ConversationType.news_preference_survey)