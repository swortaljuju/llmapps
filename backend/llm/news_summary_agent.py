from .clients import langchain_gemini_client, langchain_gemini_embedding_client
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from sqlalchemy.orm import Session, Query
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from db.models import NewsEntry, NewsPreferenceApplicationExperiment, NewsChunkingExperiment, NewsSummaryPeriod, NewsSummaryEntry, User
from datetime import datetime, date, timedelta
from backend.constants import HTTP_HEADER_USER_AGENT
import requests
from backend.utils.logger import logger
from backend.db.db import get_sql_db, SqlSessionLocal
from sqlalchemy import select
from backend.utils.date_helper import determine_start_date, get_period_length
from backend.constants import SQL_BATCH_SIZE


### Prompt templates for summarizing news entries
SUMMARY_WITH_USER_PREFERENCE_AND_CHUNKED_DATA_PROMPT = """
    You are an AI assistant that summarizes and merges news entries into a list of summaries entries. 
    You should summarize based on the following user preferences:
    User preferences:
    {user_preferences}
    
    You should also assess the importance of each news summary based on the user preferences and order from high importance to low importance.
    Thirdly, you should write the summary in accordance with the user preferences.
    If some news entries are similar, you should summarize and merge them into one news summary entry while keeping their reference urls
    For example, if the following two news entries are similar:
    {title: "title 1", content: "content 1", url: "https://example.com/1"}
    {title: "title 2", content: "content 2", url: "https://example.com/2"}
    then the output should be:
    {title: "title summary", content: "content summary", url: ["https://example.com/1", "https://example.com/2"]}
    
    If allow_expand is true, then you should expand 10 most important preferred news summary entries 
    by crawling and summarizing the reference urls and rewrite the summary in accordance with the user preferences.
    
    Allow expand: {allow_expand}
    
    News entries:
    {news_entries}
"""

# Summary without user preference prompt
SUMMARY_PER_CLUSTERING_GROUP_PROMPT = """
    Summarize and merge the following news entries into one summary entry per group.
    News entries:
    {news_entries}
"""

RANK_AND_EXPAND_PER_CLUSTERING_GROUP_PROMPT = """
    - Rank news summary entries based on their importance and an optional user preference. Order from high importance to low importance. 
    - Pick most important preferred news summary entries and expand their details by visiting their reference url.
    - Rewrite the summary in accordance with the user preferences.
    User preferences:
    {user_preferences}
    
    News Summary entries:
    {news_entries}
"""

# News summary without user preference output    
class NewsSummaryOutput(BaseModel):
    """
    Generated news summary entry. Each entry is a summary of multiple news entries. 
    """
    title : str = Field(
        default="",
        description="""Summarized from news entries' title. """)
    content: str | None = Field(
        default=None,
        description="""Summarized from news entries' contents. """)
    reference_urls: list[str] = Field(
        default=[],
        description="""The summarized news entries' reference URLs. """)

__model_with_simple_summary_output = langchain_gemini_client.with_structured_output(NewsSummaryOutput)


class NewsSummaryListOutput(BaseModel):
    """
    Generated list of news summary entries. Each entry is a summary of multiple news entries or news summaries.
    """
    summary_entry: list[NewsSummaryOutput] | None = Field(
        default=None,
        description="""The list of news summaries. """)   

__model_with_simple_summary_list_output = langchain_gemini_client.with_structured_output(NewsSummaryListOutput)

class NewsSummaryWithPreferenceAppliedOutput(BaseModel):
    """
    Generated news summary entry. Each entry is a summary of multiple news entries. 
    If based on the user preference and other factors, the summary should be expanded, then crawl the reference urls 
    and summarize them into a paragraph less than 100 words and put the summary in the content field. 
    If you fail to crawl the reference urls, then set failed_to_expand to True and set the content to None.
    """
    title : str = Field(
        default=None,
        description="""Summary of news entries' title. """)
    content: str | None = Field(
        default=None,
        description="""Summary of news entries' contents or summary of expanded contents from reference urls.""")
    reference_urls: list[str] = Field(
        default=None,
        description="""The summarized news entries' reference URLs. """)
    should_expand: bool = Field(
        default=False,
        description="""True if the summary should be expanded based on user preference or its importance. """)
    failed_to_expand: bool = Field(
        default=False,
        description="""True if you fail to crawl and summarize the content in the reference urls. """) 
    
class NewsSummaryWithPreferenceAppliedListOutput(BaseModel):
    """
    Generated list of news summary entries. Each entry is a summary of multiple news entries.
    """
    summary_entry: list[NewsSummaryWithPreferenceAppliedOutput] | None = Field(
        default=None,
        description="""The list of news summaries. """)   

__model_with_preference_applied_summary_list_output = langchain_gemini_client.with_structured_output(NewsSummaryWithPreferenceAppliedListOutput)

# The basic period for chunking news entries
BASE_CHUNK_PERIOD = NewsSummaryPeriod.daily

def summarize_news(
    news_preference_application_experiment: NewsPreferenceApplicationExperiment, 
    news_chunking_experiment: NewsChunkingExperiment, 
    user_id: int, end_date: date, period: NewsSummaryPeriod):
    if period == NewsSummaryPeriod.monthly:
        raise NotImplementedError("Monthly summary is not supported yet")
    # if in the middle of a period, we will just summarize the news entries from the start of the period to the current time
    sql_client = get_sql_db()
    user_data = sql_client.execute(select(User.news_preference, User.subscribed_rss_feeds_id).where(User.id == user_id)).one()
    start_date = determine_start_date( period, end_date)
    news_preference = None
    if news_preference_application_experiment == NewsPreferenceApplicationExperiment.APPLY_PREFERENCE:
        news_preference = user_data.news_preference
        
    if news_chunking_experiment == NewsChunkingExperiment.AGGREGATE_DAILY:
        __chunk_and_summarize_news(user_id, start_date, end_date + timedelta(days=1), user_data.subscribed_rss_feeds_id, period, news_preference)
    elif news_chunking_experiment == NewsChunkingExperiment.EMBEDDING_CLUSTERING:
        __cluster_and_summarize_news(news_entry_list, news_preference)    

# NewsChunkingExperiment.AGGREGATE_DAILY
def __chunk_and_summarize_news(
    user_id: int, start_date: date, end_date: date, subscribed_feed_id_list: list[int],
    aggregate_period_type: NewsSummaryPeriod, 
    news_preference: str | None) -> list[NewsSummaryWithPreferenceAppliedOutput]:
    # based on news entry token count, chunk them per smaller period, summarize them per chunk and then merge the summaries
    # into one summary. Currently, we only support daily chunking

    # summarize daily first 
    __chunk_and_summarize_news_per_period(user_id, start_date, end_date, subscribed_feed_id_list, BASE_CHUNK_PERIOD, news_preference)
    # aggregate to whole period
    if aggregate_period_type != BASE_CHUNK_PERIOD:
        __chunk_and_summarize_news_per_period(user_id, start_date, end_date, subscribed_feed_id_list, aggregate_period_type, news_preference)

# For NewsPreferenceApplicationExperiment.WITH_SUMMARIZATION_PROMPT experiment   
def __chunk_and_summarize_news_per_period(user_id: int, start_date: date, end_date: date, subscribed_feed_id_list: list[int], target_period_type: NewsSummaryPeriod, news_preference: str | None):
    current_date = start_date
    news_preference_experiment = NewsPreferenceApplicationExperiment.APPLY_PREFERENCE if news_preference else NewsPreferenceApplicationExperiment.NO_PREFERENCE
    news_chunking_experiment = NewsChunkingExperiment.AGGREGATE_DAILY
    for_base_period = target_period_type == BASE_CHUNK_PERIOD
    with SqlSessionLocal() as session:
        while current_date <= end_date:
            chunk_end = current_date + get_period_length(target_period_type)

            # Check if we already have summaries for this period in the database
            existing_summaries = session.query(NewsSummaryEntry).filter(
                NewsSummaryEntry.user_id == user_id,
                NewsSummaryEntry.start_date == current_date,
                NewsSummaryEntry.period_type == target_period_type,
                NewsSummaryEntry.news_preference_application_experiment == news_preference_experiment,
                NewsSummaryEntry.news_chunking_experiment == news_chunking_experiment
            ).count()
            
            if existing_summaries > 0:
                logger.info(f"Found existing summaries for {current_date}. Skipping...")
                current_date = chunk_end
                continue
            
            formatted_entries = []
            if for_base_period:
                # Query news entries for this chunk period
                chunk_entries = session.query(NewsEntry).filter(
                    NewsEntry.crawl_time >= current_date,
                    NewsEntry.crawl_time < chunk_end,
                    NewsEntry.rss_feed_id.in_(subscribed_feed_id_list)
                ).all()
                
                if not chunk_entries:
                    logger.info(f"No news entries found for {current_date}. Skipping...")
                    current_date = chunk_end
                    continue
                    
                logger.info(f"Found {len(chunk_entries)} news entries for {current_date}")
                
                # Format entries for the LLM
                for entry in chunk_entries:
                    entry_data = {
                        "title": entry.title,
                        "content":  ";".join([entry.description, entry.content]),
                        "reference url": entry.entry_url,
                        "pub_time": entry.pub_time.isoformat() if entry.pub_time else ""
                    }
                    formatted_entries.append(entry_data)
            else:
                # Query news entries for this chunk period
                chunk_entries = session.query(NewsSummaryEntry).filter(
                    NewsSummaryEntry.user_id == user_id,
                    NewsSummaryEntry.start_date == current_date,
                    NewsSummaryEntry.period_type == BASE_CHUNK_PERIOD,
                    NewsSummaryEntry.news_chunking_experiment == NewsChunkingExperiment.AGGREGATE_DAILY,
                    NewsSummaryEntry.news_preference_application_experiment == news_preference_experiment
                ).all()
                
                if not chunk_entries:
                    logger.info(f"No news summary entries found for {current_date}. Skipping...")
                    current_date = chunk_end
                    continue
                    
                logger.info(f"Found {len(chunk_entries)} news entries for {current_date}")
                
                # Format entries for the LLM
                for entry in chunk_entries:
                    entry_data = {
                        "title": entry.title,
                        "content": entry.content,
                        "reference urls": entry.reference_urls
                    }
                    formatted_entries.append(entry_data)
            
            # Invoke LLM to generate summary
            try:
                model = __model_with_preference_applied_summary_list_output if for_base_period else __model_with_simple_summary_list_output
                prompt = ChatPromptTemplate.from_template(SUMMARY_WITH_USER_PREFERENCE_AND_CHUNKED_DATA_PROMPT)
                
                summary_result = (prompt | model).invoke({
                    "user_preferences": news_preference or "No specific preferences",
                    "news_entries": formatted_entries,
                    "allow_expand": for_base_period
                })
                
                # Process results and prepare for expansion if needed
                if summary_result.summary_entry:
                    if for_base_period:
                        # Expand summaries based on user preference and importance
                        _expand_news_if_necessary(summary_result.summary_entry)
                    
                    # Create NewsSummaryEntry objects and save to database
                    for order, summary in enumerate(summary_result.summary_entry):
                        summary_entry = NewsSummaryEntry(
                            user_id=user_id,
                            start_date=current_date,
                            period_type=target_period_type,
                            news_chunking_experiment=news_chunking_experiment,
                            news_preference_application_experiment=news_preference_experiment,
                            title=summary.title,
                            content=summary.content,
                            reference_urls=summary.reference_urls,
                            clicked=False,  # Default to False, can be updated later
                            display_order_within_period=order 
                        )
                        session.add(summary_entry)
                    
                    # Commit the transaction to save to database
                    session.commit()
                    logger.info(f"Saved {len(summary_result.summary_entry)} summaries for {current_date}")
                else:
                    logger.warning(f"No summaries generated for {current_date}")
            except Exception as e:
                session.rollback()
                logger.error(f"Error summarizing news for {current_date}: {str(e)}")
                
            # Move to next period
            current_date = chunk_end

# NewsChunkingExperiment.EMBEDDING_CLUSTERING
def __cluster_and_summarize_news(news_entry_list: list[NewsEntry], news_preference: str | None) -> list[NewsSummaryWithPreferenceAppliedOutput]:
    # based on news entry embedding, cluster them and summarize each cluster
    pass


# For NewsPreferenceApplicationExperiment.AFTER_NEW_SUMMARIZATION experiment and NewsPreferenceApplicationExperiment.NO_PREFERENCE experiment
def __generate_news_summary_cluster(news_entry_list: Query[NewsEntry]) -> list[NewsSummaryOutput]:
    # summarize the news entries without user preference. Save a copy of this output to db under NO_PREFERENCE experiment
    pass

def __rank_expand_news_summary_cluster(news_entry_list: list[NewsSummaryOutput])-> list[NewsSummaryWithPreferenceAppliedOutput]:
    pass


__model_with_raw_summary_prompt = ChatPromptTemplate.from_messages(
    [
        ("user", "Summarize the following news into less than 100 words. The news is crawled from web. {content}"),
    ]
) | langchain_gemini_client

__model_with_web_search_prompt = ChatPromptTemplate.from_messages(
    [
        ("user", "Search the news content on the web based on given title and summarize into less than 100 words. {title}"),
    ]
) | langchain_gemini_client

__header = {
    'User-Agent': HTTP_HEADER_USER_AGENT
}

MAX_NEWS_SUMMARY_TO_EXPAND = 10

def _expand_news_if_necessary(news_summary_list:  list[NewsSummaryWithPreferenceAppliedOutput]):
    # If llm decide to expand the summary but fail to crawl it, we will crawl the reference urls and ask llm to summarize them
    # If we also fail to crawl the reference urls, we will just ask llm to search the title on the web and summarize the content
    # make sure headers contain correct user agent value
    expanded_news_count = 0
    for news_summary in news_summary_list:
        if expanded_news_count >= MAX_NEWS_SUMMARY_TO_EXPAND:
            break
        if news_summary.should_expand:
            expanded_news_count += 1
            if news_summary.failed_to_expand:
                if news_summary.reference_urls:
                    for url in news_summary.reference_urls:
                        try:
                            response = requests.get(url, headers=__header)
                            response.raise_for_status()  # This will raise an exception for HTTP errors
                            content = response.text
                            # summarize the content
                            summary = __model_with_raw_summary_prompt.invoke({"content": content})
                            if summary:
                                # update the content of the news summary
                                news_summary.content = summary.content
                                break
                        except requests.RequestException as e:
                            logger.error(f"Failed to crawl {url}: {e}")
                            news_summary.failed_to_expand = True
                if not news_summary.content:
                    search_result = __model_with_web_search_prompt.invoke({"title": news_summary.title})
                    news_summary.content = search_result.content
