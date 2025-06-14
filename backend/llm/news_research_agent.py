from .client_proxy import (
    LlmMessage,
    LlmMessageType,
    FunctionCallMessage,
    FunctionResponseMessage,
    LlmClientProxy,
    EmbeddingTaskType,
)
from .tracker import LlmTracker, exceed_llm_token_limit
from sqlalchemy.orm import Session
import re
from .client_proxy_factory import get_default_client_proxy
from pydantic import BaseModel, Field
from db.models.common import ConversationHistory, ConversationType, User, MessageType
from utils.conversation_history import (
    ApiConversationHistoryItem,
    convert_to_api_conversation_history,
    create_thread_id,
    create_message_id,
)
from db.models import (
    RssFeed,
    NewsEntry,
)
from enum import Enum
from datetime import  datetime, timedelta
from utils.logger import logger
from .agent_utils import from_db_conversation_history_to_llm_message, crawl_and_summarize_url
from sqlalchemy import or_, and_
import asyncio

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
    subscribed_rss_feeds_ids: list[int],
    llm_client: LlmClientProxy,
    sql_client: Session,
    sub_questions: list[str],
    period: Period | None = None,
) -> str:
    return __search_news_entries_by_text_embedding(
        subscribed_rss_feeds_ids=subscribed_rss_feeds_ids,
        llm_client=llm_client,
        sql_client=sql_client,
        query_list=sub_questions,
        embedding_task_type=EmbeddingTaskType.QUESTION_ANSWERING,
        period=period,
    )


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
    subscribed_rss_feeds_ids: list[int],
    llm_client: LlmClientProxy,
    sql_client: Session,
    terms: list[str],
    period: Period | None = None,
) -> str:
    return __search_news_entries_by_text_embedding(
        subscribed_rss_feeds_ids=subscribed_rss_feeds_ids,
        llm_client=llm_client,
        sql_client=sql_client,
        query_list=terms,
        embedding_task_type=EmbeddingTaskType.RETRIEVAL_QUERY,
        period=period,
    )


class ExpandNewsUrl(BaseModel):
    """
    Expand the news URL to get summarized content of the news article.
    You MUST use this API when you want to dig into detailed content in URL.
    """

    url: str = Field(
        description="news URL to expand",
    )


def __expand_news_url(
    llm_tracker: LlmTracker,
    url: str,
) -> str:
    return asyncio.run(crawl_and_summarize_url(url=url, llm_tracker=llm_tracker))


TEXT_SEARCH_RESPONSE_TEMPLATE = """
    News entries for {text}:
    {news_entries}
"""

NEWS_ENTRY_LIMIT_PER_QUERY = 100


def __search_news_entries_by_text_embedding(
    subscribed_rss_feeds_ids: list[int],
    llm_client: LlmClientProxy,
    sql_client: Session,
    query_list: list[str],
    embedding_task_type: EmbeddingTaskType,
    period: Period | None = None,
) -> str:
    embeddings = llm_client.embed_content(
        contents=query_list, task_type=embedding_task_type
    )
    from_time = datetime.fromtimestamp(0)
    if period == Period.LAST_WEEK:
        from_time = datetime.now() - timedelta(weeks=1)
    elif period == Period.LAST_MONTH:
        from_time = datetime.now() - timedelta(days=30)
    elif period == Period.LAST_QUARTER:
        from_time = datetime.now() - timedelta(days=90)
    elif period == Period.LAST_HALF_YEAR:
        from_time = datetime.now() - timedelta(days=180)

    response_list = []
    for idx, query in enumerate(query_list):
        embedding = embeddings[idx]
        news_entry_list = (
            sql_client.query(NewsEntry)
            .filter(
                NewsEntry.rss_feed_id.in_(subscribed_rss_feeds_ids),
                NewsEntry.summary_document_retrieval_embedding.is_not(None),
                or_(
                    and_(NewsEntry.pub_time >= from_time),
                    and_(
                        NewsEntry.pub_time.is_(None),
                        NewsEntry.crawl_time >= from_time,
                    ),
                ),
            )
            .order_by(
                NewsEntry.summary_document_retrieval_embedding.cosine_distance(
                    embedding
                )
            )
            .limit(NEWS_ENTRY_LIMIT_PER_QUERY)
            .all()
        )
        sorted_news_entry_list = sorted(
            news_entry_list,
            key=lambda news_entry: (news_entry.pub_time or news_entry.crawl_time),
            reverse=True,
        )
        simple_news_entries = [
            {
                "title": news_entry.title,
                "content": news_entry.content or "",
                "description": news_entry.description or "",
                "publish_time": (news_entry.pub_time or news_entry.crawl_time)
                .date()
                .isoformat(),
                "url": news_entry.entry_url or "",
            }
            for news_entry in sorted_news_entry_list
        ]

        response_list.append(
            TEXT_SEARCH_RESPONSE_TEMPLATE.format(
                text=query, news_entries=simple_news_entries
            )
        )
        return "\n".join(response_list)


CHAT_HISTORY_LIMIT = 100
MAX_REACT_MESSAGES = 100


def answer_user_question(
    user_id: int,
    user_question: str,
    thread_id: str | None,
    parent_message_id: str | None,
    sql_client: Session,
) -> list[ApiConversationHistoryItem]:
    if exceed_llm_token_limit(user_id):
        raise ValueError(f"User {user_id} has exceeded the LLM token limit this month.")
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
        user_id=user_id,
        thread_id=thread_id,
        message_id=create_message_id(),
        parent_message_id=parent_message_id,
        content=user_question,
        message_type=MessageType.HUMAN,
        conversation_type=ConversationType.news_research,
    )
    sql_client.add(user_question_item)
    ai_answer_item = ConversationHistory(
        user_id=user_id,
        thread_id=thread_id,
        message_id=create_message_id(),
        parent_message_id=user_question_item.message_id,
        content=final_answer,
        message_type=MessageType.AI,
        conversation_type=ConversationType.news_research,
    )
    sql_client.add(ai_answer_item)
    return convert_to_api_conversation_history([user_question_item, ai_answer_item])


def __answer_question_in_react_mode(
    user_id: int,
    user_question: str,
    chat_history: list[LlmMessage],
    sql_client: Session,
) -> str:
    subscribed_rss_feeds_ids = (
        sql_client.query(User.subscribed_rss_feeds_id)
        .filter(RssFeed.user_id == user_id)
        .one_or_none()[0]
    )
    react_intermediate_messages = [
        LlmMessage(type=LlmMessageType.HUMAN, text_content=user_question)
    ]
    system_prompt = __system_prompt.format(chat_history=chat_history)
    llm_client = get_default_client_proxy()
    tracker = LlmTracker(user_id)
    tracker.start()
    logger.info("question answering react agent starts.")
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
        logger.info(
            f"LLM response messages: {[msg.type for msg in response_llm_messages]}"
        )
        # Remove previous function responses
        while (
            react_intermediate_messages.peek().type == LlmMessageType.FUNCTION_RESPONSE
        ):
            react_intermediate_messages.pop()

        for llm_message in response_llm_messages:
            if llm_message.type == LlmMessageType.AI:
                if not llm_message.text_content:
                    raise ValueError(
                        "LLM non function call response does not contain text content."
                    )
                final_answer_match = re.search(
                    r"Final Answer:\s*(.*)", llm_message.text_content, re.DOTALL
                ).group(1)
                if final_answer_match:
                    tracker.end()
                    logger.info("Final answer generated from LLM.")
                    return final_answer_match
                react_intermediate_messages.append(llm_message)
            elif llm_message.type == LlmMessageType.FUNCTION_CALL:
                # Handle function calls here if needed
                react_intermediate_messages.append(llm_message)
                react_intermediate_messages.append(
                    LlmMessage(
                        type=LlmMessageType.FUNCTION_RESPONSE,
                        function_response=__call_function_for_llm(
                            subscribed_rss_feeds_ids=subscribed_rss_feeds_ids,
                            function_call_message=llm_message.function_call,
                            llm_client=llm_client,
                            sql_client=sql_client,
                            llm_tracker=tracker,
                        ),
                    )
                )
    tracker.end()
    raise ValueError("No final answer generated from the LLM.")


def __call_function_for_llm(
    subscribed_rss_feeds_ids: list[int],
    function_call_message: FunctionCallMessage,
    llm_client: LlmClientProxy,
    sql_client: Session,
    llm_tracker: LlmTracker,
) -> FunctionResponseMessage:
    function_response = FunctionResponseMessage(
        id=function_call_message.id,
        name=function_call_message.name,
    )
    try:
        if function_call_message.name == "CollectAnswerMaterialForSubQuestions":
            sub_questions = function_call_message.args.get("sub_questions", [])
            period = function_call_message.args.get("period", None)
            function_response.output = __collect_answer_material_for_sub_questions(
                subscribed_rss_feeds_ids=subscribed_rss_feeds_ids,
                llm_client=llm_client,
                sql_client=sql_client,
                sub_questions=sub_questions,
                period=period,
            )
        elif function_call_message.name == "SearchTerms":
            terms = function_call_message.args.get("terms", [])
            period = function_call_message.args.get("period", None)
            function_response.output = __search_terms(
                subscribed_rss_feeds_ids=subscribed_rss_feeds_ids,
                llm_client=llm_client,
                sql_client=sql_client,
                terms=terms,
                period=period,
            )
        elif function_call_message.name == "ExpandNewsUrl":
            url = function_call_message.args.get("url", "")
            function_response.output = __expand_news_url(
                llm_tracker=llm_tracker,
                url=url,
            )
        else:
            raise ValueError(f"Unsupported function call: {function_call_message.name}")
    except Exception as e:
        logger.error(f"Error calling function {function_call_message.name}: {str(e)}")
        function_response.error = "failed"

    return function_response
