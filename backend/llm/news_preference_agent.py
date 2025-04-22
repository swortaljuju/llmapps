from .clients import langchain_gemini_client
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from sqlalchemy.orm import Session
import redis.asyncio as redis
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from db.models.common import ConversationHistory, ConversationType
from utils.conversation_history import ApiConversationHistoryItem, convert_to_api_conversation_history, create_thread_id, create_message_id, convert_api_conversation_history_item_to_db_row
import json
from enum import Enum

class NewsPreferenceAgentOutput(BaseModel):
    """
    Represents the output of the news preference agent.
    """

    news_preference_summary: str = Field(
        description="The summary of the user's news preference if the survey is completed and no further action is needed"
    )
    next_survey_question: str = Field(
        description="The next new preference question to ask the user"
    )

class NewsPreferenceSurveyOneRoundConversationItem(BaseModel):
    """
    Represents a single round of conversation in the news preference survey.
    It contains the question asked and the user's answer.
    """
    parent_message_id: str | None = None
    question: str
    answer: str

class NewsPreferenceAgentError(Enum):
    # Incoming survey question's parent message id does not match the last message in chat history
    PARENT_MESSAGE_NOT_MATCH = 0

_llm = langchain_gemini_client.with_structured_output(NewsPreferenceAgentOutput)
_survey_generation_system_message = SystemMessage(
    content="""You are a news preference survey agent. Your task is to ask the user questions about their news preferences.
    You will ask one question at a time and wait for the user's response. After each response, you will determine if you have enough information
    to summarize the user's news preferences. If you do, you will return the summary in the `news_preference_summary` field.
    If not, you will return the next question to ask in the `next_survey_question` field."""
)
_prompt = ChatPromptTemplate.from_messages(
    [
        _survey_generation_system_message,
        MessagesPlaceholder("chat_history"),
    ]
)
_new_preference_survey_agent = _prompt | _llm

def _get_news_preference_survey_history_key(user_id: int) -> str:
    """
    Generates a Redis key for storing the news preference survey history for a user.
    """
    return f"news_preference_survey_history:{user_id}"

async def load_preference_survey_history(user_id: int, redis: redis.Redis, sql_client: Session) -> list[ApiConversationHistoryItem]:
    redis_key = _get_news_preference_survey_history_key(user_id)

    # Check if survey history exists in Redis
    if redis.exists(redis_key):
        # Load survey history from Redis
        cached_history = json.loads(await redis.get(redis_key))
        await redis.expire(redis_key, 3600)  # Extend TTL to 1 hour (3600 seconds)
        return [ApiConversationHistoryItem(**item) for item in cached_history]

    # If not in Redis, load from the database
    survey_history = sql_client.query(ConversationHistory).filter(
        ConversationHistory.user_id == user_id,
        ConversationHistory.conversation_type == ConversationType.news_preference_survey
    ).all()
    if not survey_history:
        # If no survey history found, return an empty list
        return []
    api_survey_history = convert_to_api_conversation_history(survey_history)
    
    redis.set(redis_key, json.dumps([item.model_dump() for item in api_survey_history]), ex=3600)  # Cache for 1 hour

    return api_survey_history

def next_preference_question(chat_history: list[ApiConversationHistoryItem]) -> NewsPreferenceAgentOutput:
    return _new_preference_survey_agent.invoke({"chat_history":  [
        item.human_message or item.ai_message or item.tool_message or item.system_message
        for item in chat_history
    ]})

def insert_preference_question_and_answer(
    user_id: int,
    one_survey_round: NewsPreferenceSurveyOneRoundConversationItem,
    chat_history: list[ApiConversationHistoryItem],
    redis: redis.Redis,
    sql_client: Session
) -> list[ApiConversationHistoryItem]:
    """
    Inserts a new question and answer into the chat history and updates Redis cache.
    """
    new_message = []
    if not chat_history:
        # If chat history is empty, create a new thread ID
        initial_system_conversation_item = ApiConversationHistoryItem(
            user_id=user_id,
            thread_id=create_thread_id(),
            message_id=create_message_id(),
            parent_message_id=None,
            system_message= _survey_generation_system_message
        )
        chat_history.append(initial_system_conversation_item)
        new_message.append(initial_system_conversation_item)
    elif chat_history[-1].message_id != one_survey_round.parent_message_id:
        # If the last message ID does not match the parent message ID, raise an error
        raise ValueError(error_type=NewsPreferenceAgentError.PARENT_MESSAGE_NOT_MATCH)   
    thread_id = chat_history[0].thread_id 
    question_conversation_item = ApiConversationHistoryItem(
        user_id=user_id,
        thread_id=thread_id,
        message_id=create_message_id(),
        parent_message_id=chat_history[-1].message_id ,
        human_message=AIMessage(content=one_survey_round.question)
    )
    chat_history.append(question_conversation_item)
    new_message.append(question_conversation_item)
    answer_conversation_item = ApiConversationHistoryItem(
        user_id=user_id,
        thread_id=thread_id,
        message_id=create_message_id(),
        parent_message_id=question_conversation_item.message_id,
        ai_message=HumanMessage(content=one_survey_round.answer)
    )
    chat_history.append(answer_conversation_item)
    new_message.append(answer_conversation_item)
    # Update Redis cache
    redis_key = _get_news_preference_survey_history_key(user_id)
    redis.set(redis_key, json.dumps([item.model_dump() for item in chat_history]), ex=3600)  # Cache for 1 hour
    sql_client.add_all([
        convert_api_conversation_history_item_to_db_row(item)
        for item in new_message
    ])
    sql_client.commit()
    return chat_history