from dotenv import load_dotenv, find_dotenv
import sys
import os

# Load environment variables from .env
load_dotenv(
    find_dotenv(filename=".env.local"), override=True
)  # Load local environment variables if available


# Add the parent directory to sys.path so that we can import modules correctly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.db import get_sql_db
from db.models import User, NewsChunkingExperiment, NewsPreferenceApplicationExperiment, NewsSummaryPeriod, UserTier
from datetime import timedelta, date
from loguru import logger
from llm.news_summary_agent import summarize_news 
from constants import SQL_BATCH_SIZE
from datetime import datetime

def summarize_news_for_all_users():
    sql_session = get_sql_db()
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    user_data = sql_session.query(
        User.id, User.preferred_news_chunking_experiment, User.preferred_news_preference_application_experiment
    ).filter(User.user_tier == UserTier.UNLIMITED).yield_per(SQL_BATCH_SIZE)

    for id, news_chunking_experiment, news_preference_application_experiment in user_data:
        summarize_news(
            news_preference_application_experiment=news_preference_application_experiment,
            news_chunking_experiment=news_chunking_experiment,
            user_id=id,
            start_date=start_of_week,  # Start from the beginning of the current week
            period=NewsSummaryPeriod.weekly
        )

    user_data = sql_session.query(
        User.id, User.preferred_news_chunking_experiment, User.preferred_news_preference_application_experiment
    ).filter(User.user_tier != UserTier.UNLIMITED).yield_per(SQL_BATCH_SIZE)

    for id, news_chunking_experiment, news_preference_application_experiment in user_data:
        try:
            summarize_news(
                news_preference_application_experiment=news_preference_application_experiment,
                news_chunking_experiment=news_chunking_experiment,
                user_id=id,
                start_date=start_of_week,  # Start from the beginning of the current week
                period=NewsSummaryPeriod.weekly
            )
        except Exception as e:
            logger.error(f"Error summarizing news for user {id}: {e}")
            continue

def __test():
    """
    Test function to summarize news for all users.
    This is a placeholder for actual test cases.
    """
    start_time = datetime.now()
    summaries = summarize_news(
        news_preference_application_experiment=NewsPreferenceApplicationExperiment.APPLY_PREFERENCE,
        news_chunking_experiment=NewsChunkingExperiment.EMBEDDING_CLUSTERING,
        user_id=6,
        start_date=date(2025, 5, 19),  # Start from the beginning of the current week
        period=NewsSummaryPeriod.weekly
    )
    logger.info(f"Summarization took {datetime.now() - start_time} seconds")
    logger.info(f"Summaries: {summaries}")

if __name__ == "__main__":
    print("testing...")
    __test()
