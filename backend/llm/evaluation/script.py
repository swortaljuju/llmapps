from dotenv import load_dotenv, find_dotenv
import sys
import os
# Load environment variables from .env
load_dotenv(
    find_dotenv(filename=".env.local"), override=True
)  # Load local environment variables if available
# Add the parent directory to sys.path so that we can import modules correctly
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from llm.news_summary_agent import summarize_news
from llm.news_research_agent import answer_user_question
from datetime import date, timedelta
import asyncio
from db.db import get_sql_db
from db.models import (
    User,
    NewsChunkingExperiment,
    NewsPreferenceApplicationExperiment,
    NewsSummaryPeriod,
    NewsEntry,
)
from sqlalchemy import or_, and_
from utils.logger import setup_logger

setup_logger("llm_evaluation")


def export_daily_entry():
    # Example of exporting daily news entry
    date_str_list = ["2025-05-15", "2025-05-20", "2025-05-22"]
    sql_client = get_sql_db()
    subscribed_feed_id_list = (
        sql_client.query(User.subscribed_rss_feeds_id)
        .filter(User.id == 6)
        .one_or_none()[0]
    )
    for date_str in date_str_list:
        with open(f"news_entry_{date_str.replace('-', '_')[5:]}.txt", "w") as f:
            start_date = date.fromisoformat(date_str)
            end_date = start_date + timedelta(days=1)
            news_entry_list = (
                sql_client.query(NewsEntry.title, NewsEntry.description)
                .filter(
                    and_(
                        or_(
                            and_(
                                NewsEntry.pub_time >= start_date,
                                NewsEntry.pub_time < end_date,
                            ),
                            and_(
                                NewsEntry.pub_time.is_(None),
                                NewsEntry.crawl_time >= start_date,
                                NewsEntry.crawl_time < end_date,
                            ),
                        ),
                        NewsEntry.rss_feed_id.in_(subscribed_feed_id_list),
                    )
                )
                .all()
            )
            formatted_news_entries = [
                f"Title: {entry[0]}\nDescription: {entry[1]}\n"
                for entry in news_entry_list
            ]
            f.write("\n".join(formatted_news_entries))


async def summarize_news_and_export(
    start_date_list: list[date],
    news_chunking_experiment: NewsChunkingExperiment,
    news_preference_application_experiment: NewsPreferenceApplicationExperiment,
    period: NewsSummaryPeriod,
    export_file_name: str,
):
    summary_entry_list = []
    for start_date in start_date_list:
        current_summary_entry_list =  await summarize_news(
                news_preference_application_experiment=news_preference_application_experiment,
                news_chunking_experiment=news_chunking_experiment,
                user_id=6,
                start_date=start_date,
                period=period,
            )
        if current_summary_entry_list:
            summary_entry_list.extend(current_summary_entry_list)
    with open(f"{export_file_name}.txt", "w") as f:
        formatted_summary_entries = [
            f"Category: {entry.category}; Title: {entry.title}; Content: {entry.content};\n"
            for entry in summary_entry_list
        ]
        f.write("\n".join(formatted_summary_entries))


async def main():
    # export_daily_entry()
    await asyncio.gather(
            summarize_news_and_export(
                start_date_list=[date(2025, 5, 15)],
                news_chunking_experiment=NewsChunkingExperiment.AGGREGATE_DAILY,
                news_preference_application_experiment=NewsPreferenceApplicationExperiment.APPLY_PREFERENCE,
                period=NewsSummaryPeriod.daily,
                export_file_name="news_summary_05_15",
            ),
            summarize_news_and_export(
                start_date_list=[date(2025, 5, 20)],
                news_chunking_experiment=NewsChunkingExperiment.AGGREGATE_DAILY,
                news_preference_application_experiment=NewsPreferenceApplicationExperiment.APPLY_PREFERENCE,
                period=NewsSummaryPeriod.daily,
                export_file_name="news_summary_05_20",
            ),
            summarize_news_and_export(
                start_date_list=[date(2025, 5, 22)],
                news_chunking_experiment=NewsChunkingExperiment.AGGREGATE_DAILY,
                news_preference_application_experiment=NewsPreferenceApplicationExperiment.APPLY_PREFERENCE,
                period=NewsSummaryPeriod.daily,
                export_file_name="news_summary_05_22",
            ),)
    await summarize_news_and_export(
                start_date_list=[
                    date(2025, 5, 19),
                    date(2025, 5, 20),
                    date(2025, 5, 21),
                    date(2025, 5, 22),
                    date(2025, 5, 23),
                    date(2025, 5, 24),
                    date(2025, 5, 25),
                ],
                news_chunking_experiment=NewsChunkingExperiment.AGGREGATE_DAILY,
                news_preference_application_experiment=NewsPreferenceApplicationExperiment.APPLY_PREFERENCE,
                period=NewsSummaryPeriod.daily,
                export_file_name="news_summary_daily_05_19_25",
            )
    await asyncio.gather(
            summarize_news_and_export(
                start_date_list=[date(2025, 5, 19)],
                news_chunking_experiment=NewsChunkingExperiment.AGGREGATE_DAILY,
                news_preference_application_experiment=NewsPreferenceApplicationExperiment.APPLY_PREFERENCE,
                period=NewsSummaryPeriod.weekly,
                export_file_name="news_summary_weekly_05_19_25",
            ),
            summarize_news_and_export(
                start_date_list=[date(2025, 5, 15)],
                news_chunking_experiment=NewsChunkingExperiment.AGGREGATE_DAILY,
                news_preference_application_experiment=NewsPreferenceApplicationExperiment.NO_PREFERENCE,
                period=NewsSummaryPeriod.daily,
                export_file_name="news_summary_no_preference_05_15",
            ),
            summarize_news_and_export(
                start_date_list=[date(2025, 5, 19)],
                news_chunking_experiment=NewsChunkingExperiment.EMBEDDING_CLUSTERING,
                news_preference_application_experiment=NewsPreferenceApplicationExperiment.APPLY_PREFERENCE,
                period=NewsSummaryPeriod.weekly,
                export_file_name="news_summary_weekly_clustering_05_19_25",
            ),
            # answer_user_question(
            #     user_id=6,
            #     user_question="Any new federal legislation passed recently?",
            #     thread_id=None,
            #     parent_message_id=None,
            #     sql_client=get_sql_db()
            # )
        )


if __name__ == "__main__":
    asyncio.run(main())
