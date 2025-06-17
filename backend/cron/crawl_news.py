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
from db.models import User, RssFeed, NewsEntry
from datetime import datetime, timedelta, timezone
import requests
from sqlalchemy import func
import random
import xml.etree.ElementTree as ET
import traceback
from loguru import logger
from constants import HTTP_HEADER_USER_AGENT, SQL_BATCH_SIZE
from dateutil import parser
from enum import Enum
import time
from cron.news_entry_embedding_backfill import backfill_embedding
from utils.rss import get_atom_tag, is_valid_rss_type


# Clear default handlers
logger.remove()
LOG_DIR = os.getenv("LOG_DIR", "/tmp/logs")
os.makedirs(LOG_DIR, exist_ok=True)
logger.add(
    f"{LOG_DIR}/crawl_news.log",
    rotation="1 day",
    retention="30 days",
    level=os.getenv("LOG_LEVEL", "INFO"),
    compression="zip",
    encoding="utf-8",
)

UNLIMITED_USER_EMAILS = os.getenv("UNLIMITED_USER_EMAILS", "").split(",")
LIMITED_USER_SIZE = 20
MAX_CRAWL_FEED_NUM = 2000


class DocRoot:
    def __init__(
        self,
        rss_root: ET.Element | None = None,
        atom_feed_root: ET.Element | None = None,
    ):
        self.rss_root = rss_root
        self.atom_feed_root = atom_feed_root


def _find_doc_root(doc: ET) -> DocRoot:
    if doc.tag == "rss":
        return DocRoot(rss_root=doc)
    else:
        rss_root = doc.find(".//rss")
        if rss_root is not None:
            return DocRoot(rss_root=rss_root)
    if doc.tag == get_atom_tag("feed"):
        return DocRoot(atom_feed_root=doc)
    raise RuntimeError("Failed to determine doc type")


def _get_rss_tag(tag: str) -> str:
    return tag


def _element_has_text(element: ET.Element) -> bool:
    """
    Check if the element has text content.
    """
    return (
        element is not None and element.text is not None and element.text.strip() != ""
    )


class DocType(Enum):
    """
    Enum for document types supported by the RSS crawler.
    """

    RSS = "rss"
    ATOM = "atom"


def _parse_doc(
    root: ET.Element, rss_feed: RssFeed, doc_type: DocType
) -> (list[NewsEntry], set[str]):
    """
    Parse the RSS document and return a list of NewsEntry objects and a set of GUIDs.
    """

    if doc_type == DocType.RSS and root.get("version") != "2.0":
        raise RuntimeError(
            f"Error: rss with invalid version. {rss_feed.feed_url}; version = {root.attrib.get('version')}"
        )
    tag_modifier = _get_rss_tag if doc_type == DocType.RSS else get_atom_tag
    items = (
        root.findall(f".//{tag_modifier("item")}")
        if doc_type == DocType.RSS
        else root.findall(f".//{tag_modifier('entry')}")
    )
    news_entries = []
    guid_set = set()
    for item in items:
        news_entry = NewsEntry(rss_feed_id=rss_feed.id, crawl_time=datetime.now())
        title = item.find(tag_modifier("title"))
        if _element_has_text(title):
            news_entry.title = title.text
        else:
            logger.warning("Error: rss item with no title")

        link = item.find(tag_modifier("link"))
        if _element_has_text(link):
            news_entry.entry_url = link.text
        description = (
            item.find(tag_modifier("description"))
            if doc_type == DocType.RSS
            else item.find(tag_modifier("summary"))
        )
        if _element_has_text(description):
            news_entry.description = description.text
        if doc_type == DocType.ATOM:
            content = item.find(tag_modifier("content"))
            if (
                content is not None
                and content.text is not None
                and content.text.strip() != ""
            ):
                news_entry.content = content.text
        guid = (
            item.find(tag_modifier("guid"))
            if doc_type == DocType.RSS
            else item.find(tag_modifier("id"))
        )
        if _element_has_text(guid):
            news_entry.entry_rss_guid = guid.text
            guid_set.add(guid.text)
        elif _element_has_text(title):
            news_entry.entry_rss_guid = news_entry.title
            guid_set.add(news_entry.title)
        elif _element_has_text(link):
            news_entry.entry_rss_guid = link.text
            guid_set.add(link.text)
        pub_date = item.find(tag_modifier("pubDate"))
        published = item.find(tag_modifier("published"))
        if _element_has_text(pub_date):
            pub_date_text = pub_date.text
        elif _element_has_text(published):
            pub_date_text = published.text
        else:
            pub_date_text = None
        if pub_date_text is not None:
            try:
                news_entry.pub_time = parser.parse(pub_date_text)
            except Exception as e:
                logger.warning(f"Error parsing pubDate: {e}")
                news_entry.pub_time = datetime.now()
        else:
            news_entry.pub_time = datetime.now()
        news_entries.append(news_entry)
    return news_entries, guid_set


def _fetch_feed_content(rss_feed: RssFeed) -> str:
    """
    Fetch the content of the RSS feed.
    """
    with SqlSessionLocal() as sql_client:
        rss_feed = sql_client.query(RssFeed).filter(RssFeed.id == rss_feed.id).first()
        headers = {"User-Agent": HTTP_HEADER_USER_AGENT}
        response = requests.get(rss_feed.feed_url, timeout=120, headers=headers)
        if response.status_code >= 400 and response.reason == "Not Found":
            response = requests.get(rss_feed.html_url, timeout=120)
            rss_feed.feed_url = rss_feed.html_url
        response.raise_for_status()  # Raise an error for bad responses
        content_type = response.headers.get("Content-Type", "")
        if not is_valid_rss_type(content_type):
            raise RuntimeError(
                f"Error: Bad rss type for rss {rss_feed.feed_url}. Actual content type {response.headers.get('Content-Type')}"
            )
        if sql_client.is_modified(rss_feed):
            sql_client.commit()

    return response.text


def crawl_rss_feed(rss_feed: RssFeed):
    response_text = _fetch_feed_content(rss_feed)
    doc_root = _find_doc_root(ET.fromstring(response_text))

    if doc_root.rss_root is not None:
        doc_type = DocType.RSS
        doc_root_obj = doc_root.rss_root
    elif doc_root.atom_feed_root is not None:
        doc_type = DocType.ATOM
        doc_root_obj = doc_root.atom_feed_root

    news_entries, guid_set = _parse_doc(doc_root_obj, rss_feed, doc_type)
    # always create a new session for parallel execution
    sql_session = SqlSessionLocal()
    existing_guids = (
        sql_session.query(NewsEntry.entry_rss_guid)
        .filter(NewsEntry.entry_rss_guid.in_(guid_set))
        .all()
    )
    existing_guids = set(guid[0] for guid in existing_guids)
    news_entries = [
        entry
        for entry in news_entries
        if entry.entry_rss_guid not in existing_guids
        and (
            entry.pub_time is None
            or entry.pub_time.date() >= (datetime.now(timezone.utc) - timedelta(days=7)).date()
        )
    ]
    sql_session.add_all(news_entries)
    sql_session.commit()


def get_subscribed_feed_ids():
    sql_session = get_sql_db()
    unlimited_user_subscribed_feed_ids = (
        sql_session.query(User.subscribed_rss_feeds_id)
        .filter(
            User.email.in_(UNLIMITED_USER_EMAILS),
            User.subscribed_rss_feeds_id.is_not(None),
            )
        .all()
    )
    subscribed_feed_ids = set(
        feed_id
        for sublist in unlimited_user_subscribed_feed_ids
        for feed_id in sublist[0]
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
        feed_id
        for sublist in limited_user_subscribed_feed_ids
        for feed_id in sublist[0]
    ]
    random.shuffle(limited_user_subscribed_feed_ids)
    for feed_id in limited_user_subscribed_feed_ids:
        if feed_id not in subscribed_feed_ids:
            subscribed_feed_ids.add(feed_id)
            if len(subscribed_feed_ids) >= MAX_CRAWL_FEED_NUM:
                return list(subscribed_feed_ids)
    return list(subscribed_feed_ids)


def crawl_news() -> int:
    subscribed_feed_ids = get_subscribed_feed_ids()
    sql_session = get_sql_db()
    # Get today's date at midnight (beginning of the day)
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    rss_feeds = (
        sql_session.query(RssFeed)
        .filter(
            RssFeed.id.in_(subscribed_feed_ids),
            (RssFeed.last_crawl_time == None) | (RssFeed.last_crawl_time < today),
        )
        .yield_per(SQL_BATCH_SIZE)
    )
    with ThreadPoolExecutor(max_workers=10) as executor:
        # Use a thread pool to crawl multiple RSS feeds concurrently
        future_to_feed = {
            executor.submit(crawl_rss_feed, rss_feed): rss_feed
            for rss_feed in rss_feeds
        }
        logger.info(f"Total feeds to crawl: {len(future_to_feed)}")
        finished_count = 0
        success_count = 0
        error_count = 0
        # Wait for all futures to complete
        for future in as_completed(future_to_feed.keys()):
            rss_feed = future_to_feed[future]
            try:
                future.result()  # This will raise an exception if the thread failed
                success_count += 1
                # Update last_crawl_time in a separate session
                update_session = SqlSessionLocal()
                try:
                    feed_obj = (
                        update_session.query(RssFeed)
                        .filter(RssFeed.id == rss_feed.id)
                        .first()
                    )
                    if feed_obj:
                        feed_obj.last_crawl_time = datetime.now()
                        update_session.commit()
                except Exception as e:
                    update_session.rollback()
                    logger.error(
                        f"Error updating feed timestamp {rss_feed.feed_url}: {e}"
                    )
                finally:
                    update_session.close()
            except Exception as e:
                logger.error(f"Error crawling feed {rss_feed.feed_url}: {e}")
                error_count += 1
                logger.error(f"Stack trace: {traceback.format_exc()}")
            finished_count += 1
        logger.info(f"success count {success_count} error count {error_count}.")
        return error_count


# Defining main function
def main():
    unfinished_count = 1
    retry_count = 0
    while unfinished_count > 0 and retry_count < 3:
        unfinished_count = crawl_news()
        retry_count += 1
        if unfinished_count > 0:
            logger.info("Sleeping for 1 minutes before retrying...")
            time.sleep(60)  # Sleep for 10 minutes
    # populate the embedding separately so that the quota won't block the crawling
    backfill_embedding()

if __name__ == "__main__":
    main()
