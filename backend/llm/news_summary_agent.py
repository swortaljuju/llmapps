from .client_proxy_factory import get_default_client_proxy
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from db.models import (
    NewsEntry,
    NewsPreferenceApplicationExperiment,
    NewsChunkingExperiment,
    NewsSummaryPeriod,
    NewsSummaryEntry,
    User,
    RssFeed,
)
from datetime import datetime, date, timedelta
from utils.http import ua
import requests
from utils.logger import logger
from db.db import get_sql_db, SqlSessionLocal
from sqlalchemy import select
from utils.date_helper import (
    is_valid_period_start_date,
    determine_period_exclusive_end_date,
)
import numpy as np
from sklearn.cluster import KMeans
from llm.tracker import exceed_llm_token_limit, LlmTracker
import traceback
import asyncio

MAX_NEWS_SUMMARY_EACH_TURN = 25

### Prompt templates for summarizing news entries
SUMMARY_WITH_USER_PREFERENCE_AND_CHUNKED_DATA_PROMPT = """
    You are an AI assistant that summarizes and merges news entries into a list of summaries entries. 
    You should summarize based on the following user preferences:
    User preferences:
    {user_preferences}
    
    You should also assess the importance of each news summary based on the user preferences and order from high importance to low importance.
    Thirdly, you should write the summary in accordance with the user preferences.
    If some news entries are similar, you should summarize and merge them into one news summary entry while keeping their reference urls.
    Do NOT exceed 25 news summary entries in the output. Only keep the most important news summary entries.
    
    {expansion_instruction}
    
    News entries:
    {news_entries}
"""

EXPANSION_INSTRUCTION = """
    Among returned news summary entries, you should pick 10 most important and preferred news summary entries and summarize their reference urls. 
"""

# Aggregated summary
class AggregatedSummaryOutput(BaseModel):
    """
    Generated news summary entry. Each entry is a summary of multiple news entries.
    """

    title: str = Field(description="""Summarized from news entries' title. """)
    content: str | None = Field(
        description="""Summarized from news entries' content field. """
    )
    expanded_content: str | None = Field(
        description="""Summarized from news entries' expanded_content field. """
    )
    reference_urls: list[str] = Field(
        description="""The summarized news entries' reference URLs. Only keep 3 most important URLs. """
    )

class AggregatedSummaryListOutput(BaseModel):
    """
    A list of aggregated news summaries.
    """

    summaries: list[AggregatedSummaryOutput] = Field(
        max_items=MAX_NEWS_SUMMARY_EACH_TURN,
        description="""List of aggregated news summaries."""
    )

class NewsSummaryWithPreferenceAppliedOutput(BaseModel):
    """
    Generated news summary entry. Each entry is a summary of multiple news entries.
    If required, summarize the reference urls into a paragraph less than 100 words and put the summary in the expanded_content field.
    """

    title: str = Field(description="""Summary of news entries' title. """)
    content: str | None = Field(description="""Summary of news entries' contents.""")
    reference_urls: list[str] = Field(
        description="""The summarized news entries' reference URLs. Only keep 3 most important URLs. """
    )
    should_expand: bool = Field(
        description="""True if the summary should be expanded based on user preference or its importance. """
    )
    expanded_content: str | None = Field(
        description="""Optional. Summary of the reference urls' contents in accordance with the user preferences. None if failed to access the reference urls."""
    )
    
class NewsSummaryWithPreferenceAppliedListOutput(BaseModel):
    """
    A list of news summaries with user preferences applied.
    """

    summaries: list[NewsSummaryWithPreferenceAppliedOutput] = Field(
        max_items=MAX_NEWS_SUMMARY_EACH_TURN,
        description="""List of news summaries with user preferences applied."""
    )

# The basic period for chunking news entries
BASE_CHUNK_PERIOD = NewsSummaryPeriod.daily


async def summarize_news(
    news_preference_application_experiment: NewsPreferenceApplicationExperiment,
    news_chunking_experiment: NewsChunkingExperiment,
    user_id: int,
    start_date: date,
    period: NewsSummaryPeriod,
) -> list[NewsSummaryEntry]:
    if exceed_llm_token_limit(user_id):
        raise ValueError(f"User {user_id} has exceeded the LLM token limit this month.")
    if period == NewsSummaryPeriod.monthly:
        raise NotImplementedError("Monthly summary is not supported yet")
    if not is_valid_period_start_date(start_date, period):
        raise ValueError(
            f"Invalid start date {start_date} for period type {period}. Please provide a valid start date."
        )
    # if in the middle of a period, we will just summarize the news entries from the start of the period to the current time
    sql_client = get_sql_db()
    user_data = sql_client.execute(
        select(User.news_preference, User.subscribed_rss_feeds_id).where(
            User.id == user_id
        )
    ).one()
    news_preference = None
    if (
        news_preference_application_experiment
        == NewsPreferenceApplicationExperiment.APPLY_PREFERENCE
    ):
        news_preference = user_data.news_preference
    news_summary_entry_list = []
    llm_tracker = LlmTracker(user_id)
    llm_tracker.start()
    if news_chunking_experiment == NewsChunkingExperiment.AGGREGATE_DAILY:
        news_summary_entry_list = await __chunk_and_summarize_news(
            user_id,
            start_date,
            user_data.subscribed_rss_feeds_id,
            period,
            news_preference,
            llm_tracker,
        )
    elif news_chunking_experiment == NewsChunkingExperiment.EMBEDDING_CLUSTERING:
        news_summary_entry_list = await __cluster_and_summarize_news(
            user_id,
            start_date,
            user_data.subscribed_rss_feeds_id,
            period,
            news_preference,
            llm_tracker,
        )
    llm_tracker.end()
    return news_summary_entry_list


def __get_existing_news_summary_entries(
    session: Session,
    user_id: int,
    start_date: date,
    end_date: date,
    target_period_type: NewsSummaryPeriod,
    subscribed_feed_id_list: list[int],
    news_preference_application_experiment: NewsPreferenceApplicationExperiment,
    news_chunking_experiment: NewsChunkingExperiment,
    delete_if_outdated: bool = False,
) -> list[NewsSummaryEntry]:
    existing_summaries = (
        session.query(NewsSummaryEntry)
        .filter(
            NewsSummaryEntry.user_id == user_id,
            NewsSummaryEntry.start_date == start_date,
            NewsSummaryEntry.period_type == target_period_type,
            NewsSummaryEntry.news_preference_application_experiment
            == news_preference_application_experiment,
            NewsSummaryEntry.news_chunking_experiment == news_chunking_experiment,
        )
        .all()
    )
    if existing_summaries and existing_summaries[0].creation_time:
        # Get the latest creation time of news summaries for this period
        # Check if we need to regenerate summaries or use existing ones
        news_summary_creation_time = existing_summaries[0].creation_time
        if news_summary_creation_time >= (
            datetime(end_date.year, end_date.month, end_date.day)
        ):
            logger.info(
                f"News summaries already exist for period {start_date} to {end_date}. Skipping..."
            )
            return existing_summaries
        # Check minimum feed crawl time to see if new content is available
        max_feed_crawl_time = (
            session.query(func.max(RssFeed.last_crawl_time))
            .filter(RssFeed.id.in_(subscribed_feed_id_list))
            .scalar()
        )

        if news_summary_creation_time >= max_feed_crawl_time:
            logger.info(
                f"No new content since last summary generation for period {start_date} to {end_date}. Skipping..."
            )
            return existing_summaries
        if delete_if_outdated:
            # If we are deleting existing summaries, remove them first
            logger.info(
                f"Deleting existing summaries for period {start_date} to {end_date} before regenerating."
            )
            for summary in existing_summaries:
                session.delete(summary)
                session.flush()
    return []


# NewsChunkingExperiment.AGGREGATE_DAILY
async def __chunk_and_summarize_news(
    user_id: int,
    start_date: date,
    subscribed_feed_id_list: list[int],
    period_type: NewsSummaryPeriod,
    news_preference: str | None,
    llm_tracker: LlmTracker,
) -> list[NewsSummaryEntry]:
    # based on news entry token count, chunk them per smaller period, summarize them per chunk and then merge the summaries
    # into one summary. Currently, we only support daily chunking
    period_end_date = determine_period_exclusive_end_date(period_type, start_date)
    if period_type != BASE_CHUNK_PERIOD:
        base_summary_task = []
        for i in range(0, (period_end_date - start_date).days):
            current_date = start_date + timedelta(days=i)
            # summarize daily first
            base_summary_task.append(__chunk_and_summarize_news_per_period(
                user_id,
                current_date,
                subscribed_feed_id_list,
                BASE_CHUNK_PERIOD,
                news_preference,
                llm_tracker,
            ))
        await asyncio.gather(*base_summary_task)

    # aggregate to whole period
    news_summary_entry_list = await __chunk_and_summarize_news_per_period(
        user_id,
        start_date,
        subscribed_feed_id_list,
        period_type,
        news_preference,
        llm_tracker,
    )
    return news_summary_entry_list


# For NewsPreferenceApplicationExperiment.WITH_SUMMARIZATION_PROMPT experiment
async def __chunk_and_summarize_news_per_period(
    user_id: int,
    start_date: date,
    subscribed_feed_id_list: list[int],
    target_period_type: NewsSummaryPeriod,
    news_preference: str | None,
    llm_tracker: LlmTracker,
):
    news_preference_experiment = (
        NewsPreferenceApplicationExperiment.APPLY_PREFERENCE
        if news_preference
        else NewsPreferenceApplicationExperiment.NO_PREFERENCE
    )
    news_chunking_experiment = NewsChunkingExperiment.AGGREGATE_DAILY
    for_base_period = target_period_type == BASE_CHUNK_PERIOD
    end_date = determine_period_exclusive_end_date(target_period_type, start_date)
    with SqlSessionLocal() as session:
        existing_summary = __get_existing_news_summary_entries(
            session,
            user_id,
            start_date,
            end_date,
            target_period_type,
            subscribed_feed_id_list,
            news_preference_experiment,
            news_chunking_experiment,
            delete_if_outdated=True,
        )
        if existing_summary:
            # If existing summaries are found, return them
            logger.info(f"Using existing summaries for {start_date} to {end_date}")
            return existing_summary
        formatted_entries = []
        if for_base_period:
            # Query news entries for this chunk period
            chunk_entries = (
                session.query(NewsEntry)
                .filter(
                    __get_news_entry_filter_for_summarization(
                        start_date, end_date, subscribed_feed_id_list
                    )
                )
                .all()
            )

            if not chunk_entries:
                logger.info(f"No news entries found for {start_date}. Skipping...")
                return []

            logger.info(f"Found {len(chunk_entries)} news entries for {start_date}")

            # Format entries for the LLM
            for entry in chunk_entries:
                entry_data = {
                    "title": entry.title or "",
                    "content": ";".join([entry.description or "", entry.content or ""]),
                    "reference url": entry.entry_url,
                    "pub_time": entry.pub_time.isoformat() if entry.pub_time else "",
                }
                formatted_entries.append(entry_data)
        else:
            # Query news entries for this chunk period
            chunk_entries = (
                session.query(NewsSummaryEntry)
                .filter(
                    NewsSummaryEntry.user_id == user_id,
                    NewsSummaryEntry.start_date == start_date,
                    NewsSummaryEntry.period_type == BASE_CHUNK_PERIOD,
                    NewsSummaryEntry.news_chunking_experiment
                    == NewsChunkingExperiment.AGGREGATE_DAILY,
                    NewsSummaryEntry.news_preference_application_experiment
                    == news_preference_experiment,
                )
                .all()
            )

            if not chunk_entries:
                logger.info(
                    f"No news summary entries found for {start_date}. Skipping..."
                )
                return []

            logger.info(f"Found {len(chunk_entries)} news entries for {start_date}")

            # Format entries for the LLM
            for entry in chunk_entries:
                entry_data = {
                    "title": entry.title,
                    "content": entry.content or "",
                    "expanded content": entry.expanded_content or "",
                    "reference urls": entry.reference_urls,
                }
                formatted_entries.append(entry_data)

        # Invoke LLM to generate summary
        try:
            prompt = SUMMARY_WITH_USER_PREFERENCE_AND_CHUNKED_DATA_PROMPT.format_map(
                {
                    "user_preferences": news_preference or "No specific preferences",
                    "news_entries": formatted_entries,
                    "expansion_instruction": (
                        EXPANSION_INSTRUCTION if for_base_period else ""
                    ),
                }
            )
            summary_result = (await get_default_client_proxy().generate_content_async(
                    prompt=prompt,
                    tracker=llm_tracker,
                    output_object=(
                        NewsSummaryWithPreferenceAppliedListOutput
                        if for_base_period
                        else AggregatedSummaryListOutput
                    ),
                    max_retry=5,
                )).structured_output

            # Process results and prepare for expansion if needed
            if summary_result:
                logger.info(
                    f"Generated {len(summary_result.summaries)} summaries for {start_date}"
                )
                for summary in summary_result.summaries:
                    logger.info(summary.model_dump_json(indent=2))
                if for_base_period:
                    # Expand summaries based on user preference and importance
                    await __expand_news_if_necessary(summary_result.summaries, llm_tracker)
                added_summaries = []
                # Create NewsSummaryEntry objects and save to database
                for order, summary in enumerate(summary_result.summaries):
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
                        display_order_within_period=order,
                    )
                    added_summaries.append(summary_entry)
                    session.add(summary_entry)

                # Commit the transaction to save to database
                session.commit()
                logger.info(f"Saved {len(summary_result.summaries)} summaries for {start_date}")
                return __get_existing_news_summary_entries(
                    session,
                    user_id,
                    start_date,
                    end_date,
                    target_period_type,
                    subscribed_feed_id_list,
                    news_preference_experiment,
                    news_chunking_experiment,
                    delete_if_outdated=False,
                )
            else:
                return []
        except Exception as e:
            session.rollback()
            logger.error(f"Error summarizing news for {start_date}: {str(e)}")
            logger.error(traceback.format_exc())

CLUSTER_NUMBER = 10

# NewsChunkingExperiment.EMBEDDING_CLUSTERING
async def __cluster_and_summarize_news(
    user_id: int,
    start_date: date,
    subscribed_feed_id_list: list[int],
    target_period_type: NewsSummaryPeriod,
    news_preference: str | None,
    llm_tracker: LlmTracker,
) -> list[NewsSummaryEntry]:
    news_preference_experiment = (
        NewsPreferenceApplicationExperiment.APPLY_PREFERENCE
        if news_preference
        else NewsPreferenceApplicationExperiment.NO_PREFERENCE
    )
    news_chunking_experiment = NewsChunkingExperiment.EMBEDDING_CLUSTERING
    end_date = determine_period_exclusive_end_date(target_period_type, start_date)
    with SqlSessionLocal() as session:
        existing_summary = __get_existing_news_summary_entries(
            session,
            user_id,
            start_date,
            end_date,
            target_period_type,
            subscribed_feed_id_list,
            news_preference_experiment,
            news_chunking_experiment,
            delete_if_outdated=True,
        )
        if existing_summary:
            # If existing summaries are found, return them
            logger.info(f"Using existing summaries for {start_date} to {end_date}")
            return existing_summary
        news_entry_id_and_embeddings = (
            session.query(NewsEntry.id, NewsEntry.summary_clustering_embedding)
            .filter(
                __get_news_entry_filter_for_summarization(
                    start_date, end_date, subscribed_feed_id_list
                )
            )
            .all()
        )
        if not news_entry_id_and_embeddings:
            logger.info(f"No news summary entries found for {start_date}. Skipping...")
            return []
        # Process embeddings
        entry_id_with_non_empty_embedding = []
        embeddings_list = []

        # Filter out entries with None or empty embeddings
        for entry_id, embedding in news_entry_id_and_embeddings:
            if embedding.any():
                entry_id_with_non_empty_embedding.append(entry_id)
                embeddings_list.append(embedding)

        # Convert to numpy array if we have any valid embeddings
        if embeddings_list and len(embeddings_list) > 1:
            all_embeddings = np.array(embeddings_list)
            cluster_labels = KMeans(
                    n_clusters=CLUSTER_NUMBER,
                ).fit_predict(all_embeddings)

            # Group news entries by cluster
            clusters = {}
            for idx, label in enumerate(cluster_labels):
                if label not in clusters:
                    clusters[label] = []
                clusters[label].append(entry_id_with_non_empty_embedding[idx])

            logger.info(
                f"Found {len(clusters)} clusters for {start_date} with {len(entry_id_with_non_empty_embedding)} valid embeddings.")
            for cluster_id, entry_ids in clusters.items():
                logger.debug(
                    f"Cluster {cluster_id} has {len(entry_ids)} entries"
                )
            # Summarize each cluster
            try:
                summary_task_list_per_cluster = []
                for entry_ids in clusters.values():
                    summary_task_list_per_cluster.append(
                        __summarize_single_cluster(
                            session,
                            entry_ids,
                            news_preference,
                            llm_tracker,
                        )
                    )  
                summary_task_responses = await asyncio.gather(*summary_task_list_per_cluster)
                summary_list = []
                for summary_response in summary_task_responses:
                    if summary_response:
                        summary_list.extend(summary_response)
        
                logger.info(
                    f"Generated {len(summary_list)} summaries for {start_date}"
                )
                # Convert summary_list objects to dictionaries
                summaries_as_dicts = [
                    {
                        "title": summary.title,
                        "content": summary.content or "",
                        "expanded content": summary.expanded_content or "",
                        "reference urls": summary.reference_urls,
                    }
                    for summary in summary_list
                ]
                prompt = SUMMARY_WITH_USER_PREFERENCE_AND_CHUNKED_DATA_PROMPT.format_map(
                        {
                            "user_preferences": news_preference or "No specific preferences",
                            "news_entries": summaries_as_dicts,
                            "expansion_instruction": "",
                        })

                aggregated_summary = (await get_default_client_proxy().generate_content_async(
                        prompt=prompt,
                        tracker=llm_tracker,
                        output_object=AggregatedSummaryListOutput,
                        max_retry=5,
                    )).structured_output

                # Process results and prepare for expansion if needed
                if aggregated_summary.summaries:
                    for summary in aggregated_summary.summaries:
                        logger.info(summary.model_dump_json(indent=2))
                    added_summaries = []
                    # Create NewsSummaryEntry objects and save to database
                    for order, summary in enumerate(aggregated_summary.summaries):
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
                            display_order_within_period=order,
                        )
                        added_summaries.append(summary_entry)
                        session.add(summary_entry)

                    # Commit the transaction to save to database
                    session.commit()
                    return __get_existing_news_summary_entries(
                        session,
                        user_id,
                        start_date,
                        end_date,
                        target_period_type,
                        subscribed_feed_id_list,
                        news_preference_experiment,
                        news_chunking_experiment,
                        delete_if_outdated=False,
                    )
            except Exception as e:
                session.rollback()
                traceback.print_exc()
                logger.error(f"Error summarizing news for {start_date}: {str(e)}")
    return []

async def __summarize_single_cluster(
    session: Session,
    entry_ids: list[int],
    news_preference: str | None,
    llm_tracker: LlmTracker,
) -> list[NewsSummaryWithPreferenceAppliedOutput]:
    """
    Summarize a single cluster of news entries.
    """
    cluster_entries = session.query(NewsEntry).filter(NewsEntry.id.in_(entry_ids)).all()
                    
    # Format entries for the LLM
    formatted_entries = []
    for entry in cluster_entries:
        entry_data = {
            "title": entry.title,
            "content": ";".join(
                [entry.description or "", entry.content or ""]
            ),
            "reference url": entry.entry_url,
        }
        formatted_entries.append(entry_data)
    # Invoke LLM to generate summary per cluster
    prompt = SUMMARY_WITH_USER_PREFERENCE_AND_CHUNKED_DATA_PROMPT.format_map(
        {
            "user_preferences": news_preference or "No specific preferences",
            "news_entries": formatted_entries,
            "expansion_instruction": EXPANSION_INSTRUCTION ,
        }
    )
    logger.info(f"Summarizing cluster with {len(formatted_entries)} entries.")
    summary_list = await get_default_client_proxy().generate_content_async(
            prompt=prompt,
            tracker=llm_tracker,
            output_object=NewsSummaryWithPreferenceAppliedListOutput,
            max_retry=5,
        )
    if not summary_list.structured_output:
        logger.error(f"No summaries generated for the cluster. {summary_list}")
        raise ValueError(
            "Internal Error. No summaries generated for the cluster."
        )
    else :
        logger.info(f"Generated {len(summary_list.structured_output.summaries)} summaries for the cluster.")
        for summary in summary_list.structured_output.summaries:
            logger.debug(summary.model_dump_json(indent=2))
    await __expand_news_if_necessary(summary_list.structured_output.summaries, llm_tracker)
    return summary_list.structured_output.summaries

__raw_summary_prompt = "Summarize the following news into less than 100 words. The news is crawled from web. {content}"

__web_search_prompt = """
        Summarize the content in the urls into less than 100 words.
        {url}
        If you can't fetch content from the above urls, then search the news content on the web based on given title {title} 
    """

__header = {"User-Agent": ua.random}

MAX_NEWS_SUMMARY_TO_EXPAND = 10

async def __expand_single_news_summary(
    news_summary: NewsSummaryWithPreferenceAppliedOutput | NewsSummaryEntry,
    llm_tracker: LlmTracker,
):
    """
    Expand a single news summary if necessary.
    """
    if news_summary.reference_urls:
        for url in news_summary.reference_urls:
            try:
                response = requests.get(url, headers=__header, timeout=10)
                response.raise_for_status()  # This will raise an exception for HTTP errors
                content = response.text
                # summarize the content
                summary = (await get_default_client_proxy().generate_content_async(
                        prompt=__raw_summary_prompt.format_map(
                            {"content": content}
                        ),
                        tracker=llm_tracker,
                    )).text_content

                if summary:
                    # update the content of the news summary
                    news_summary.expanded_content = summary
                    break
            except Exception as e:
                logger.warning(f"Failed to crawl and summarize {url}: {e}")
    if not news_summary.expanded_content:
        try:
            search_result = (await get_default_client_proxy().generate_content_async(
                    prompt=__web_search_prompt.format_map(
                        {
                            "title": news_summary.title,
                            "url": news_summary.reference_urls,
                        }
                    ),
                    tracker=llm_tracker,
                )).text_content
            
            news_summary.expanded_content = search_result
        except Exception as e:
            logger.warning(f"Failed to search for {news_summary.title}: {e}")



async def __expand_news_if_necessary(
    news_summary_list: list[NewsSummaryWithPreferenceAppliedOutput],
    llm_tracker: LlmTracker,
):
    # If llm decide to expand the summary but fail to crawl it, we will crawl the reference urls and ask llm to summarize them
    # If we also fail to crawl the reference urls, we will just ask llm to search the title on the web and summarize the content
    # make sure headers contain correct user agent value
    expanded_news_count = 0
    logger.info(
        f"Expanding news summaries if necessary. Total summaries to expand: {len(news_summary_list)}"
    )
    for news_summary in news_summary_list:
        if expanded_news_count >= MAX_NEWS_SUMMARY_TO_EXPAND:
            break
        if news_summary.should_expand:
            expanded_news_count += 1
            if not news_summary.expanded_content:
                await __expand_single_news_summary(
                    news_summary, llm_tracker
                )

async def expand_news_summary(
    summary_entry: NewsSummaryEntry
):
    """
    Expand the news summary if necessary.
    """
    if exceed_llm_token_limit(summary_entry.user_id):
        raise ValueError(f"User {summary_entry.user_id} has exceeded the LLM token limit this month.")
    
    llm_tracker = LlmTracker(summary_entry.user_id)
    llm_tracker.start()
    await __expand_single_news_summary(summary_entry, llm_tracker)
    llm_tracker.end()

def __get_news_entry_filter_for_summarization(
    start_date: date, end_date: date, subscribed_feed_id_list: list[int]
):
    # Get news entries for the given user and period
    return and_(
        or_(
            and_(NewsEntry.pub_time >= start_date, NewsEntry.pub_time < end_date),
            and_(
                NewsEntry.pub_time.is_(None),
                NewsEntry.crawl_time >= start_date,
                NewsEntry.crawl_time < end_date,
            ),
        ),
        NewsEntry.rss_feed_id.in_(subscribed_feed_id_list),
    )
