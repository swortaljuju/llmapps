from .clients import langchain_gemini_client
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy.orm import Session
from sqlalchemy import func
from db.models import NewsEntry, NewsPreferenceApplicationExperiment, NewsChunkingExperiment, NewsSummaryPeriod, NewsSummaryEntry, User, RssFeed
from datetime import datetime, date, timedelta
from utils.http import ua
import requests
from utils.logger import logger
from db.db import get_sql_db, SqlSessionLocal
from sqlalchemy import select
from utils.date_helper import is_valid_period_start_date, determine_period_exclusive_end_date
import numpy as np
from sklearn.cluster import HDBSCAN
from langchain_core.callbacks import UsageMetadataCallbackHandler
from llm.tracker import exceed_llm_token_limit, LlmTracker
import traceback
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.runnables.utils import Input
from typing import Optional

### Prompt templates for summarizing news entries
SUMMARY_WITH_USER_PREFERENCE_AND_CHUNKED_DATA_PROMPT = """
    You are an AI assistant that summarizes and merges news entries into a list of summaries entries. 
    You should summarize based on the following user preferences:
    User preferences:
    {user_preferences}
    
    You should also assess the importance of each news summary based on the user preferences and order from high importance to low importance.
    Thirdly, you should write the summary in accordance with the user preferences.
    If some news entries are similar, you should summarize and merge them into one news summary entry while keeping their reference urls
    
    {expansion_instruction}
    
    News entries:
    {news_entries}
"""

EXPANSION_INSTRUCTION = """
    You should pick 10 most important and preferred news summary entries and summarize their reference urls.
"""

# Summary without user preference prompt
SUMMARY_PER_CLUSTERING_GROUP_PROMPT = """
    Summarize and merge the following news entries into one summary entry per group.
    News entries:
    {news_entries}
"""

RANK_AND_EXPAND_PER_CLUSTERING_GROUP_PROMPT = """
    - Rank news summary entries based on their importance and an optional user preference. Order from high importance to low importance. 
    - Pick most important and preferred news summary entries and summarize their reference url.
    User preferences:
    {user_preferences}
    
    News Summary entries:
    {news_entries}
"""

# Aggregated summary 
class AggregatedSummaryOutput(BaseModel):
    """
    Generated news summary entry. Each entry is a summary of multiple news entries. 
    """
    title : str = Field(
        default="",
        description="""Summarized from news entries' title. """)
    content: str | None = Field(
        default=None,
        description="""Summarized from news entries' content field. """)
    expanded_content: str | None = Field(
        default=None,
        description="""Summarized from news entries' expanded_content field. """)
    reference_urls: list[str] = Field(
        default=[],
        description="""The summarized news entries' reference URLs. """)

class AggregatedSummaryListOutput(BaseModel):
    """
    Generated list of news summary entries. Each entry is a summary of multiple news entries or news summaries.
    """
    summary_entry: list[AggregatedSummaryOutput] | None = Field(
        default=None,
        description="""The list of news summaries. """)   

__model_with_aggregated_summary_list_output = langchain_gemini_client.with_structured_output(AggregatedSummaryListOutput)

class NewsSummaryWithPreferenceAppliedOutput(BaseModel):
    """
    Generated news summary entry. Each entry is a summary of multiple news entries. 
    If required, summarize the reference urls into a paragraph less than 100 words and put the summary in the expanded_content field. 
    """
    title : str = Field(
        default=None,
        description="""Summary of news entries' title. """)
    content: str | None = Field(
        default=None,
        description="""Summary of news entries' contents.""")
    reference_urls: list[str] = Field(
        default=None,
        description="""The summarized news entries' reference URLs. """)
    should_expand: bool = Field(
        default=False,
        description="""True if the summary should be expanded based on user preference or its importance. """)
    expanded_content: str | None = Field(
        default=None,
        description="""Optional. Summary of the reference urls' contents in accordance with the user preferences. None if failed to access the reference urls.""")

class NewsSummaryWithPreferenceAppliedListOutput(BaseModel):
    """
    Generated list of news summary entries. Each entry is a summary of multiple news entries.
    Pick 10 most important and preferred news summary entries and summarize their reference urls.
    """
    summary_entry: list[NewsSummaryWithPreferenceAppliedOutput] | None = Field(
        default=None,
        description="""The list of news summaries. """)   

__model_with_preference_applied_summary_list_output = langchain_gemini_client.with_structured_output(NewsSummaryWithPreferenceAppliedListOutput)

# News summary without user preference output    
class ClusterSummaryOutput(BaseModel):
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

__model_with_cluster_summary_output = langchain_gemini_client.with_structured_output(ClusterSummaryOutput)

# The basic period for chunking news entries
BASE_CHUNK_PERIOD = NewsSummaryPeriod.daily

def summarize_news(
    news_preference_application_experiment: NewsPreferenceApplicationExperiment, 
    news_chunking_experiment: NewsChunkingExperiment, 
    user_id: int, start_date: date, period: NewsSummaryPeriod) -> list[NewsSummaryEntry]:
    if exceed_llm_token_limit(user_id):
        raise ValueError(f"User {user_id} has exceeded the LLM token limit this month.")
    if period == NewsSummaryPeriod.monthly:
        raise NotImplementedError("Monthly summary is not supported yet")
    if not is_valid_period_start_date(start_date, period):
        raise ValueError(f"Invalid start date {start_date} for period type {period}. Please provide a valid start date.")
    # if in the middle of a period, we will just summarize the news entries from the start of the period to the current time
    sql_client = get_sql_db()
    user_data = sql_client.execute(select(User.news_preference, User.subscribed_rss_feeds_id).where(User.id == user_id)).one()
    news_preference = None
    if news_preference_application_experiment == NewsPreferenceApplicationExperiment.APPLY_PREFERENCE:
        news_preference = user_data.news_preference
    usage_metadata_callback = UsageMetadataCallbackHandler()    
    news_summary_entry_list = []
    llm_tracker = LlmTracker(user_id)
    llm_tracker.start()
    if news_chunking_experiment == NewsChunkingExperiment.AGGREGATE_DAILY:
        news_summary_entry_list = __chunk_and_summarize_news(user_id, start_date, user_data.subscribed_rss_feeds_id, period, news_preference, llm_tracker)
    elif news_chunking_experiment == NewsChunkingExperiment.EMBEDDING_CLUSTERING:
        news_summary_entry_list = __cluster_and_summarize_news(user_id, start_date, user_data.subscribed_rss_feeds_id, period, news_preference, llm_tracker)
    llm_tracker.end()
    return news_summary_entry_list
        
def __get_existing_news_summary_entries(
    session: Session,
    user_id: int, start_date: date, end_date: date, target_period_type: NewsSummaryPeriod,
    subscribed_feed_id_list: list[int],
    news_preference_application_experiment: NewsPreferenceApplicationExperiment,
    news_chunking_experiment: NewsChunkingExperiment) -> list[NewsSummaryEntry]:    
    existing_summaries = session.query(NewsSummaryEntry).filter(
            NewsSummaryEntry.user_id == user_id,
            NewsSummaryEntry.start_date == start_date,
            NewsSummaryEntry.period_type == target_period_type,
            NewsSummaryEntry.news_preference_application_experiment == news_preference_application_experiment,
            NewsSummaryEntry.news_chunking_experiment == news_chunking_experiment).all()
    if existing_summaries and existing_summaries[0].creation_time: 
        # Get the latest creation time of news summaries for this period
        # Check if we need to regenerate summaries or use existing ones
        news_summary_creation_time = existing_summaries[0].creation_time
        if news_summary_creation_time >= (datetime(end_date.year, end_date.month, end_date.day)):
            logger.info(f"News summaries already exist for period {start_date} to {end_date}. Skipping...")
            return existing_summaries
        # Check minimum feed crawl time to see if new content is available
        max_feed_crawl_time = session.query(
            func.max(RssFeed.last_crawl_time)
        ).filter(
            RssFeed.id.in_(subscribed_feed_id_list)
        ).scalar()
        
        if news_summary_creation_time >= max_feed_crawl_time:
            logger.info(f"No new content since last summary generation for period {start_date} to {end_date}. Skipping...")
            return existing_summaries
    return []

# NewsChunkingExperiment.AGGREGATE_DAILY
def __chunk_and_summarize_news(
    user_id: int, start_date: date, subscribed_feed_id_list: list[int],
    period_type: NewsSummaryPeriod, 
    news_preference: str | None,
    llm_tracker: LlmTracker) -> list[NewsSummaryEntry]:
    # based on news entry token count, chunk them per smaller period, summarize them per chunk and then merge the summaries
    # into one summary. Currently, we only support daily chunking
    period_end_date = determine_period_exclusive_end_date(period_type, start_date)
    news_summary_entry_list = []
    for i in range(0, (period_end_date - start_date).days):
        current_date = start_date + timedelta(days=i)
        # summarize daily first 
        news_summary_entry_list = __chunk_and_summarize_news_per_period(user_id, current_date, subscribed_feed_id_list, BASE_CHUNK_PERIOD, news_preference, usage_metadata_callback)

    # aggregate to whole period
    if period_type != BASE_CHUNK_PERIOD:
        news_summary_entry_list = __chunk_and_summarize_news_per_period(user_id, start_date, subscribed_feed_id_list, period_type, news_preference, usage_metadata_callback)
    return news_summary_entry_list

# For NewsPreferenceApplicationExperiment.WITH_SUMMARIZATION_PROMPT experiment   
def __chunk_and_summarize_news_per_period(
    user_id: int, start_date: date, 
    subscribed_feed_id_list: list[int], 
    target_period_type: NewsSummaryPeriod, 
    news_preference: str | None,
    llm_tracker: LlmTracker):
    news_preference_experiment = NewsPreferenceApplicationExperiment.APPLY_PREFERENCE if news_preference else NewsPreferenceApplicationExperiment.NO_PREFERENCE
    news_chunking_experiment = NewsChunkingExperiment.AGGREGATE_DAILY
    for_base_period = target_period_type == BASE_CHUNK_PERIOD
    end_date = determine_period_exclusive_end_date(target_period_type, start_date)
    with SqlSessionLocal() as session:
        existing_summary = __get_existing_news_summary_entries(
            session, user_id, start_date, end_date, target_period_type,
            subscribed_feed_id_list, news_preference_experiment, news_chunking_experiment)
        if existing_summary:
            # If existing summaries are found, return them
            logger.info(f"Using existing summaries for {start_date} to {end_date}")
            return existing_summary    
        formatted_entries = []
        if for_base_period:
            # Query news entries for this chunk period
            chunk_entries = session.query(NewsEntry).filter(
                NewsEntry.crawl_time >= start_date,
                NewsEntry.crawl_time < end_date,
                NewsEntry.rss_feed_id.in_(subscribed_feed_id_list)
            ).all()
            
            if not chunk_entries:
                logger.info(f"No news entries found for {start_date}. Skipping...")
                return []
                
            logger.info(f"Found {len(chunk_entries)} news entries for {start_date}")
            
            # Format entries for the LLM
            for entry in chunk_entries:
                entry_data = {
                    "title": entry.title or '',
                    "content":  ";".join([entry.description or '', entry.content or '']),
                    "reference url": entry.entry_url,
                    "pub_time": entry.pub_time.isoformat() if entry.pub_time else ""
                }
                formatted_entries.append(entry_data)
        else:
            # Query news entries for this chunk period
            chunk_entries = session.query(NewsSummaryEntry).filter(
                NewsSummaryEntry.user_id == user_id,
                NewsSummaryEntry.start_date == start_date,
                NewsSummaryEntry.period_type == BASE_CHUNK_PERIOD,
                NewsSummaryEntry.news_chunking_experiment == NewsChunkingExperiment.AGGREGATE_DAILY,
                NewsSummaryEntry.news_preference_application_experiment == news_preference_experiment
            ).all()
            
            if not chunk_entries:
                logger.info(f"No news summary entries found for {start_date}. Skipping...")
                return []
                
            logger.info(f"Found {len(chunk_entries)} news entries for {start_date}")
            
            # Format entries for the LLM
            for entry in chunk_entries:
                entry_data = {
                    "title": entry.title,
                    "content": entry.content or '', 
                    "expanded content": entry.expanded_content or '',
                    "reference urls": entry.reference_urls
                }
                formatted_entries.append(entry_data)
        
        # Invoke LLM to generate summary
        try:
            model = __model_with_preference_applied_summary_list_output if for_base_period else __model_with_aggregated_summary_list_output
            prompt = ChatPromptTemplate.from_template(SUMMARY_WITH_USER_PREFERENCE_AND_CHUNKED_DATA_PROMPT)
            summary_result = __run_model_with_retry((prompt | model), {
                "user_preferences": news_preference or "No specific preferences",
                "news_entries": formatted_entries,
                "expansion_instruction": EXPANSION_INSTRUCTION if for_base_period else ""
            }, config={"callbacks": [usage_metadata_callback]})             
            # Process results and prepare for expansion if needed
            if summary_result and summary_result.summary_entry:
                logger.info(f"Generated summary for {start_date} with {summary_result.model_dump_json(indent=2)}")
                if for_base_period:
                    # Expand summaries based on user preference and importance
                    _expand_news_if_necessary(summary_result.summary_entry, usage_metadata_callback)
                added_summaries = []
                # Create NewsSummaryEntry objects and save to database
                for order, summary in enumerate(summary_result.summary_entry):
                    summary_entry = NewsSummaryEntry(
                        user_id=user_id,
                        start_date=start_date,
                        period_type=target_period_type,
                        news_chunking_experiment=news_chunking_experiment,
                        news_preference_application_experiment=news_preference_experiment,
                        title=summary.title,
                        content=summary.content,
                        expanded_content=summary.expanded_content,
                        reference_urls=summary.reference_urls,
                        clicked=False,  # Default to False, can be updated later
                        display_order_within_period=order 
                    )
                    added_summaries.append(summary_entry)
                    session.add(summary_entry)
                
                # Commit the transaction to save to database
                session.commit()
                logger.info(f"Saved {len(summary_result.summary_entry)} summaries for {start_date}")
                return __get_existing_news_summary_entries(
                    session, user_id, start_date, end_date, target_period_type,
                    subscribed_feed_id_list, news_preference_experiment, news_chunking_experiment)
            else:
                return []
        except Exception as e:
            session.rollback()
            logger.error(f"Error summarizing news for {start_date}: {str(e)}")
            logger.error(traceback.format_exc())

# NewsChunkingExperiment.EMBEDDING_CLUSTERING
def __cluster_and_summarize_news(
    user_id: int, start_date: date, 
    subscribed_feed_id_list: list[int],
    target_period_type: NewsSummaryPeriod, 
    news_preference: str | None,
    llm_tracker: LlmTracker) -> list[NewsSummaryEntry]:
    news_preference_experiment = NewsPreferenceApplicationExperiment.APPLY_PREFERENCE if news_preference else NewsPreferenceApplicationExperiment.NO_PREFERENCE
    news_chunking_experiment = NewsChunkingExperiment.EMBEDDING_CLUSTERING
    end_date = determine_period_exclusive_end_date(target_period_type, start_date)
    with SqlSessionLocal() as session:
        existing_summary = __get_existing_news_summary_entries(
            session, user_id, start_date, end_date, target_period_type,
            subscribed_feed_id_list, news_preference_experiment, news_chunking_experiment)
        if existing_summary:
            # If existing summaries are found, return them
            logger.info(f"Using existing summaries for {start_date} to {end_date}")
            return existing_summary 
        news_entry_id_and_embeddings = session.query(NewsEntry.id, NewsEntry.summary_embedding).filter(
                NewsEntry.crawl_time >= start_date,
                NewsEntry.crawl_time < end_date,
                NewsEntry.rss_feed_id.in_(subscribed_feed_id_list)
            ).all()
        if not news_entry_id_and_embeddings:
            logger.info(f"No news summary entries found for {start_date}. Skipping...")
            return []
        # Process embeddings
        entry_id_with_non_empty_embedding = []
        embeddings_list = []

        # Filter out entries with None or empty embeddings
        for entry_id, embedding in news_entry_id_and_embeddings:
            if embedding:
                entry_id_with_non_empty_embedding.append(entry_id)
                embeddings_list.append(embedding)

        # Convert to numpy array if we have any valid embeddings
        if embeddings_list and len(embeddings_list) > 1:
            all_embeddings = np.array(embeddings_list)
            cluster_labels = HDBSCAN().fit_predict(all_embeddings)
                
            # Group news entries by cluster
            clusters = {}
            for idx, label in enumerate(cluster_labels):
                if label != -1:  # -1 means noise point in HDBSCAN
                    if label not in clusters:
                        clusters[label] = []
                    clusters[label].append(entry_id_with_non_empty_embedding[idx])
                
            # Handle unclustered points as their own clusters
            for idx, label in enumerate(cluster_labels):
                if label == -1:
                    new_label = max(clusters.keys()) + 1 if clusters else 0
                    clusters[new_label] = [entry_id_with_non_empty_embedding[idx]]
            # Summarize each cluster
            try:
                summary_list = []
                for cluster_id, entry_ids in clusters.items():
                    # Get the news entries for this cluster
                    cluster_entries = session.query(NewsEntry).filter(
                        NewsEntry.id.in_(entry_ids)
                    ).all()
                                    
                    # Format entries for the LLM
                    formatted_entries = []
                    for entry in cluster_entries:
                        entry_data = {
                            "title": entry.title,
                            "content":  ";".join([entry.description or '', entry.content or '']),
                            "reference url": entry.entry_url,
                            "pub_time": entry.pub_time.isoformat() if entry.pub_time else ""
                        }
                        formatted_entries.append(entry_data)
                    
                    # Invoke LLM to generate summary per cluster
                    model = __model_with_cluster_summary_output
                    prompt = ChatPromptTemplate.from_template(SUMMARY_PER_CLUSTERING_GROUP_PROMPT)
                    
                    summary_result = __run_model_with_retry((prompt | model), {
                        "news_entries": formatted_entries
                    }, config={"callbacks": [usage_metadata_callback]})
                    
                    if summary_result: 
                        summary_list.append(summary_result)
                
                model = __model_with_preference_applied_summary_list_output
                prompt = ChatPromptTemplate.from_template(RANK_AND_EXPAND_PER_CLUSTERING_GROUP_PROMPT)
                # Convert summary_list objects to dictionaries
                summaries_as_dicts = [
                    {
                        "title": summary.title,
                        "content": summary.content,
                        "reference_urls": summary.reference_urls
                    }
                    for summary in summary_list
                ]
                
                rank_and_expand_result = __run_model_with_retry( (prompt | model), {
                    "user_preferences": news_preference or "No specific preferences",
                    "news_entries": summaries_as_dicts,
                }, config={"callbacks": [usage_metadata_callback]})
                
                # Process results and prepare for expansion if needed
                if rank_and_expand_result.summary_entry:
                    _expand_news_if_necessary(rank_and_expand_result.summary_entry, usage_metadata_callback)
                    added_summaries = []
                    # Create NewsSummaryEntry objects and save to database
                    for order, summary in enumerate(summary_result.summary_entry):
                        summary_entry = NewsSummaryEntry(
                            user_id=user_id,
                            start_date=start_date,
                            period_type=target_period_type,
                            news_chunking_experiment=news_chunking_experiment,
                            news_preference_application_experiment=news_preference_experiment,
                            title=summary.title,
                            content=summary.content,
                            expanded_content=summary.expanded_content,
                            reference_urls=summary.reference_urls,
                            clicked=False,  # Default to False, can be updated later
                            display_order_within_period=order 
                        )
                        added_summaries.append(summary_entry)
                        session.add(summary_entry)
                    
                    # Commit the transaction to save to database
                    session.commit()
                    return __get_existing_news_summary_entries(
                        session, user_id, start_date, end_date, target_period_type,
                        subscribed_feed_id_list, news_preference_experiment, news_chunking_experiment)
            except Exception as e:
                session.rollback()
                logger.error(f"Error summarizing news for {start_date}: {str(e)}")
    return []

def __run_model_with_retry(model: Runnable, input: Input, config: Optional[RunnableConfig] = None) -> AggregatedSummaryListOutput | NewsSummaryWithPreferenceAppliedListOutput | ClusterSummaryOutput:
    """
    Run the model with retry logic. If the model fails, it will retry up to 5 times. 
    If the input and output is large, gemini model may fail with MALFORMED_FUNCTION_CALL intermittently.
    """
    max_retries = 5
    for attempt in range(max_retries):
        logger.info(f"Attempt {attempt + 1} to run model")
        result = model.invoke(input, config=config)
        if result and (
            (isinstance(result, AggregatedSummaryListOutput) or 
            isinstance(result, NewsSummaryWithPreferenceAppliedListOutput)) and result.summary_entry
            or isinstance(result, ClusterSummaryOutput)
        ):
            return result

__model_with_raw_summary_prompt = ChatPromptTemplate.from_template(
    "Summarize the following news into less than 100 words. The news is crawled from web. {content}"
) | langchain_gemini_client

__model_with_web_search_prompt = ChatPromptTemplate.from_template(
    """
        Summarize the content in the urls into less than 100 words.
        {url}
        If you can't fetch content from the above urls, then search the news content on the web based on given title {title} 
    """
) | langchain_gemini_client

__header = {
    'User-Agent': ua.random
}

MAX_NEWS_SUMMARY_TO_EXPAND = 10

def _expand_news_if_necessary(
    news_summary_list:  list[NewsSummaryWithPreferenceAppliedOutput],
    llm_tracker: LlmTracker):
    # If llm decide to expand the summary but fail to crawl it, we will crawl the reference urls and ask llm to summarize them
    # If we also fail to crawl the reference urls, we will just ask llm to search the title on the web and summarize the content
    # make sure headers contain correct user agent value
    expanded_news_count = 0
    for news_summary in news_summary_list:
        if expanded_news_count >= MAX_NEWS_SUMMARY_TO_EXPAND:
            break
        if news_summary.should_expand:
            expanded_news_count += 1
            if not news_summary.expanded_content:
                if news_summary.reference_urls:
                    for url in news_summary.reference_urls:
                        try:
                            response = requests.get(url, headers=__header, timeout=10)
                            response.raise_for_status()  # This will raise an exception for HTTP errors
                            content = response.text
                            # summarize the content
                            summary = __model_with_raw_summary_prompt.invoke({"content": content}, config={"callbacks": [usage_metadata_callback]})
                            if summary:
                                # update the content of the news summary
                                news_summary.expanded_content = summary.content
                                break
                        except requests.RequestException as e:
                            logger.error(f"Failed to crawl {url}: {e}")
                if not news_summary.expanded_content:
                    search_result = __model_with_web_search_prompt.invoke({"title": news_summary.title, "url": news_summary.reference_urls}, config={"callbacks": [usage_metadata_callback]})
                    news_summary.expanded_content = search_result.content
