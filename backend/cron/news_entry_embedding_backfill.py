from dotenv import load_dotenv, find_dotenv
import sys
import os

# Load environment variables from .env
load_dotenv(
    find_dotenv(filename=".env.local"), override=True
)  # Load local environment variables if available


# Add the parent directory to sys.path so that we can import modules correctly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cron.common import generate_embedding
from db.db import get_sql_db
from db.models import  NewsEntry
from cron.common import generate_embedding
import time

BATCH_SIZE = 1000
MINI_BATCH_SIZE = 100
    
# Defining main function
def backfill_embedding():
    sql_client = get_sql_db()
    news_entries_to_backfill = sql_client.query(NewsEntry).filter(
        NewsEntry.summary_embedding.is_(None)).limit(BATCH_SIZE).all()
    while len(news_entries_to_backfill) > 0:
        print(f"Backfilling {len(news_entries_to_backfill)} news entries")
        generate_embedding(news_entries_to_backfill)
        sql_client.commit()
        # avoid exceeding gemini rate limit        
        time.sleep(60)
        news_entries_to_backfill = sql_client.query(NewsEntry).filter(
            NewsEntry.summary_embedding.is_(None)).limit(BATCH_SIZE).all()
        

if __name__ == "__main__":
    backfill_embedding()
