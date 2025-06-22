from .client_proxy_factory import get_default_client_proxy
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_, select
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
from utils.logger import logger
from db.db import get_sql_db, SqlSessionLocal
from utils.date_helper import (
    is_valid_period_start_date,
    determine_period_exclusive_end_date,
)
import numpy as np
from sklearn.cluster import KMeans
from llm.tracker import exceed_llm_token_limit, LlmTracker
import traceback
import asyncio
from .agent_utils import crawl_and_summarize_url
from utils.exceptions import UserErrorCode, ApiErrorType, ApiException

MAX_NEWS_SUMMARY_EACH_TURN = 25

### Prompt templates for summarizing news entries
SUMMARY_WITH_USER_PREFERENCE_AND_CHUNKED_DATA_PROMPT = """
    You are an AI assistant that summarizes news entries into a list of summary entries. 
    User preferences:
    {user_preferences}
    
    - Group the news into several categories and topics and then summarize. 
    - One category can have multiple topics.
    - Don't create too granular topics, but also don't make them too broad.
    - Decide the category, topic and selection of news entries based on the user preferences.
    - Assess the importance of each news summary based on the user preferences.
    - Write the summary in accordance with the user preferences.
    - Do NOT exceed {max_entry} news summary entries in the output. Only keep the most important news summary entries.
        
    News entries:
    {news_entries}
"""

class NewsSummaryOutput(BaseModel):
    """
    Generated news summary entry. 
    """
    category: str = Field(
        description="""Required. Category of the news summary."""
    )
    title: str = Field(description="""Title """)
    content: str | None = Field(description="""Content""")
    reference_urls: list[str] = Field(
        description="""The summarized news entries' reference URLs. Only keep 3 most important URLs. """
    )
    importance_score: int = Field(
        minimum=0,
        maximum=100,
        description="""Importance score of the news summary based on user preferences.
        The score is between 0 and 100, where 100 is the most important. Each number should be distinct in the list.
        """
    )
    
class NewsSummaryListOutput(BaseModel):
    """
    A list of news summaries with user preferences applied.
    """

    summaries: list[NewsSummaryOutput] = Field(
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
        else:
            return existing_summaries
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
        if exceed_llm_token_limit(user_id):
            raise ApiException(
                user_error_code=UserErrorCode.TOKEN_LIMIT_EXCEEDED,
                type=ApiErrorType.CLIENT_ERROR,
            )
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
                    "reference urls": entry.reference_urls,
                }
                formatted_entries.append(entry_data)

        # Invoke LLM to generate summary
        try:
            summary_result = await __generate_news_summary_from_chunked_data(
                    formatted_entries=formatted_entries,
                    news_preference=news_preference,
                    llm_tracker=llm_tracker,
                )

            # Process results and prepare for expansion if needed
            return await __save_and_return_summary_entry(
                    summary_list=summary_result,
                    user_id=user_id,
                    start_date=start_date,
                    end_date=end_date,
                    target_period_type=target_period_type,
                    subscribed_feed_id_list=subscribed_feed_id_list,
                    news_preference_experiment=news_preference_experiment,
                    news_chunking_experiment=news_chunking_experiment,
                    session=session,
                )
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
        if exceed_llm_token_limit(user_id):
            raise ApiException(
                user_error_code=UserErrorCode.TOKEN_LIMIT_EXCEEDED,
                type=ApiErrorType.CLIENT_ERROR,
            )
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
                    n_clusters=min(CLUSTER_NUMBER, len(all_embeddings)),
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
                        "reference urls": summary.reference_urls,
                    }
                    for summary in summary_list
                ]

                aggregated_summary = await __generate_news_summary_from_chunked_data(
                    formatted_entries=summaries_as_dicts,
                    news_preference=news_preference,
                    llm_tracker=llm_tracker,
                )

                # Process results and prepare for expansion if needed
                return await __save_and_return_summary_entry(
                    summary_list=aggregated_summary,
                    user_id=user_id,
                    start_date=start_date,
                    end_date=end_date,
                    target_period_type=target_period_type,
                    subscribed_feed_id_list=subscribed_feed_id_list,
                    news_preference_experiment=news_preference_experiment,
                    news_chunking_experiment=news_chunking_experiment,
                    session=session,
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
) -> list[NewsSummaryListOutput]:
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
    return await __generate_news_summary_from_chunked_data(formatted_entries, news_preference, llm_tracker)

async def __generate_news_summary_from_chunked_data(
    formatted_entries: list[dict],
    news_preference: str | None,
    llm_tracker: LlmTracker,
) -> list[NewsSummaryListOutput]:
    if not formatted_entries:
        logger.info("No news entries to summarize.")
        return []
    prompt = SUMMARY_WITH_USER_PREFERENCE_AND_CHUNKED_DATA_PROMPT.format_map(
        {
            "user_preferences": news_preference or "No specific preferences",
            "news_entries": formatted_entries,
            "max_entry": MAX_NEWS_SUMMARY_EACH_TURN
        }
    )
    logger.info(f"Summarizing with {len(formatted_entries)} entries.")
    summary_list = (await get_default_client_proxy().generate_content_async(
            prompt=prompt,
            tracker=llm_tracker,
            output_object=NewsSummaryListOutput,
            max_retry=5,
        ))[0]
    if not summary_list.structured_output:
        logger.error(f"No summaries generated. {summary_list}")
    else :
        logger.info(f"Generated {len(summary_list.structured_output.summaries)} summaries.")
        for summary in summary_list.structured_output.summaries:
            logger.info(summary.model_dump_json(indent=2))
    return summary_list.structured_output.summaries

async def __save_and_return_summary_entry(
    summary_list: list[NewsSummaryOutput],
    user_id: int,
    start_date: date,
    end_date: date,
    target_period_type: NewsSummaryPeriod,
    subscribed_feed_id_list: list[int],
    news_preference_experiment: NewsPreferenceApplicationExperiment,
    news_chunking_experiment: NewsChunkingExperiment,
    session: Session = None,
    ) -> list[NewsSummaryEntry]:
    """
    Save the generated summary entry to the database and return it.
    This function is a placeholder and should be implemented based on your database logic.
    """
    # Implement your logic to save the summary entry to the database
    # and return the saved entry or entries.
    
    # Process results and prepare for expansion if needed
    if summary_list:
        for summary in summary_list:
            logger.info(summary.model_dump_json(indent=2))
        added_summaries = []
        sorted_summaries = sorted(
            summary_list,
            key=lambda x: x.importance_score,
            reverse=True,
        )
        # Create NewsSummaryEntry objects and save to database
        for order, summary in enumerate(sorted_summaries):
            summary_entry = NewsSummaryEntry(
                user_id=user_id,
                start_date=start_date,
                period_type=target_period_type,
                news_chunking_experiment=news_chunking_experiment,
                news_preference_application_experiment=news_preference_experiment,
                category=summary.category,
                title=summary.title,
                content=summary.content,
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
    return []

__web_search_prompt = """
        Search the news content on the web based on given title {title} and summarize it.
    """


async def __expand_single_news_summary(
    news_summary: NewsSummaryEntry,
    llm_tracker: LlmTracker,
):
    """
    Expand a single news summary if necessary.
    """
    if news_summary.reference_urls:
        try:
            # summarize the content
            summary = await crawl_and_summarize_url(news_summary.reference_urls, llm_tracker)

            if summary:
                # update the content of the news summary
                news_summary.expanded_content = summary
        except Exception as e:
            logger.warning(f"Failed to crawl and summarize {news_summary.reference_urls}: {e}")
    if not news_summary.expanded_content:
        try:
            search_result = (await get_default_client_proxy().generate_content_async(
                    prompt=__web_search_prompt.format_map(
                        {
                            "url": news_summary.reference_urls,
                        }
                    ),
                    tracker=llm_tracker,
                ))[0].text_content
            
            news_summary.expanded_content = search_result
        except Exception as e:
            logger.warning(f"Failed to search for {news_summary.title}: {e}")

async def expand_news_summary(
    summary_entry: NewsSummaryEntry
):
    """
    Expand the news summary if necessary.
    """
    if exceed_llm_token_limit(summary_entry.user_id):
        raise ApiException(
            user_error_code=UserErrorCode.TOKEN_LIMIT_EXCEEDED,
            type=ApiErrorType.CLIENT_ERROR,
        )
    
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
