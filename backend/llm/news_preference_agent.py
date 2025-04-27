from .clients import langchain_gemini_client
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from sqlalchemy.orm import Session
import redis.asyncio as redis
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from db.models.common import ConversationHistory, ConversationType
from db.models import ApiLatencyLog
from utils.conversation_history import (
    ApiConversationHistoryItem,
    convert_to_api_conversation_history,
    create_thread_id,
    create_message_id,
    convert_api_conversation_history_item_to_db_row,
)
import json
from enum import Enum
import time


class NewsPreferenceAgentOutput(BaseModel):
    """
    Generated next survey question or summary of the user's news preferences. If the survey is not completed,
    the `next_survey_question` field will contain the next question to ask the user. If the survey is completed,
    the `news_preference_summary` field will contain a summary of the user's news preferences.
    The `next_survey_question` field will be `None` if the survey is completed and no next question is generated.
    The `news_preference_summary` field will be `None` if the survey is not completed and a next question is generated.
    """

    news_preference_summary: str | None = Field(
        default=None,
        description="""The summary of the user's news preference if the survey is completed 
            and no next survey question is generated. Write the preference summary in third-person perspective 
            so that AI could understand how to write news summary and rank news. 
            It should also contain instructions to rank news based on the user's preferences.""",
    )
    next_survey_question: str | None = Field(
        default=None, description="The next new preference question to ask the user"
    )


class NewsPreferenceAgentError(Enum):
    # Incoming survey question's parent message id does not match the last message in chat history
    MISSING_ANSWER = 0
    MISSING_QUESTION_FOR_ANSWER = 1


_llm = langchain_gemini_client.with_structured_output(NewsPreferenceAgentOutput)
_survey_generation_system_message = SystemMessage(
    content="""You are a news preference survey agent. Your task is to ask the user questions about their news preferences.
    - Ask one question at a time and wait for the user's response. 
    - After each response, Determine if you have enough information to summarize the user's news preferences. 
    -- If you do, you will return the summary in the `news_preference_summary` field.
    -- If not, you will return the next question to ask in the `next_survey_question` field.
    - Ask questions to help you determine the order of importance of different news topics for the user.
    - Since you will show user a summary of weekly news, you should ask questions which help you understand how to 
        make the user more likely and comfortable to read the summary.
    - Introduce yourself as a news preference survey agent and explain the purpose of the survey to the user first."""
)
_prompt = ChatPromptTemplate.from_messages(
    [
        _survey_generation_system_message,
        # Workaround for Gemini. The Gemini api request must have a content
        # field which is only from HumanMessage or AIMessage. So add a dummy
        # AIMessage to the prompt to satisfy this requirement.
        AIMessage(content="Let's start"),
        MessagesPlaceholder("chat_history"),
    ]
)
_new_preference_survey_agent = _prompt | _llm


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
        return [ApiConversationHistoryItem(**item) for item in cached_history]
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
        json.dumps([item.model_dump() for item in api_survey_history]),
        ex=3600,
    )  # Cache for 1 hour

    return api_survey_history


def next_preference_question(
    chat_history: list[ApiConversationHistoryItem], api_latency_log: ApiLatencyLog
) -> NewsPreferenceAgentOutput:
    llm_start_time = time.time()
    llm_result = _new_preference_survey_agent.invoke(
        {
            "chat_history": [
                item.human_message
                or item.ai_message
                or item.tool_message
                or item.system_message
                for item in chat_history
            ]
        }
    )
    api_latency_log.llm_elapsed_time_ms = (
        api_latency_log.llm_elapsed_time_ms
        if api_latency_log.llm_elapsed_time_ms
        else 0
    ) + int(
        (time.time() - llm_start_time) * 1000
    )  # Convert to milliseconds
    return llm_result


class NextPreferenceSurveyMessage(BaseModel):
    parent_message_id: str | None = None
    next_survey_question: str | None = None
    next_survey_question_message_id: str | None = None
    preference_summary: str | None = None


async def save_answer_and_generate_next_question(
    user_id: int,
    answer: str | None,
    parent_message_id: str | None,
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
        raise ValueError(
            error_type=NewsPreferenceAgentError.MISSING_QUESTION_FOR_ANSWER
        )
    elif answer is None and chat_history:
        # If the last message ID does not match the parent message ID, raise an error
        raise ValueError(error_type=NewsPreferenceAgentError.PARENT_MESSAGE_NOT_MATCH)
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
            human_message=HumanMessage(content=answer),
        )
        chat_history.append(answer_conversation_item)
        message_to_save.append(answer_conversation_item)

    next_question_or_summary = next_preference_question(
        chat_history, api_latency_log=api_latency_log
    )
    if next_question_or_summary.next_survey_question is not None:
        question_conversation_item = ApiConversationHistoryItem(
            user_id=user_id,
            thread_id=thread_id,
            message_id=create_message_id(),
            ai_message=AIMessage(content=next_question_or_summary.next_survey_question),
        )
        if chat_history:
            question_conversation_item.parent_message_id = chat_history[-1].message_id
        chat_history.append(question_conversation_item)
        message_to_save.append(question_conversation_item)

    # Update Redis cache
    redis_key = _get_news_preference_survey_history_key(user_id)
    await redis.set(
        redis_key, json.dumps([item.model_dump() for item in chat_history]), ex=3600
    )  # Cache for 1 hour

    sql_client.add_all(
        [
            convert_api_conversation_history_item_to_db_row(
                item, user_id, ConversationType.news_preference_survey
            )
            for item in message_to_save
        ]
    )
    sql_client.commit()
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
