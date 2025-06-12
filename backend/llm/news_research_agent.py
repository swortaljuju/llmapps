from .client_proxy import LlmMessage, LlmMessageType, FunctionCallMessage, FunctionResponseMessage, LlmClientProxy
from collections.abc import Callable
from typing import Any
from .tracker import LlmTracker
from sqlalchemy.orm import Session
import re
from .client_proxy_factory import get_default_client_proxy
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import redis.asyncio as redis
from db.models.common import ConversationHistory, ConversationType, User, MessageType
from db.models import ApiLatencyLog
from db.db import SqlSessionLocal
from utils.conversation_history import (
    ApiConversationHistoryItem,
    convert_to_api_conversation_history,
    create_thread_id,
    create_message_id,
    convert_api_conversation_history_item_to_db_row,
)
from db.models.newssummary import (
    RssFeed,
    NewsSummaryEntry,
    NewsPreferenceVersion,
    NewsPreferenceChangeCause,
)
import json
from enum import Enum
import datetime
from datetime import date
from sqlalchemy import select
from utils.logger import logger
from .common import from_db_conversation_history_to_llm_message

__system_prompt = """
    Answer a user's questions based on crawls news data. We have already crawled recent news from the user's subscribed channels.
    You generate sub questions and search terms to search in the crawled news data and answer the user's question. 
    You can generate more sub questions and search terms based on previous search results until enough news are retrieved to answer user's question.
    You should understand the user's question context based on chat history.
    {chat_history}

    Use the following format:

    Question: the input question you must answer
    Thought: you should always think about what to do next
    Action: execute a function call
    Observation: a summary of the action response.
    ... (this Thought/Action/Observation can repeat N times)
    Final Answer: the final answer to the original input question

    Begin!
    
    Question: 
"""


class Period(str, Enum):
    LAST_WEEK = "last_week"
    LAST_MONTH = "last_month"
    LAST_QUARTER = "last_quarter"
    LAST_HALF_YEAR = "last_half_year"
    ALL_TIME = "all_time"


class CollectAnswerMaterialForSubQuestions(BaseModel):
    """
    Collect potential answer material from the crawled news data based on the generated list of sub questions.
    You MUST use this API when you want to collect material for sub questions.
    """

    sub_questions: list[str] = Field(
        ...,
        description="list of sub questions",
    )
    period: Period | None = Field(
        description="Optional date range to search news data from. If user doesn't specify a date range, then set this to all_time. ",
    )

def __collect_answer_material_for_sub_questions(
    user_id: int,
    llm_client: LlmClientProxy,
    sql_client: Session,
    sub_questions: list[str],
    period: Period | None = None
) -> str:
    pass 

class SearchTerms(BaseModel):
    """
    Search for news data based on the list of search terms.
    You MUST use this API when you want to search news data based on the search terms.
    """
    terms: list[str] = Field(
        description="list of search terms",
    )
    period: Period | None = Field(
        description="Optional date range to search news data from. If user doesn't specify a date range, then set this to all_time. ",
    )

def __search_terms(
    user_id: int,
    llm_client: LlmClientProxy,
    sql_client: Session,
    terms: list[str],
    period: Period | None = None
) -> str:
    pass 

class ExpandNewsUrl(BaseModel):
    """
    Expand the news URL to get summarized content of the news article.
    You MUST use this API when you want to dig into detailed content in URL.
    """

    url: str = Field(
        description="news URL to expand",
    )

def __expand_news_url(
    user_id: int,
    llm_client: LlmClientProxy,
    sql_client: Session,
    url: str,
) -> str:
    pass 

CHAT_HISTORY_LIMIT = 100
MAX_REACT_MESSAGES = 100

def answer_user_question(
    user_id: int,
    user_question: str,
    thread_id: str | None,
    parent_message_id: str | None,
    sql_client: Session,
) -> list[ApiConversationHistoryItem]:
    user_ai_chat_history = []
    if thread_id:
        # Fetch chat history from the database
        db_conversation_history = (
            sql_client.query(ConversationHistory)
            .filter(
                ConversationHistory.user_id == user_id,
                ConversationHistory.thread_id == thread_id,
                ConversationHistory.conversation_type == ConversationType.news_research,
            )
            .order_by(ConversationHistory.id.desc())
            .limit(CHAT_HISTORY_LIMIT)
            .all()
        )
        if db_conversation_history[0].message_id != parent_message_id:
            raise ValueError(
                "Parent message ID does not match the last message in the thread."
            )
        user_ai_chat_history = [
            from_db_conversation_history_to_llm_message(item)
            for item in db_conversation_history.reverse()
        ]
    final_answer = __answer_question_in_react_mode(
        user_id=user_id,
        user_question=user_question,
        chat_history=user_ai_chat_history,
        sql_client=sql_client,
    )
    if not thread_id:
        thread_id = create_thread_id()
    user_question_item = ConversationHistory(
        user_id = user_id,
        thread_id = thread_id,
        message_id = create_message_id(),
        parent_message_id = parent_message_id,
        content = user_question,
        message_type = MessageType.HUMAN,
        conversation_type = ConversationType.news_research,
    )
    sql_client.add(user_question_item)
    ai_answer_item = ConversationHistory(
        user_id = user_id,
        thread_id = thread_id,
        message_id = create_message_id(),
        parent_message_id = user_question_item.message_id,
        content = final_answer, 
        message_type = MessageType.AI,
        conversation_type = ConversationType.news_research,
    )
    sql_client.add(ai_answer_item)
    return convert_to_api_conversation_history(
        [user_question_item, ai_answer_item])

def __answer_question_in_react_mode(
    user_id: int, 
    user_question: str, 
    chat_history: list[LlmMessage],
    sql_client: Session) -> str:
    react_intermediate_messages = [
        LlmMessage(type=LlmMessageType.HUMAN, text_content=user_question)
    ]
    system_prompt = __system_prompt.format(
        chat_history=chat_history
    )
    llm_client = get_default_client_proxy()
    tracker = LlmTracker(user_id)
    tracker.start()
    while len(react_intermediate_messages) < MAX_REACT_MESSAGES:
        response_llm_messages = llm_client.generate_content(
            prompt=react_intermediate_messages,
            system_prompt=system_prompt,
            tracker=tracker,
            tool_schemas=[
                CollectAnswerMaterialForSubQuestions,
                SearchTerms,
                ExpandNewsUrl,
            ],
        )
        # Remove previous function responses
        while react_intermediate_messages.peek().type == LlmMessageType.FUNCTION_RESPONSE:
            react_intermediate_messages.pop()
        
        for llm_message in response_llm_messages:
            if llm_message.type == LlmMessageType.AI:
                if not llm_message.text_content:
                    raise ValueError("LLM non function call response does not contain text content.")
                final_answer_match = re.search(r"Final Answer:\s*(.*)", llm_message.text_content, re.DOTALL).group(1)
                if final_answer_match:
                    tracker.end()   
                    return final_answer_match
                react_intermediate_messages.append(llm_message)
            elif llm_message.type == LlmMessageType.FUNCTION_CALL:
                # Handle function calls here if needed
                react_intermediate_messages.append(llm_message)
                react_intermediate_messages.append(
                    LlmMessage(
                        type=LlmMessageType.FUNCTION_RESPONSE,
                        function_response=__call_function_for_llm(
                            user_id=user_id,
                            function_call_message=llm_message.function_call,
                            llm_client=llm_client,
                            sql_client=sql_client,
                    )))
    tracker.end()    
    raise ValueError("No final answer generated from the LLM.")

def __call_function_for_llm( 
    user_id: int, 
    function_call_message: FunctionCallMessage,
    llm_client: LlmClientProxy,
    sql_client: Session) -> FunctionResponseMessage:
    function_response = FunctionResponseMessage(
        id=function_call_message.id,
        name=function_call_message.name,
    )
    try:
        if function_call_message.name == "CollectAnswerMaterialForSubQuestions":
            sub_questions = function_call_message.args.get("sub_questions", [])
            period = function_call_message.args.get("period", None)
            function_response.output = __collect_answer_material_for_sub_questions(
                user_id=user_id,
                llm_client=llm_client,
                sql_client=sql_client,
                sub_questions=sub_questions,
                period=period
            )
        elif function_call_message.name == "SearchTerms":
            terms = function_call_message.args.get("terms", [])
            period = function_call_message.args.get("period", None)
            function_response.output = __search_terms(
                user_id=user_id,
                llm_client=llm_client,
                sql_client=sql_client,
                terms=terms,
                period=period
            )
        elif function_call_message.name == "ExpandNewsUrl":
            url = function_call_message.args.get("url", "")
            function_response.output = __expand_news_url(
                user_id=user_id,
                llm_client=llm_client,
                sql_client=sql_client,
                url=url
            )
        else:
            raise ValueError(f"Unsupported function call: {function_call_message.name}")
    except Exception as e:
        function_response.error = str(e)

    return function_response
