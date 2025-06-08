from dotenv import load_dotenv, find_dotenv
import sys
import os

# Load environment variables from .env
load_dotenv(
    find_dotenv(filename=".env.local"), override=True
)  # Load local environment variables if available


# Add the parent directory to sys.path so that we can import modules correctly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from concurrent.futures import ThreadPoolExecutor, as_completed
from db.db import get_sql_db
from db.models import User, UserStatus
import traceback
from loguru import logger
from llm.news_preference_agent import update_preference_based_on_clicked_news

logger.remove()
LOG_DIR = os.getenv("LOG_DIR", "/tmp/logs")
os.makedirs(LOG_DIR, exist_ok=True)
logger.add(
    f"{LOG_DIR}/update_preference.log",
    rotation="1 day",
    retention="30 days",
    level=os.getenv("LOG_LEVEL", "INFO"),
    compression="zip",
    encoding="utf-8",
)


def main():
    sql_client = get_sql_db()
    user_ids = (
        sql_client.query(User.id).filter(User.status.in_([UserStatus.active])).all()
    )
    with ThreadPoolExecutor(max_workers=5) as executor:
        # Use a thread pool to crawl multiple RSS feeds concurrently
        futures = [
            executor.submit(update_preference_based_on_clicked_news, user_id[0])
            for user_id in user_ids
        ]
        finished_count = 0
        success_count = 0
        error_count = 0
        # Wait for all futures to complete
        for future in as_completed(futures):
            try:
                future.result()  # This will raise an exception if the thread failed
                success_count += 1
            except Exception as e:
                logger.error(f"Error updating preference: {e}")
                error_count += 1
                logger.error(f"Stack trace: {traceback.format_exc()}")
            finished_count += 1
        logger.info(
            f"update preference success count {success_count} error count {error_count}."
        )


if __name__ == "__main__":
    main()
