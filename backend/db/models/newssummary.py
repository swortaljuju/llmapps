from sqlalchemy import Column, Integer, String, DateTime, Enum, Boolean, Date, Index
from datetime import datetime
import enum
from .base import Base
from sqlalchemy.dialects.postgresql import  ARRAY
from .experiment import NewsChunkingExperiment, NewsPreferenceApplicationExperiment
from pgvector.sqlalchemy import Vector

class RssFeed(Base):
    __tablename__ = "rss_feeds"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    feed_url = Column(String, unique=True, index=True)
    last_crawl_time = Column(DateTime, default=datetime(1970, 1, 1))
    title = Column(String)
    html_url = Column(String)


class NewsEntry(Base):
    __tablename__ = "news_entries"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    rss_feed_id = Column(Integer)
    entry_rss_guid = Column(String)
    # might be empty
    entry_url = Column(String)
    crawl_time = Column(DateTime, default=datetime.now())
    title = Column(String)
    description = Column(String)
    content = Column(String)
    pub_time = Column(DateTime)
    summary_embedding = Column(Vector(768))  # embedding of the content

class NewsSummaryPeriod(enum.Enum):
    # Weekly summary
    weekly = "weekly"
    # Monthly summary
    monthly = "monthly"
class NewsSummaryEntry(Base):
    __tablename__ = "news_summary_entry"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer)
    # summary start date
    start_date = Column(Date)
    # summary end date
    period_type = Column(Enum(NewsSummaryPeriod), default=NewsSummaryPeriod.weekly)
    news_chunking_experiment = Column(Enum(NewsChunkingExperiment), default=NewsChunkingExperiment.AGGREGATE_DAILY)
    news_preference_application_experiment = Column(Enum(NewsPreferenceApplicationExperiment), default=NewsPreferenceApplicationExperiment.WITH_SUMMARIZATION_PROMPT)
    # summarized title from rss feeds title and description
    title = Column(String)
    # Expanded detailed summary of the news either by User or by AI
    content = Column(String)
    # Referenced RSS feeds URLs
    reference_urls = Column(ARRAY(String))
    # If user clicked the news summary
    clicked = Column(Boolean, default=False)  # whether the user clicked this summary
    # The order of the entry in the summary list for a given period by start_date and end_date
    display_order_within_period = Column(Integer)
    
    __table_args__ = (
        Index("logical_key", "user_id", "start_date", "period_type", "news_chunking_experiment", "news_preference_application_experiment", "display_order_within_period", unique=True),
    )
    # TODO add category embeddings up to 3

class NewsSummaryExperimentStats(Base):
    __tablename__ = "news_summary_experiment_stats"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer)
    # summary start date
    start_date = Column(Date)
    # summary end date
    period_type = Column(Enum(NewsSummaryPeriod), default=NewsSummaryPeriod.weekly)
    news_chunking_experiment = Column(Enum(NewsChunkingExperiment), default=NewsChunkingExperiment.AGGREGATE_DAILY)
    news_preference_application_experiment = Column(Enum(NewsPreferenceApplicationExperiment), default=NewsPreferenceApplicationExperiment.WITH_SUMMARIZATION_PROMPT)
    liked = Column(Boolean, default=False)  # whether the user liked this summary
    disliked = Column(Boolean, default=False) # if a summary is shown to the user but not liked, it is considered as disliked

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
    causal_clicked_news_summary_entry_id = Column(
        ARRAY(Integer), nullable=True
    )  # clicked news summary which caused the change. empty if no change.
    created_at = Column(DateTime, default=datetime.now())
