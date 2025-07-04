from .client_proxy_factory import get_default_client_proxy
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import redis.asyncio as redis
from db.models.common import ConversationHistory, ConversationType, User
from db.models import ApiLatencyLog
from db.db import SqlSessionLocal
from utils.conversation_history import (
    ApiConversationHistoryItem,
    convert_to_api_conversation_history,
    create_thread_id,
    create_message_id,
    convert_api_conversation_history_item_to_db_row,
)
from db.models.newssummary import RssFeed, NewsSummaryEntry, NewsPreferenceVersion, NewsPreferenceChangeCause
import json
from enum import Enum
import time
from sqlalchemy import select
from .client_proxy import LlmMessage, LlmMessageType
from utils.logger import logger
from utils.exceptions import UserErrorCode, ApiErrorType, ApiException

class NewsPreferenceAgentOutput(BaseModel):
    """
    Generated next survey question or summary of the user's news preferences. If the survey is not completed,
    the `next_survey_question` field will contain the next question to ask the user. If the survey is completed,
    the `news_preference_summary` field will contain a summary of the user's news preferences.
    The `next_survey_question` field will be `None` if the survey is completed and no next question is generated.
    The `news_preference_summary` field will be `None` if the survey is not completed and a next question is generated.
    """

    news_preference_summary: str | None = Field(
        description="""The summary of the user's news preference if the survey is completed 
            and no next survey question is generated. Write the preference summary in third-person perspective 
            so that AI could understand how to write news summary and rank news. 
            It should also contain instructions to rank news based on the user's preferences.""",
    )
    next_survey_question: str | None = Field(
        description="The next new preference question to ask the user"
    )


class NewsPreferenceAgentError(Enum):
    # Incoming survey question's parent message id does not match the last message in chat history
    MISSING_ANSWER = 0
    MISSING_QUESTION_FOR_ANSWER = 1
    NO_SUBSCRIBED_RSS_FEED = 2


_survey_generation_system_message = """You are a news preference survey agent. Your task is learn their news preferences by asking questions.
    - We already know the user has subscribed to follow RSS feeds: {rss_feed_list}
    - You will be provided with a huge amount of news to summarize. 
    - Ask questions to learn user's preference of topic, story, idea, or meta element which might be helpful to summarize, select and sort news. 
    - Also ask questions to learn user's preference of writing style and format which makes user more likely and comfortable to read the news summary.
        We only support text summary 
    - generate all questions first and then ask one question at a time and wait for the user's response. 
    - After each response, Determine if you have enough information to summarize the user's news preferences. 
    -- If you do, you will return the summary in the `news_preference_summary` field.
    -- If not, you will return the next question to ask in the `next_survey_question` field.
    - Introduce yourself as a news preference survey agent and explain the purpose of the survey to the user first.
    - Don't tell the user that we know the user has subscribed to follow RSS feeds.
    """


def _get_news_preference_survey_history_key(user_id: int) -> str:
    """
    Generates a Redis key for storing the news preference survey history for a user.
    """
    return f"news_preference_survey_history:{user_id}"


async def load_preference_survey_history(
    user_id: int, redis: redis.Redis, sql_client: Session
) -> list[ApiConversationHistoryItem]:
    redis_key = _get_news_preference_survey_history_key(user_id)

    # Check if survey history exists in Redis
    redis_key_exists = await redis.exists(redis_key)
    if redis_key_exists:
        # Load survey history from Redis
        cached_history = json.loads(await redis.get(redis_key))
        await redis.expire(redis_key, 3600)  # Extend TTL to 1 hour (3600 seconds)
        return [
            ApiConversationHistoryItem.model_validate_json(item)
            for item in cached_history
        ]
    # If not in Redis, load from the database
    survey_history = (
        sql_client.query(ConversationHistory)
        .filter(
            ConversationHistory.user_id == user_id,
            ConversationHistory.conversation_type
            == ConversationType.news_preference_survey,
        )
        .all()
    )
    if not survey_history:
        # If no survey history found, return an empty list
        return []
    api_survey_history = convert_to_api_conversation_history(survey_history)

    await redis.set(
        redis_key,
        json.dumps([item.model_dump_json() for item in api_survey_history]),
        ex=3600,
    )  # Cache for 1 hour

    return api_survey_history


def _get_subscribed_rss_feed_list_redis_key(user_id: int) -> str:
    """
    Generates a Redis key for storing the news preference survey history for a user.
    """
    return f"news_preference_survey_subscribed_rss_feed_list:{user_id}"


async def load_subscribed_rss_feed_list_for_preference_prompt(
    user_id: int, redis: redis.Redis, sql_client: Session
) -> str:
    redis_key = _get_subscribed_rss_feed_list_redis_key(user_id)

    # Check if cached_subscribed_rss_feed_list exists in Redis
    redis_key_exists = await redis.exists(redis_key)
    if redis_key_exists:
        # Load survey history from Redis
        cached_subscribed_rss_feed_list = await redis.get(redis_key)
        await redis.expire(redis_key, 3600)  # Extend TTL to 1 hour (3600 seconds)
        return cached_subscribed_rss_feed_list
    # If not in Redis, load from the database
    subscribed_rss_feeds_id = (
        sql_client.execute(
            select(User.subscribed_rss_feeds_id).filter(User.id == user_id)
        )
        .first()
        .subscribed_rss_feeds_id
    )

    if not subscribed_rss_feeds_id:
        raise ApiException(
            type=ApiErrorType.CLIENT_ERROR,
            user_error_code=UserErrorCode.NO_RSS_FEED_SUBSCRIBED,
            message="User has no subscribed rss feed list",
        )
    subscribed_rss_feed_title_list = [
        row.title
        for row in sql_client.execute(
            select(RssFeed.title).filter(RssFeed.id.in_(subscribed_rss_feeds_id))
        ).all()
    ]
    subscribed_rss_feed_title_list_str = (
        "(list start)" + ";\n".join(subscribed_rss_feed_title_list) + "(list end)"
    )

    await redis.set(
        redis_key,
        subscribed_rss_feed_title_list_str,
        ex=3600,
    )  # Cache for 1 hour

    return subscribed_rss_feed_title_list_str


def next_preference_question(
    subscribed_rss_feed_list: str,
    chat_history: list[ApiConversationHistoryItem],
    api_latency_log: ApiLatencyLog,
) -> NewsPreferenceAgentOutput:
    llm_start_time = time.time()
    llm_result = get_default_client_proxy().generate_content(
        system_prompt=_survey_generation_system_message.format_map(
            {"rss_feed_list": subscribed_rss_feed_list}
        ),
        prompt=[LlmMessage(text_content="Let's start", type=LlmMessageType.AI)]
        + [
            item.llm_message
            for item in chat_history
            if item.llm_message
            and item.llm_message.type in (LlmMessageType.HUMAN, LlmMessageType.AI)
        ],
        output_object=NewsPreferenceAgentOutput,
    )[0]
    api_latency_log.llm_elapsed_time_ms = (
        api_latency_log.llm_elapsed_time_ms
        if api_latency_log.llm_elapsed_time_ms
        else 0
    ) + int(
        (time.time() - llm_start_time) * 1000
    )  # Convert to milliseconds
    return llm_result.structured_output


class NextPreferenceSurveyMessage(BaseModel):
    parent_message_id: str | None = None
    next_survey_question: str | None = None
    next_survey_question_message_id: str | None = None
    preference_summary: str | None = None


async def save_answer_and_generate_next_question(
    user_id: int,
    answer: str | None,
    parent_message_id: str | None,
    subscribed_rss_feed_list: str,
    chat_history: list[ApiConversationHistoryItem],
    redis: redis.Redis,
    sql_client: Session,
    api_latency_log: ApiLatencyLog,
) -> tuple[list[ApiConversationHistoryItem], NextPreferenceSurveyMessage]:
    """
    Save an answer and generate the next question. Defer all PostGreSQL writes to the end of the function
    so that they can be further deferred to the end of the request in the future.
    """

    message_to_save = []
    if (
        not chat_history
        and (answer is not None or parent_message_id is not None)
        or chat_history
        and (not parent_message_id or chat_history[-1].message_id != parent_message_id)
    ):
        raise ApiException(
            type=ApiErrorType.SERVER_ERROR,
            message="news preference agent, missing question for answer."
        )
    elif answer is None and chat_history:
        # If the last message ID does not match the parent message ID, raise an error
        raise ApiException(
            type=ApiErrorType.SERVER_ERROR,
            message="parent message not matched."
        )
    if chat_history:
        thread_id = chat_history[0].thread_id
    else:
        thread_id = create_thread_id()
    answer_message_id = None
    if answer is not None:
        answer_message_id = create_message_id()
        answer_conversation_item = ApiConversationHistoryItem(
            user_id=user_id,
            thread_id=thread_id,
            message_id=answer_message_id,
            parent_message_id=chat_history[-1].message_id,
            llm_message=LlmMessage(
                text_content=answer,
                type=LlmMessageType.HUMAN,
            ),
        )
        chat_history.append(answer_conversation_item)
        message_to_save.append(answer_conversation_item)

    next_question_or_summary = next_preference_question(
        subscribed_rss_feed_list, chat_history, api_latency_log=api_latency_log
    )
    if next_question_or_summary.next_survey_question is not None:
        question_conversation_item = ApiConversationHistoryItem(
            user_id=user_id,
            thread_id=thread_id,
            message_id=create_message_id(),
            llm_message=LlmMessage(
                text_content=next_question_or_summary.next_survey_question,
                type=LlmMessageType.AI,
            ),
        )
        if chat_history:
            question_conversation_item.parent_message_id = chat_history[-1].message_id
        chat_history.append(question_conversation_item)
        message_to_save.append(question_conversation_item)

    # Update Redis cache
    redis_key = _get_news_preference_survey_history_key(user_id)
    await redis.set(
        redis_key,
        json.dumps([item.model_dump_json() for item in chat_history]),
        ex=3600,
    )  # Cache for 1 hour
    for item in message_to_save:
        db_conversation_history_item = convert_api_conversation_history_item_to_db_row(
            item, user_id, ConversationType.news_preference_survey
        )
        if db_conversation_history_item:
            sql_client.add(db_conversation_history_item)
    return (
        chat_history,
        NextPreferenceSurveyMessage(
            parent_message_id=answer_message_id,
            next_survey_question=next_question_or_summary.next_survey_question,
            next_survey_question_message_id=(
                chat_history[-1].message_id
                if next_question_or_summary.next_survey_question
                else None
            ),
            preference_summary=next_question_or_summary.news_preference_summary,
        ),
    )

__update_preference_based_on_clicked_news_prompt = """
Update the user's news preference based on the clicked news.
{user_preference}
{clicked_news}
"""
class NewsPreference(BaseModel):
    """
    Represents the user's news preference.
    """
    updated_news_preference: str = Field(
        description="The user's updated news preference."
    )
CLICKED_NEWS_LIMIT = 500  # Limit the number of clicked news to consider

def update_preference_based_on_clicked_news(user_id: int):
    with SqlSessionLocal() as sql_client:
        user_data = (
            sql_client.query(User)
            .filter(User.id == user_id)
            .one_or_none()
        )
        clicked_news = (
            sql_client.query(NewsSummaryEntry.id, NewsSummaryEntry.title)
            .filter(NewsSummaryEntry.clicked.is_(True), NewsSummaryEntry.user_id == user_id)
            .order_by(NewsSummaryEntry.clicked_time.desc())
            .limit(CLICKED_NEWS_LIMIT)
            .all()
        )
        if not clicked_news:
            logger.info(f"No clicked news found for user {user_id}.")
            return
        prompt = __update_preference_based_on_clicked_news_prompt.format_map(
            {
                "user_preference": {"user_preference": user_data.news_preference},
                "clicked_news": {"clicked_news": [news_summary[1] for news_summary in clicked_news]},
            }
        )
        updated_preference = get_default_client_proxy().generate_content(prompt=prompt, output_object=NewsPreference)[0].structured_output.updated_news_preference
        logger.info(f"Old user preference: {user_data.news_preference}\n Updated user preference: {updated_preference}")
        news_preference_version = NewsPreferenceVersion(
            user_id=user_id,
            content=updated_preference,
            cause=NewsPreferenceChangeCause.news_click,
            previous_version_id=user_data.current_news_preference_version_id or -1,
            causal_clicked_news_summary_entry_id =  [news_summary[0] for news_summary in clicked_news]
        )
        sql_client.add(news_preference_version)
        sql_client.flush()
        user_data.news_preference = news_preference_version.content
        user_data.current_news_preference_version_id = news_preference_version.id
        sql_client.commit()
