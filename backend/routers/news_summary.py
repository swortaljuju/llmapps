from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.middleware.base import BaseHTTPMiddleware
from typing import Optional, Callable
from pydantic import BaseModel
from starlette.responses import JSONResponse
from db import db
from db.models import User, NewsSummary, NewsSummaryList, NewsPreferenceChangeCause, NewsPreferenceVersion, ApiLatencyLog
from utils.manage_session import GetUserInSession
from utils.logger import logger
import os
import time
from llm.news_preference_agent import (
    load_preference_survey_history,
    next_preference_question,
    insert_preference_question_and_answer,
    NewsPreferenceSurveyOneRoundConversationItem
)
from common import ChatMessage, ChatAuthorType
from utils.manage_session import limit_usage

DOMAIN = os.getenv("DOMAIN", "localhost:3000")

class NewsSummaryMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Start timer for performance logging
        start_time = time.time()
        
        # Extract the path for logging
        path = request.url.path
        method = request.method
        
        # Check for authentication session
        try:
            request.state.api_latency_log = ApiLatencyLog(
                user_id=None,
                path=path,
                method=method
            )
            # Continue with the request
            response = await call_next(request)
            
            # Log response time
            process_time = time.time() - start_time
            request.state.api_latency_log.total_elapsed_time_ms = int( process_time * 1000)
            sql_client = db.SqlClient()
            sql_client.add(request.state.api_latency_log)
            sql_client.commit()
            return response
                    
        except Exception as e:
            # Log any uncaught exceptions
            process_time = time.time() - start_time
            logger.error(f"NewsSummary error: {method} {path} - Error: {str(e)} - Time: {process_time:.4f}s")
            
            # Return appropriate error response
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
            )

router = APIRouter(prefix="/api/py/news_summary", tags=["news_summary"])
router.add_middleware(NewsSummaryMiddleware)

class NewsSummaryPeriod(BaseModel):
    start_date_timestamp: int  # Timestamp in seconds
    end_date_timestamp: int  # Timestamp in seconds
    id: int


class NewsSummaryInitializeResponse(BaseModel):
    mode: str
    latest_summary: Optional[NewsSummaryList] = None
    news_summary_periods: list[NewsSummaryPeriod]
    preference_conversation_history: list[ChatMessage] = None
    next_preference_question: Optional[str] = None


@router.get("/initialize", response_model=NewsSummaryInitializeResponse, dependencies=[Depends(GetUserInSession)])
async def initialize(request:Request, user: GetUserInSession, sql_client: db.SqlClient, redis_client: db.RedisClient):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    request.state.api_latency_log.user_id = user.user_id
    
    # Query user data
    user_data = db.query(User).filter(User.id == user.user_id).first()
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")

    # Check news preference
    if not user_data.news_preference:
        api_survey_history = await load_preference_survey_history(
            user.user_id, redis=redis_client, sql_client=sql_client
        )
        preference_conversation_history = []
        for item in api_survey_history:
            if item.ai_message is not None or item.human_message is not None:
                preference_conversation_history.append(
                    ChatMessage(
                        thread_id=item.thread_id,
                        message_id=item.message_id,
                        parent_message_id=item.parent_message_id,
                        content=(
                            item.human_message.content
                            if item.human_message
                            else item.ai_message.content if item.ai_message else ""
                        ),
                        author=(
                            ChatAuthorType.USER
                            if item.human_message
                            else ChatAuthorType.AI
                        ),
                    )
                )        
        return NewsSummaryInitializeResponse(
            mode="collect_news_preference",
            preference_conversation_history=preference_conversation_history,
            next_preference_question=next_preference_question(
                api_survey_history, request.state.api_latency_log
            ).question,
        )

    # Check RSS feeds subscription
    if not user_data.subscribed_rss_feeds_id:
        return NewsSummaryInitializeResponse(mode="collect_rss_feeds")

    # Query latest news summary
    all_summary = (
        db.query(NewsSummary)
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
    question: str
    answer: str

class PreferenceSurveyResponse(BaseModel):
    next_question: Optional[str] = None
    parent_message_id: str

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
    chat_history = await load_preference_survey_history(user.user_id, redis=redis_client, sql_client=sql_client)
    
    chat_history = await insert_preference_question_and_answer(
        user.user_id,
        NewsPreferenceSurveyOneRoundConversationItem(
            question=preference_survey_request.question,
            answer=preference_survey_request.answer,
            parent_message_id=preference_survey_request.parent_message_id
        ),
        chat_history,
        redis=redis_client,
        sql_client=sql_client
    )

    # Get the next question from the agent
    next_question = next_preference_question(chat_history, request.state.api_latency_log)
    
    if next_question.news_preference_summary is not None:
        # If the agent has provided a summary, update the user's news preference
        news_preference_version = NewsPreferenceVersion(
            user_id=user.user_id,
            previous_version_id=-1,  # -1 indicates no previous version
            content=next_question.news_preference_summary,
            cause=NewsPreferenceChangeCause.survey,
            causal_survey_conversation_history_thread_id=chat_history[-1].thread_id
        )
        sql_client.add(news_preference_version)
        sql_client.commit()
        sql_client.refresh(news_preference_version)
        # Update user's news preference and preference version ID
        user_data = sql_client.query(User).filter(User.id == user.user_id).first()
        user_data.news_preference = next_question.news_preference_summary
        user_data.current_news_preference_version_id = news_preference_version.id
        sql_client.commit()

    return PreferenceSurveyResponse(
        next_question=next_question.next_survey_question,
        parent_message_id=chat_history[-1].message_id
    )