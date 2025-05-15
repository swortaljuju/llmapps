from fastapi import APIRouter, HTTPException, Request, UploadFile, Form
from typing import Optional
from pydantic import BaseModel
from db import db
from db.models import (
    User,
    NewsSummary,
    NewsSummaryList,
    NewsPreferenceChangeCause,
    NewsPreferenceVersion,
    RssFeed,
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
class NewsSummaryInitializeResponse(BaseModel):
    mode: str
    latest_summary: Optional[NewsSummaryList] = None
    news_summary_periods: list[NewsSummaryPeriod] = None
    preference_conversation_history: list[ChatMessage] = None


def _from_api_conversation_history_item_to_chat_message(
    api_item: ApiConversationHistoryItem,
) -> ChatMessage | None:
    if api_item.ai_message is None and api_item.human_message is None:
        return None
    return ChatMessage(
        thread_id=api_item.thread_id,
        message_id=api_item.message_id,
        parent_message_id=api_item.parent_message_id,
        content=(
            api_item.human_message.content
            if api_item.human_message
            else api_item.ai_message.content if api_item.ai_message else ""
        ),
        author=(ChatAuthorType.USER if api_item.human_message else ChatAuthorType.AI),
    )


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
        return NewsSummaryInitializeResponse(mode="collect_rss_feeds")
    
    # Check news preference
    if not user_data.news_preference:
        api_survey_history = await load_preference_survey_history(
            user.user_id, redis=redis_client, sql_client=sql_client
        )
        
        if not api_survey_history:
            subscribe_rss_feed_list = load_subscribed_rss_feed_list_for_preference_prompt(
                user.user_id, redis=redis_client, sql_client=sql_client
            )
            api_survey_history, next_survey_message = await save_answer_and_generate_next_question(
                user.user_id,
                answer=None,
                parent_message_id=None,
                subscribe_rss_feed_list=subscribe_rss_feed_list,
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
            mode="collect_news_preference",
            preference_conversation_history=preference_conversation_history,
        )

    # Query latest news summary
    all_summary = (
        sql_client.query(NewsSummary)
        .filter(NewsSummary.user_id == user.user_id)
        .order_by(NewsSummary.end_date.desc())
        .all()
    )

    return NewsSummaryInitializeResponse(
        mode="show_summary",
        latest_summary=len(all_summary) > 0 and all_summary[0].content or None,
        news_summary_periods=[
            NewsSummaryPeriod(
                start_date_timestamp=int(summary.start_date.timestamp()),
                end_date_timestamp=int(summary.end_date.timestamp()),
                id=summary.id,
            )
            for summary in all_summary
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
    
    subscribe_rss_feed_list = await load_subscribed_rss_feed_list_for_preference_prompt(
        user.user_id, redis=redis_client, sql_client=sql_client
    )

    chat_history, next_survey_message = await save_answer_and_generate_next_question(
        user.user_id,
        answer=preference_survey_request.answer,
        parent_message_id=preference_survey_request.parent_message_id,
        subscribe_rss_feed_list=subscribe_rss_feed_list,
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
    sql_client.commit()
    sql_client.refresh(news_preference_version)
    # Update user's news preference and preference version ID
    user_data = sql_client.query(User).filter(User.id == user_id).first()
    user_data.news_preference = news_preference_summary
    user_data.current_news_preference_version_id = news_preference_version.id
    sql_client.commit()


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
    for feed_url, db_feed in feeds_to_add.items():
        if not is_valid_rss_feed(db_feed.feed_url) and not is_valid_rss_feed(db_feed.html_url):
            del feeds_to_add[feed_url]

    if feeds_to_add:
        sql_client.add_all(feeds_to_add.values())
        sql_client.commit()
    subscribed_feeds = sql_client.query(RssFeed).filter(
        RssFeed.feed_url.in_(subscribed_feed_keys)
    ).all()
    user_data = sql_client.query(User).filter(User.id == user.user_id).first()
    user_data.subscribed_rss_feeds_id = [feed.id for feed in subscribed_feeds]
    sql_client.commit()



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
        RssFeed.id.in_(user_data.subscribed_rss_feeds_id)
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
    user_data.subscribed_rss_feeds_id.remove(feed_id)
    sql_client.commit()

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
    existing_feed = sql_client.query(RssFeed).filter(
        RssFeed.feed_url == rss_feed.feed_url
    ).first()
    if existing_feed:
        user_data.subscribed_rss_feeds_id.append(existing_feed.id)
    else:
        new_feed = RssFeed(
            title=rss_feed.title,
            feed_url=rss_feed.feed_url,
        )
        sql_client.add(new_feed)
        sql_client.flush()
        user_data.subscribed_rss_feeds_id.append(new_feed.id)
    sql_client.commit()
    