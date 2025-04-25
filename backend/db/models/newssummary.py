from sqlalchemy import Column, Integer, String, DateTime, Enum, TypeDecorator, Date
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
import enum
from pydantic import BaseModel
import json
from backend.db.models.base import Base

class RssFeed(Base):
    __tablename__ = "rss_feeds"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    feed_url = Column(String, unique=True, index=True)
    last_crawl_time = Column(DateTime, default=datetime.now())
    title = Column(String)
    html_url = Column(String)
    xml_url = Column(String)


class NewsEntry(Base):
    __tablename__ = "news_entries"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    rss_feed_id = Column(Integer)
    entry_rss_guid = Column(String, unique=True, index=True)
    entry_url = Column(String)
    crawl_time = Column(DateTime, default=datetime.now())
    title = Column(String)
    description = Column(String)
    content = Column(String)


class NewsSummaryItem(BaseModel):
    title: str
    content: str
    reference_urls: list[str]
    clicked: bool


# list of news summary items. sorted by ranking from high to low
class NewsSummaryList(BaseModel):
    summary: list[NewsSummaryItem]


class NewsSummaryListPostGreSqlWrapper(TypeDecorator):
    impl = JSONB
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            if isinstance(value, NewsSummaryList):
                return json.loads(value.model_dump_json())
            return value
        return None

    def process_result_value(self, value, dialect):
        if value is not None:
            return NewsSummaryList(**value)
        return None


class NewsSummary(Base):
    __tablename__ = "news_summaries"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer)
    start_date = Column(Date)
    end_date = Column(Date)
    content = Column(NewsSummaryListPostGreSqlWrapper)


class NewsPreferenceChangeCause(enum.Enum):
    survey = "survey"
    user_edit = "user_edit"
    news_click = "news_click"


class NewsPreferenceVersion(Base):
    __tablename__ = "news_preference_versions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer)
    previous_version_id = Column(Integer)  # -1 if no previous version
    content = Column(String)
    cause = Column(Enum(NewsPreferenceChangeCause))
    causal_survey_conversation_history_thread_id = Column(
        String, nullable=True
    )  # survey conversation history which caused the change. empty if no change.
    causal_clicked_news_summary = Column(
        NewsSummaryListPostGreSqlWrapper, nullable=True
    )  # clicked news summary which caused the change. empty if no change.
    created_at = Column(DateTime, default=datetime.now())
