from fastapi import APIRouter, HTTPException, Request, UploadFile, Form
from typing import Optional
from pydantic import BaseModel
from db import db
from db.models import (
    User,
    NewsPreferenceChangeCause,
    NewsPreferenceVersion,
    RssFeed,
    NewsPreferenceApplicationExperiment,
    NewsSummaryPeriod,
    NewsSummaryExperimentStats,
    NewsSummaryEntry,
    NewsChunkingExperiment,
)
from utils.manage_session import GetUserInSession
import os
from llm.news_preference_agent import (
    load_preference_survey_history,
    save_answer_and_generate_next_question,
    ApiConversationHistoryItem,
    load_subscribed_rss_feed_list_for_preference_prompt
)
from .common import ChatMessage, ChatAuthorType
from utils.manage_session import limit_usage
from typing import Annotated
import xml.etree.ElementTree as ET
from utils.logger import logger
from utils.rss import is_valid_rss_feed
from constants import MAX_RSS_SUBSCRIPTION
from enum import Enum
from llm.client_proxy import LlmMessageType
from llm.news_summary_agent import (
    summarize_news, expand_news_summary)
from utils.date_helper import get_current_week_start_date, format_date, parse_date
import enum

DOMAIN = os.getenv("DOMAIN", "localhost:3000")


router = APIRouter(prefix="/api/py/news_summary", tags=["news_summary"])

class NewsSummaryPeriod(BaseModel):
    start_date_timestamp: int  # Timestamp in seconds
    end_date_timestamp: int  # Timestamp in seconds
    id: int

class ApiRssFeed(BaseModel):
    id: int | None = None
    title: str
    feed_url: str

class NewsSummaryUiMode(Enum):
    COLLECT_RSS_FEEDS = "collect_rss_feeds"
    COLLECT_NEWS_PREFERENCE = "collect_news_preference"
    SHOW_SUMMARY = "show_summary"

class ApiNewsSummaryEntry(BaseModel):
    id: int
    title: str
    content: str
    expanded_content: Optional[str] = None
    reference_urls: list[str] = []
    display_order: int = 0

class NewsSummaryOptions(BaseModel):
    news_chunking_experiment: NewsChunkingExperiment = NewsChunkingExperiment.AGGREGATE_DAILY
    news_preference_application_experiment: NewsPreferenceApplicationExperiment = NewsPreferenceApplicationExperiment.APPLY_PREFERENCE
    period_type: NewsSummaryPeriod = NewsSummaryPeriod.weekly

class NewsSummaryInitializeResponse(BaseModel):
    mode: NewsSummaryUiMode      
    # latest summary from default user preference option and current week            
    latest_summary: list[ApiNewsSummaryEntry] = []
    default_news_summary_options: NewsSummaryOptions
    available_period_start_date_str: list[str] = []
    # date string in YYYY-MM-DD format
    preference_conversation_history: list[ChatMessage] = []


def _from_api_conversation_history_item_to_chat_message(
    api_item: ApiConversationHistoryItem,
) -> ChatMessage | None:
    if api_item.ai_message is None and api_item.human_message is None:
        return None
    return ChatMessage(
        thread_id=api_item.thread_id,
        message_id=api_item.message_id,
        parent_message_id=api_item.parent_message_id,
        content=api_item.llm_message.text_content or "",
        author=(ChatAuthorType.USER if api_item.llm_message.type == LlmMessageType.HUMAN else ChatAuthorType.AI),
    )

def __convert_to_api_news_summary_entry(
    news_summary_entry: NewsSummaryEntry,
) -> ApiNewsSummaryEntry:
    return ApiNewsSummaryEntry(
        id=news_summary_entry.id,
        title=news_summary_entry.title,
        content=news_summary_entry.content,
        expanded_content=news_summary_entry.expanded_content,
        reference_urls=news_summary_entry.reference_urls or [],
        display_order=news_summary_entry.display_order_within_period,
    )

def __get_or_create_news_summary_experiment_stats(
    user_id: int,
    start_date: str,
    period_type: NewsSummaryPeriod,
    news_chunking_experiment: NewsChunkingExperiment,
    news_preference_application_experiment: NewsPreferenceApplicationExperiment,
    sql_client: db.SqlClient,
) -> NewsSummaryExperimentStats:
    stats = sql_client.query(NewsSummaryExperimentStats).filter(
        NewsSummaryExperimentStats.user_id == user_id,
        NewsSummaryExperimentStats.start_date == start_date,
        NewsSummaryExperimentStats.period_type == period_type,
        NewsSummaryExperimentStats.news_chunking_experiment == news_chunking_experiment,
        NewsSummaryExperimentStats.news_preference_application_experiment == news_preference_application_experiment
    ).one_or_none()
    
    if not stats:
        stats = NewsSummaryExperimentStats(
            user_id=user_id,
            start_date=start_date,
            period_type=period_type,
            news_chunking_experiment=news_chunking_experiment,
            news_preference_application_experiment=news_preference_application_experiment
        )
        sql_client.add(stats)
        sql_client.flush()
    
    return stats

@router.get(
    "/initialize",
    response_model=NewsSummaryInitializeResponse,
)
async def initialize(
    request: Request,
    user: GetUserInSession,
    sql_client: db.SqlClient,
    redis_client: db.RedisClient,
):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    request.state.api_latency_log.user_id = user.user_id
    # Query user data
    user_data = sql_client.query(User).filter(User.id == user.user_id).first()
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check RSS feeds subscription
    if not user_data.subscribed_rss_feeds_id:
        return NewsSummaryInitializeResponse(mode=NewsSummaryUiMode.COLLECT_RSS_FEEDS)
    
    # Check news preference
    if not user_data.news_preference:
        api_survey_history = await load_preference_survey_history(
            user.user_id, redis=redis_client, sql_client=sql_client
        )
        
        if not api_survey_history:
            subscribed_rss_feed_list = await load_subscribed_rss_feed_list_for_preference_prompt(
                user.user_id, redis=redis_client, sql_client=sql_client
            )
            api_survey_history, next_survey_message = await save_answer_and_generate_next_question(
                user.user_id,
                answer=None,
                parent_message_id=None,
                subscribed_rss_feed_list=subscribed_rss_feed_list,
                chat_history=[],
                redis=redis_client,
                sql_client=sql_client,
                api_latency_log=request.state.api_latency_log,
            )
        preference_conversation_history = []
        for item in api_survey_history:
            if item.ai_message is not None or item.human_message is not None:
                preference_conversation_history.append(
                    _from_api_conversation_history_item_to_chat_message(item)
                )
        return NewsSummaryInitializeResponse(
            mode=NewsSummaryUiMode.COLLECT_NEWS_PREFERENCE,
            preference_conversation_history=preference_conversation_history,
        )
    default_news_preference_application_experiment = (
        user_data.preferred_news_preference_application_experiment
        or NewsPreferenceApplicationExperiment.APPLY_PREFERENCE
    )
    default_news_chunking_experiment = (
        user_data.preferred_news_chunking_experiment
        or NewsChunkingExperiment.AGGREGATE_DAILY
    )
    default_period_type = (
        user_data.preferred_news_summary_period_type or NewsSummaryPeriod.weekly
    )
    current_week_start_date = get_current_week_start_date()
    latest_summary = sql_client.query(NewsSummaryEntry).filter(
            NewsSummaryEntry.user_id == user.user_id,
            NewsSummaryEntry.start_date == current_week_start_date,
            NewsSummaryEntry.period_type == default_period_type,
            NewsSummaryEntry.news_preference_application_experiment
            == default_news_preference_application_experiment,
            NewsSummaryEntry.news_chunking_experiment == default_news_chunking_experiment,
        ).order_by(NewsSummaryEntry.display_order_within_period).all()
    if latest_summary:
        news_summary_exp_stats = __get_or_create_news_summary_experiment_stats(
            user_id=user.user_id,
            start_date=current_week_start_date,
            period_type=default_period_type,
            news_chunking_experiment=default_news_chunking_experiment,
            news_preference_application_experiment=default_news_preference_application_experiment,
            sql_client=sql_client,
        )
        news_summary_exp_stats.shown = True
    
    available_period_start_date = sql_client.query(NewsSummaryEntry.start_date).filter(
        NewsSummaryEntry.user_id == user.user_id,
        NewsSummaryEntry.period_type == default_period_type,
        NewsSummaryEntry.news_preference_application_experiment
        == default_news_preference_application_experiment,
        NewsSummaryEntry.news_chunking_experiment == default_news_chunking_experiment,
    ).distinct().all()
    return NewsSummaryInitializeResponse(
        mode=NewsSummaryUiMode.SHOW_SUMMARY,
        latest_summary= [ __convert_to_api_news_summary_entry(news_summary_entry) for news_summary_entry in latest_summary],
        default_news_summary_options=NewsSummaryOptions(
            news_chunking_experiment=default_news_chunking_experiment,
            news_preference_application_experiment=default_news_preference_application_experiment,
            period_type=default_period_type,
        ),
        available_period_start_date_str=[
                format_date(date_obj)
                for date_obj in available_period_start_date
            ],
    )

class PreferenceSurveyRequest(BaseModel):
    parent_message_id: str | None = None
    answer: str

class PreferenceSurveyResponse(BaseModel):
    answer_message_id: str
    next_question: Optional[str] = None
    next_question_message_id: Optional[str] = None
    preference_summary: Optional[str] = None


@router.post("/preference_survey", response_model=PreferenceSurveyResponse)
async def preference_survey(
    request: Request,
    preference_survey_request: PreferenceSurveyRequest,
    user: GetUserInSession,
    sql_client: db.SqlClient,
    redis_client: db.RedisClient,
):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    request.state.api_latency_log.user_id = user.user_id
    # Insert the question and answer into the chat history
    chat_history = await load_preference_survey_history(
        user.user_id, redis=redis_client, sql_client=sql_client
    )
    
    subscribed_rss_feed_list = await load_subscribed_rss_feed_list_for_preference_prompt(
        user.user_id, redis=redis_client, sql_client=sql_client
    )

    chat_history, next_survey_message = await save_answer_and_generate_next_question(
        user.user_id,
        answer=preference_survey_request.answer,
        parent_message_id=preference_survey_request.parent_message_id,
        subscribed_rss_feed_list=subscribed_rss_feed_list,
        chat_history=chat_history,
        redis=redis_client,
        sql_client=sql_client,
        api_latency_log=request.state.api_latency_log,
    )

    if next_survey_message.preference_summary is not None:
        # If the agent has provided a summary, update the user's news preference
        await _save_preference_summary(
            user.user_id,
            news_preference_summary=next_survey_message.preference_summary,
            cause=NewsPreferenceChangeCause.survey,
            causal_survey_conversation_history_thread_id=chat_history[0].thread_id,
            sql_client=sql_client,
        )

    return PreferenceSurveyResponse(
        answer_message_id=next_survey_message.parent_message_id,
        next_question=next_survey_message.next_survey_question,
        next_question_message_id=next_survey_message.next_survey_question_message_id,
        preference_summary=next_survey_message.preference_summary,
    )


async def _save_preference_summary(
    user_id: int,
    news_preference_summary: str,
    cause: NewsPreferenceChangeCause,
    sql_client: db.SqlClient,
    causal_survey_conversation_history_thread_id: str | None = None,
):
    # Save the news preference summary as a new version
    news_preference_version = NewsPreferenceVersion(
        user_id=user_id,
        previous_version_id=-1,  # -1 indicates no previous version
        content=news_preference_summary,
        cause=cause,
    )
    if cause == NewsPreferenceChangeCause.survey:
        news_preference_version.causal_survey_conversation_history_thread_id = (
            causal_survey_conversation_history_thread_id
        )
    sql_client.add(news_preference_version)
    sql_client.flush()
    # Update user's news preference and preference version ID
    user_data = sql_client.query(User).filter(User.id == user_id).first()
    user_data.news_preference = news_preference_summary
    user_data.current_news_preference_version_id = news_preference_version.id


class GetPreferenceResponse(BaseModel):
    preference_summary: Optional[str] = None

@router.get("/get_preference", response_model=GetPreferenceResponse)
async def get_preference(
    request: Request,
    user: GetUserInSession,
    sql_client: db.SqlClient,
):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    request.state.api_latency_log.user_id = user.user_id
    preference_summary = (
        sql_client.query(User).filter(User.id == user.user_id).first().news_preference
    )
    return GetPreferenceResponse(preference_summary=preference_summary)


class SavePreferenceRequest(BaseModel):
    preference_summary: str

@router.post("/save_preference")
async def save_preference(
    request: Request,
    save_preference_request: SavePreferenceRequest,
    user: GetUserInSession,
    sql_client: db.SqlClient,
):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    request.state.api_latency_log.user_id = user.user_id
    if save_preference_request.preference_summary is not None:
        # If the agent has provided a summary, update the user's news preference
        await _save_preference_summary(
            user.user_id,
            news_preference_summary=save_preference_request.preference_summary,
            cause=NewsPreferenceChangeCause.user_edit,
            sql_client=sql_client,
        )
    return {}

@router.post("/upload_rss_feeds")
async def upload_rss_feeds( 
    request: Request,
    user: GetUserInSession,
    sql_client: db.SqlClient,
    opml_file: UploadFile | None = None,
    use_default: Annotated[bool, Form()] = False):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    request.state.api_latency_log.user_id = user.user_id
    if not opml_file and not use_default:
        raise HTTPException(status_code=400, detail="No OPML file provided")
    if opml_file and use_default:
        raise HTTPException(status_code=400, detail="Cannot provide both OPML file and use default")
    if opml_file and opml_file.filename and not opml_file.filename.endswith(".opml") and opml_file.content_type != "application/xml":
        raise HTTPException(status_code=400, detail="Invalid file type, must be .opml") 

    if opml_file:
        # Process the uploaded OPML file
        content = (await opml_file.read()).decode("utf-8")
    else: 
        with open("resources/default.opml", "r", encoding="utf-8") as f:
            content = f.read()
    
    if not content:
        raise HTTPException(status_code=400, detail="Empty OPML content")
    
    root = ET.fromstring(content)
    rss_feeds = root.findall('.//outline[@type="rss"]')
    if len(rss_feeds) > MAX_RSS_SUBSCRIPTION:
        raise HTTPException(
            status_code=400,
            detail=f"Exceeded maximum number of RSS subscriptions: {MAX_RSS_SUBSCRIPTION}",
        )
    feeds_to_add = {}
    for feed in rss_feeds:
        db_feed = RssFeed(
            title=feed.attrib.get("title", ""),
            html_url=feed.attrib.get("htmlUrl", ""),
            feed_url=feed.attrib.get("xmlUrl", ""),
        )
        if not db_feed.feed_url or not db_feed.title:
            logger.warning(f"Skipping invalid feed: {feed.attrib}")
            continue
        feeds_to_add[db_feed.feed_url] = db_feed
    subscribed_feed_keys = list(feeds_to_add.keys())

    existing_feeds = sql_client.query(RssFeed).filter(
        RssFeed.feed_url.in_(subscribed_feed_keys)
    ).all()
    for db_feed in existing_feeds:
        if db_feed.feed_url in feeds_to_add:
            del feeds_to_add[db_feed.feed_url]
    valid_feeds_to_add = []
    for feed_url, db_feed in feeds_to_add.items():
        if is_valid_rss_feed(db_feed.feed_url) or is_valid_rss_feed(db_feed.html_url):
            valid_feeds_to_add.append(db_feed)

    if valid_feeds_to_add:
        sql_client.add_all(valid_feeds_to_add)
        sql_client.flush()
    subscribed_feeds = existing_feeds + valid_feeds_to_add
    user_data = sql_client.query(User).filter(User.id == user.user_id).first()
    user_data.subscribed_rss_feeds_id = [feed.id for feed in subscribed_feeds]



@router.get("/get_subscribed_rss_feeds", response_model=list[ApiRssFeed])
async def get_subscribed_rss_feeds( 
    request: Request,
    user: GetUserInSession,
    sql_client: db.SqlClient):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    request.state.api_latency_log.user_id = user.user_id
    user_data = sql_client.query(User).filter(User.id == user.user_id).first()
    subscribed_rss_feeds = sql_client.query(RssFeed).filter(
        RssFeed.id.in_(user_data.subscribed_rss_feeds_id or [])
    ).all()
    return [
        ApiRssFeed(id=feed.id, title=feed.title, feed_url=feed.feed_url)
        for feed in subscribed_rss_feeds
    ]

@router.get("/delete_rss_feed/{feed_id}")
async def delete_rss_feed( 
    request: Request,
    user: GetUserInSession,
    sql_client: db.SqlClient,
    feed_id: int):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    request.state.api_latency_log.user_id = user.user_id
    user_data = sql_client.query(User).filter(User.id == user.user_id).first()
    if feed_id not in user_data.subscribed_rss_feeds_id:
        raise HTTPException(status_code=400, detail="Feed ID not found in subscribed feeds")
    subscribed_rss_feeds_id = user_data.subscribed_rss_feeds_id.copy()
    subscribed_rss_feeds_id.remove(feed_id)
    user_data.subscribed_rss_feeds_id = subscribed_rss_feeds_id

@router.post("/subscribe_rss_feed")
async def subscribe_rss_feed( 
    request: Request,
    user: GetUserInSession,
    sql_client: db.SqlClient,
    rss_feed: ApiRssFeed):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    request.state.api_latency_log.user_id = user.user_id
    user_data = sql_client.query(User).filter(User.id == user.user_id).first()
    if rss_feed.id in user_data.subscribed_rss_feeds_id:
        return
    if len(user_data.subscribed_rss_feeds_id) >= MAX_RSS_SUBSCRIPTION:
        raise HTTPException(
            status_code=400,
            detail=f"Exceeded maximum number of RSS subscriptions: {MAX_RSS_SUBSCRIPTION}",
        )
    if not is_valid_rss_feed(rss_feed.feed_url):
        raise HTTPException(status_code=400, detail="Invalid RSS feed URL")
    existing_feed = sql_client.query(RssFeed).filter(
        RssFeed.feed_url == rss_feed.feed_url
    ).first()
    feed_id_to_add = None
    if existing_feed:
        feed_id_to_add = existing_feed.id
    else:
        new_feed = RssFeed(
            title=rss_feed.title,
            feed_url=rss_feed.feed_url,
        )
        sql_client.add(new_feed)
        sql_client.flush()
        feed_id_to_add = new_feed.id
    subscribed_rss_feeds_id = user_data.subscribed_rss_feeds_id.copy()
    subscribed_rss_feeds_id.append(feed_id_to_add)
    user_data.subscribed_rss_feeds_id = subscribed_rss_feeds_id
    return {
        "status": "success",
        "feed_id": feed_id_to_add,
    }

class NewsSummaryStartDateAndOptionSelector(BaseModel):
    start_date: str  # Date in YYYY-MM-DD format
    option: NewsSummaryOptions

class GetNewsSummaryRequest(BaseModel):
    news_summary_start_date_and_option_selector: NewsSummaryStartDateAndOptionSelector

@router.post("/get_news_summary", response_model=list[ApiNewsSummaryEntry])
async def get_news_summary(
    request: Request,
    get_news_summary_request: GetNewsSummaryRequest,
    user: GetUserInSession,
    sql_client: db.SqlClient):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    request.state.api_latency_log.user_id = user.user_id
    news_summary_entry_list = await summarize_news(
        news_preference_application_experiment=get_news_summary_request.news_summary_start_date_and_option_selector.option.news_preference_application_experiment,
        news_chunking_experiment=get_news_summary_request.news_summary_start_date_and_option_selector.option.news_chunking_experiment,
        user_id=user.user_id,
        start_date=parse_date(get_news_summary_request.news_summary_start_date_and_option_selector.start_date),
        period=get_news_summary_request.news_summary_start_date_and_option_selector.option.period_type,
    )
    news_summary_exp_stats = __get_or_create_news_summary_experiment_stats(
        user_id=user.user_id,
        start_date=get_news_summary_request.news_summary_start_date_and_option_selector.start_date,
        period_type=get_news_summary_request.news_summary_start_date_and_option_selector.option.period_type,
        news_chunking_experiment=get_news_summary_request.news_summary_start_date_and_option_selector.option.news_chunking_experiment,
        news_preference_application_experiment=get_news_summary_request.news_summary_start_date_and_option_selector.option.news_preference_application_experiment,
        sql_client=sql_client,
    )
    news_summary_exp_stats.shown = True
    return [
        __convert_to_api_news_summary_entry(news_summary_entry)
        for news_summary_entry in news_summary_entry_list
    ]

class NewsSummaryLikeOrDislike(enum.Enum):
    LIKE = "like"
    DISLIKE = "dislike"

class NewsSummaryLikeDislikeRequest(BaseModel):
    news_summary_start_date_and_option_selector: NewsSummaryStartDateAndOptionSelector
    action: NewsSummaryLikeOrDislike
@router.post("/like_dislike_news_summary")
async def like_dislike_news_summary(
    request: Request,
    news_summary_like_dislike_request: NewsSummaryLikeDislikeRequest,
    user: GetUserInSession,
    sql_client: db.SqlClient,
):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    request.state.api_latency_log.user_id = user.user_id
    start_date = parse_date(news_summary_like_dislike_request.news_summary_start_date_and_option_selector.start_date)
    period_type = news_summary_like_dislike_request.news_summary_start_date_and_option_selector.option.period_type
    news_chunking_experiment = news_summary_like_dislike_request.news_summary_start_date_and_option_selector.option.news_chunking_experiment
    news_preference_application_experiment = news_summary_like_dislike_request.news_summary_start_date_and_option_selector.option.news_preference_application_experiment
    
    stats = sql_client.query(NewsSummaryExperimentStats).filter(
        NewsSummaryExperimentStats.user_id == user_data.id,
        NewsSummaryExperimentStats.start_date == start_date,
        NewsSummaryExperimentStats.period_type == period_type,
        NewsSummaryExperimentStats.news_chunking_experiment == news_chunking_experiment,
        NewsSummaryExperimentStats.news_preference_application_experiment == news_preference_application_experiment
    ).one_or_none()
    if not stats or not stats.shown:
        raise HTTPException(
            status_code=404,
            detail="News summary experiment stats not found for the given parameters",
        )
    if news_summary_like_dislike_request.action == NewsSummaryLikeOrDislike.LIKE:
        stats.liked = True
        stats.disliked = False
        user_data = sql_client.query(User).filter(User.id == user.user_id).first()
        user_data.preferred_news_chunking_experiment = news_chunking_experiment
        user_data.preferred_news_preference_application_experiment = news_preference_application_experiment
        user_data.preferred_news_summary_period_type = period_type
    elif news_summary_like_dislike_request.action == NewsSummaryLikeOrDislike.DISLIKE:
        stats.liked = False
        stats.disliked = True
    return {"status": "success", "message": "News summary like or dislike action recorded successfully."}

@router.get(
    "/expand_summary/",
    response_model=ApiNewsSummaryEntry,
)
async def expand_summary(
    request: Request,
    user: GetUserInSession,
    sql_client: db.SqlClient,
    summary_id: int,
):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    request.state.api_latency_log.user_id = user.user_id
    summary_entry = sql_client.query(NewsSummaryEntry).filter(
        NewsSummaryEntry.id == summary_id,
        NewsSummaryEntry.user_id == user.user_id,
    ).one_or_none()
    if not summary_entry:
        raise HTTPException(status_code=404, detail="Summary not found")
    summary_entry.clicked = True
    if not summary_entry.expanded_content: 
        await expand_news_summary(summary_entry)
        if not summary_entry.expanded_content:
            raise HTTPException(status_code=500, detail="Failed to expand news summary")
    return __convert_to_api_news_summary_entry(summary_entry)
    