from fastapi import APIRouter, HTTPException, Request, Depends
from typing import Optional
from pydantic import BaseModel
from db import db
from db.models import (
    User,
    NewsSummary,
    NewsSummaryList,
    NewsPreferenceChangeCause,
    NewsPreferenceVersion,
)
from utils.manage_session import GetUserInSession
import os
from llm.news_preference_agent import (
    load_preference_survey_history,
    save_answer_and_generate_next_question,
    ApiConversationHistoryItem,
)
from .common import ChatMessage, ChatAuthorType
from utils.manage_session import limit_usage

DOMAIN = os.getenv("DOMAIN", "localhost:3000")


router = APIRouter(prefix="/api/py/news_summary", tags=["news_summary"])

class NewsSummaryPeriod(BaseModel):
    start_date_timestamp: int  # Timestamp in seconds
    end_date_timestamp: int  # Timestamp in seconds
    id: int


class NewsSummaryInitializeResponse(BaseModel):
    mode: str
    latest_summary: Optional[NewsSummaryList] = None
    news_summary_periods: list[NewsSummaryPeriod]
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

    # Check news preference
    if not user_data.news_preference:
        api_survey_history = await load_preference_survey_history(
            user.user_id, redis=redis_client, sql_client=sql_client
        )
        if not api_survey_history:
            api_survey_history = await save_answer_and_generate_next_question(
                user.user_id,
                answer=None,
                parent_message_id=None,
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

    # Check RSS feeds subscription
    if not user_data.subscribed_rss_feeds_id:
        return NewsSummaryInitializeResponse(mode="collect_rss_feeds")

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

    next_survey_message = await save_answer_and_generate_next_question(
        user.user_id,
        answer=preference_survey_request.answer,
        parent_message_id=preference_survey_request.parent_message_id,
        chat_history=chat_history,
        redis=redis_client,
        sql_client=sql_client,
        api_latency_log=request.state.api_latency_log,
    )

    if next_survey_message.news_preference_summary is not None:
        # If the agent has provided a summary, update the user's news preference
        await _save_preference_summary(
            user.user_id,
            news_preference_summary=next_survey_message.news_preference_summary,
            case=NewsPreferenceChangeCause.survey,
            causal_survey_conversation_history_thread_id=chat_history[0].thread_id,
            sql_client=sql_client,
        )

    return PreferenceSurveyResponse(
        answer_message_id=next_survey_message.parent_message_id,
        next_question=next_survey_message.next_survey_question,
        next_question_message_id=next_survey_message.next_survey_question_message_id,
        preference_summary=next_survey_message.news_preference_summary,
    )


async def _save_preference_summary(
    user_id: int,
    news_preference_summary: str,
    cause: NewsPreferenceChangeCause,
    causal_survey_conversation_history_thread_id: str | None,
    sql_client: db.SqlClient,
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
