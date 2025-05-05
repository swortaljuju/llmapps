from dotenv import load_dotenv, find_dotenv

# Load environment variables from .env
load_dotenv(
    find_dotenv(filename=".env.local")
)  # Load local environment variables if available

from concurrent.futures import ThreadPoolExecutor
from db.db import get_sql_db
from db.models import User, RssFeed, NewsEntry
from summarize_news import summarize_news
from datetime import datetime
import os
import requests
from sqlalchemy import func
import random
from utils.logger import logger
import xml.etree.ElementTree as ET
from sqlalchemy.dialects.postgresql import insert

UNLIMITED_USER_EMAILS = os.getenv("UNLIMITED_USER_EMAILS", "").split(",")
SQL_BATCH_SIZE = 1000
LIMITED_USER_SIZE = 20
MAX_CRAWL_FEED_NUM = 2000

def crawl_rss_feed(rss_feed: RssFeed):
    response = requests.get(rss_feed.feed_url)
    if response.status >= 400:
        logger.error(f"Error: Fail to fetch rss {rss_feed.feed_url}")
        return
    if response.content_type != "text/xml":
        logger.error(
            f"Error: Bad rss type for rss {rss_feed.feed_url}. Actual content type {response.content_type}"
        )
        return

    rss_doc = ET.fromstring(response)
    if rss_doc.tag == "rss":
        rss_root = rss_doc
    else:
        rss_root = rss_doc.find(".//rss")

    if rss_root.get("version") != "2.0":
        logger.error(
            f"Error: rss with invalid version. {rss_feed.feed_url}; version = {rss_root.attrib.get('version')}"
        )
        return
    rss_items = rss_root.findall(".//item")

    news_entries = []
    for rss_item in rss_items:
        news_entry = NewsEntry(rss_feed_id=rss_feed.id, crawl_time=datetime.now())
        title = rss_item.find("title")
        if title is None:
            logger.warning("Error: rss item with no title")
            continue
        news_entry.title = title.text
        link = rss_item.find("link")
        if link is None:
            logger.warning("Error: rss item with no link")
            continue
        news_entry.entry_url = link.text
        description = rss_item.find("description")
        if description is not None:
            news_entry.description = description.text
        guid = rss_item.find("guid")
        if guid is not None:
            news_entry.entry_rss_guid = guid.text
        news_entries.append(news_entry)
    sql_session = get_sql_db()
    stmt = (
        insert(NewsEntry)
        .values([news_entries.__dict__ for news_entries in news_entries])
        .on_conflict_do_nothing(index_elements=["entry_rss_guid"])
    )
    sql_session.execute(stmt)
    sql_session.commit()


def get_subscribed_feed_ids():
    sql_session = get_sql_db()
    unlimited_user_subscribed_feed_ids = (
        sql_session.query(User.subscribed_rss_feeds_id)
        .filter(User.email.in_(UNLIMITED_USER_EMAILS))
        .all()
    )
    subscribed_feed_ids = set(
        feed_id for sublist in unlimited_user_subscribed_feed_ids for feed_id in sublist
    )

    limited_user_subscribed_feed_ids = (
        sql_session.query(User.subscribed_rss_feeds_id)
        .filter(User.email.not_in(UNLIMITED_USER_EMAILS))
        .order_by(func.random())
        .limit(LIMITED_USER_SIZE)
        .all()
    )
    # Flatten the list and shuffle the feed IDs
    limited_user_subscribed_feed_ids = [
        feed_id for sublist in limited_user_subscribed_feed_ids for feed_id in sublist
    ]
    random.shuffle(limited_user_subscribed_feed_ids)
    for sublist in limited_user_subscribed_feed_ids:
        for feed_id in sublist:
            if feed_id not in subscribed_feed_ids:
                subscribed_feed_ids.add(feed_id)
                if len(subscribed_feed_ids) >= MAX_CRAWL_FEED_NUM:
                    return list(subscribed_feed_ids)
    return list(subscribed_feed_ids)


def crawl_news():
    script_start_time = datetime.now()
    subscribed_feed_ids = get_subscribed_feed_ids()
    sql_session = get_sql_db()
    rss_feeds = (
        sql_session.query(RssFeed)
        .filter(
            RssFeed.id.in_(subscribed_feed_ids),
            RssFeed.last_crawl_time < script_start_time,
        )
        .yield_per(SQL_BATCH_SIZE)
    )
    with ThreadPoolExecutor(max_workers=10) as executor:
        # Use a thread pool to crawl multiple RSS feeds concurrently
        futures = {
            executor.submit(crawl_rss_feed, rss_feed): rss_feed
            for rss_feed in rss_feeds
        }

        # Wait for all futures to complete
        for future in futures:
            try:
                future.result()  # This will raise an exception if the thread failed
            except Exception as e:
                print(f"Error crawling feed {futures[future].feed_url}: {e}")


# Defining main function
def main():
    crawl_news()
    # Summarize news every Saturday
    if datetime.now().weekday() == 5:  # 0 is Monday, 6 is Sunday
        summarize_news()


if __name__ == "__main__":
    main()
