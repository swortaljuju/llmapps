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
from db.db import get_sql_db, SqlSessionLocal
from db.models import User, NewsEntry
from datetime import datetime, timedelta
from loguru import logger

UNLIMITED_USER_EMAILS = os.getenv("UNLIMITED_USER_EMAILS", "").split(",")


def _summarize_news_per_user(user_id: int, feed_ids: list[int]):
    """
    Summarize news for a specific user and their subscribed feeds.
    """
    with SqlSessionLocal() as sql_session:
        # Fetch the latest news entries for the user
        news_entries = (
            sql_session.query(NewsEntry)
            .filter(
                NewsEntry.rss_feed_id.in_(feed_ids),
                NewsEntry.pub_time >= datetime.now() - timedelta(days=1),
            )
            .all()
        )
        print("news_entries: ", len(news_entries))
        # Create a map where key is rss_feed_id and value is a list of news entries
        feed_to_entries = {}
        for entry in news_entries:
            if entry.rss_feed_id not in feed_to_entries:
                feed_to_entries[entry.rss_feed_id] = []
            feed_to_entries[entry.rss_feed_id].append(entry)
        # Process the news entries and summarize them
        # summaries = []
        # for entry in news_entries:
        #     summary = {
        #         "title": entry.title,
        #         "description": entry.description,
        #         "content": entry.content,
        #         "url": entry.entry_url,
        #     }
        #     summaries.append(summary)

        from google import genai

        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))
        for feed_id, entries in feed_to_entries.items():
            prompt = "\n".join(
                [
                    f"title: {entry.title}; description: {entry.description}; content:{entry.content}; url:{entry.entry_url}"
                    for entry in entries
                ]
            )
            total_tokens = client.models.count_tokens(
                model="gemini-2.0-flash", contents=prompt
            )
            print("feed id", feed_id, " total_tokens with title, description, content: ", total_tokens)
        # prompt = "\n".join(
        #     [
        #         f"title: {entry.title}; description: {entry.description}; content:{entry.content}; url:{entry.entry_url}"
        #         for entry in news_entries
        #     ]
        # )
        # Count tokens using the new client method.
        # total_tokens = client.models.count_tokens(
        #     model="gemini-2.0-flash", contents=prompt
        # )
        # print("total_tokens with title, description, content: ", total_tokens)
        
        
        # prompt = "\n".join(
        #     [
        #         f"title: {entry.title}; description: {entry.description};  reference link:{entry.entry_url}"
        #         for entry in news_entries
        #     ]
        # )

        # # Count tokens using the new client method.
        # total_tokens = client.models.count_tokens(
        #     model="gemini-2.0-flash", contents=prompt
        # )
        # print("total_tokens with title, description: ", total_tokens)
        
        # prompt = "\n".join(
        #     [
        #         f"title: {entry.title}; url:{entry.entry_url}"
        #         for entry in news_entries
        #     ]
        # )
        # # Count tokens using the new client method.
        # total_tokens = client.models.count_tokens(
        #     model="gemini-2.0-flash", contents=prompt
        # )
        # print("total_tokens with title: ", total_tokens)
        
        # response = client.models.generate_content(
        #     model="gemini-2.0-flash", contents='''Summarize the following news.
        #         Put reference link under the item of which is summarized from.\n''' +prompt
        # )

        # # The usage_metadata provides detailed token counts.
        # print(response.usage_metadata)
        # print("output: ", response.text)

        # Save the summaries to the database
        return summaries


def summarize_news():
    sql_session = get_sql_db()
    user_and_subscribed_feed_ids = (
        sql_session.query(User.id, User.subscribed_rss_feeds_id)
        .filter(User.email.in_(UNLIMITED_USER_EMAILS))
        .all()
    )
    with ThreadPoolExecutor(max_workers=10) as executor:
        # Use a thread pool to crawl multiple RSS feeds concurrently
        futures = [
            executor.submit(_summarize_news_per_user, entry[0], entry[1])
            for entry in user_and_subscribed_feed_ids
        ]
        print("futures: ", len(futures))
        print("UNLIMITED_USER_EMAILS: ", UNLIMITED_USER_EMAILS)
        # Wait for all futures to complete
        for future in as_completed(futures):
            try:
                future.result()  # This will raise an exception if the thread failed
            except Exception as e:
                logger.error(f"fail to summarize for user: {e}")


if __name__ == "__main__":
    print("Summarizing news...")
    summarize_news()
