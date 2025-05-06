from dotenv import load_dotenv, find_dotenv
import sys
import os

# Load environment variables from .env
load_dotenv(
    find_dotenv(filename=".env.local")
)  # Load local environment variables if available


# Add the parent directory to sys.path so that we can import modules correctly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from concurrent.futures import ThreadPoolExecutor, as_completed
from db.db import get_sql_db, SqlSessionLocal
from db.models import User, RssFeed, NewsEntry
from cron.summarize_news import summarize_news
from datetime import datetime
import requests
from sqlalchemy import func
import random
import xml.etree.ElementTree as ET
from sqlalchemy.dialects.postgresql import insert
import traceback
from loguru import logger
from constants import ( HTTP_HEADER_USER_AGENT)

# Clear default handlers
logger.remove()
LOG_DIR = os.getenv("LOG_DIR", "/tmp/logs")
os.makedirs(LOG_DIR, exist_ok=True)
logger.add(f"{LOG_DIR}/crawl_news.log", rotation="1 day", retention="30 days", level=os.getenv("LOG_LEVEL", "INFO"), compression="zip", encoding="utf-8")

UNLIMITED_USER_EMAILS = os.getenv("UNLIMITED_USER_EMAILS", "").split(",")
SQL_BATCH_SIZE = 1000
LIMITED_USER_SIZE = 20
MAX_CRAWL_FEED_NUM = 2000
ATOM_TAG_PREFIX = "{http://www.w3.org/2005/Atom}"

class DocRoot():
    def __init__(self, rss_root: ET.Element | None = None, atom_feed_root: ET.Element | None = None):
        self.rss_root = rss_root
        self.atom_feed_root = atom_feed_root

def _is_valid_rss_type(content_type: str) -> bool:
    """
    Check if the content type is a valid RSS type.
    """
    valid_rss_types = [
        "application/rss+xml",
        "text/xml",
        "application/atom+xml",
        "application/xml",
        "text/html",
    ]
    for valid_type in valid_rss_types:
        if valid_type in content_type:
            return True
    return False

def _find_doc_root(doc: ET) -> DocRoot:
    if doc.tag == "rss":
        return DocRoot(rss_root=doc)
    else:
        rss_root = doc.find(".//rss")
        if rss_root is not None:
            return DocRoot(rss_root=rss_root)
    if doc.tag == _get_atom_tag("feed"):
        return DocRoot(atom_feed_root=doc)
    raise RuntimeError("Failed to determine doc type")

def _get_atom_tag(tag: str) -> str:
    """
    Get the full Atom tag name with namespace.
    """
    if tag.startswith(ATOM_TAG_PREFIX):
        return tag
    return f"{ATOM_TAG_PREFIX}{tag}"
def _parse_rss_doc(rss_root: ET.Element, rss_feed: RssFeed) -> (list[NewsEntry], set[str]):
    """
    Parse the RSS document and return a list of NewsEntry objects and a set of GUIDs.
    """
    if rss_root.get("version") != "2.0":
        raise RuntimeError(
        f"Error: rss with invalid version. {rss_feed.feed_url}; version = {rss_root.attrib.get('version')}"
    )
    rss_items = rss_root.findall(".//item")
    news_entries = []
    guid_set = set()
    for rss_item in rss_items:
        news_entry = NewsEntry(rss_feed_id=rss_feed.id, crawl_time=datetime.now())
        title = rss_item.find("title")
        if title is None:
            logger.warning("Error: rss item with no title")
        else:
            news_entry.title = title.text
        link = rss_item.find("link")
        if link is not None:
            news_entry.entry_url = link.text
        description = rss_item.find("description")
        if description is not None:
            news_entry.description = description.text
        guid = rss_item.find("guid")
        if guid is not None and guid.text is not None and guid.text.strip() != "":
            news_entry.entry_rss_guid = guid.text
            guid_set.add(guid.text)
        elif title is not None and title.text is not None and title.text.strip() != "":
            news_entry.entry_rss_guid = news_entry.title
            guid_set.add(news_entry.title)    
        elif link is not None and link.text is not None and link.text.strip() != "":
            news_entry.entry_rss_guid = link.text
            guid_set.add(link.text)    
        news_entries.append(news_entry)
    return news_entries, guid_set

def _parse_atom_feed_doc(root: ET.Element, rss_feed: RssFeed) -> (list[NewsEntry], set[str]):
    """
    Parse the RSS document and return a list of NewsEntry objects and a set of GUIDs.
    """
    
    atom_feed_entries = root.findall(f".//{_get_atom_tag("entry")}")
    news_entries = []
    guid_set = set()
    for atom_feed_entry in atom_feed_entries:
        news_entry = NewsEntry(rss_feed_id=rss_feed.id, crawl_time=datetime.now())
        title = atom_feed_entry.find(_get_atom_tag("title"))
        if title is None:
            logger.warning("Error: rss item with no title")
            continue
        news_entry.title = title.text
        link = atom_feed_entry.find(_get_atom_tag("link"))
        if link is not None:
            news_entry.entry_url = link.text
        summary = atom_feed_entry.find(_get_atom_tag("summary"))
        if summary is not None:
            news_entry.description = summary.text
        content = atom_feed_entry.find(_get_atom_tag("content"))
        if content is not None:
            news_entry.content = content.text    
        id = atom_feed_entry.find(_get_atom_tag("id"))
        if id is not None and id.text is not None and id.text.strip() != "":
            news_entry.entry_rss_guid = id.text
            guid_set.add(id.text)
        elif title is not None and title.text is not None and title.text.strip() != "":
            news_entry.entry_rss_guid = news_entry.title
            guid_set.add(news_entry.title)    
        elif link is not None and link.text is not None and link.text.strip() != "":
            news_entry.entry_rss_guid = link.text
            guid_set.add(link.text)     
        news_entries.append(news_entry)
    return news_entries, guid_set

def _fetch_feed_content(rss_feed: RssFeed) -> str:
    """
    Fetch the content of the RSS feed.
    """
    with SqlSessionLocal() as sql_client:
        rss_feed = sql_client.query(RssFeed).filter(RssFeed.id == rss_feed.id).first()
        headers = {
            'User-Agent': HTTP_HEADER_USER_AGENT
        }
        response = requests.get(rss_feed.feed_url, timeout=120, headers=headers)
        if response.status_code >= 400 and response.reason == "Not Found":
            response = requests.get(rss_feed.html_url, timeout=120)
            rss_feed.feed_url = rss_feed.html_url
        response.raise_for_status()  # Raise an error for bad responses
        content_type = response.headers.get('Content-Type', '')
        if not _is_valid_rss_type(content_type):
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
        news_entries, guid_set = _parse_rss_doc(doc_root.rss_root, rss_feed)
    elif doc_root.atom_feed_root is not None:
        news_entries, guid_set = _parse_atom_feed_doc(doc_root.atom_feed_root, rss_feed)
    # always create a new session for parallel execution
    sql_session = SqlSessionLocal()
    existing_guids = sql_session.query(NewsEntry.entry_rss_guid).filter(
        NewsEntry.entry_rss_guid.in_(guid_set)
    ).all()
    existing_guids = set(guid[0] for guid in existing_guids)
    news_entries = [
        entry for entry in news_entries if entry.entry_rss_guid not in existing_guids
    ]
    sql_session.add_all(news_entries)
    sql_session.commit()


def get_subscribed_feed_ids():
    sql_session = get_sql_db()
    unlimited_user_subscribed_feed_ids = (
        sql_session.query(User.subscribed_rss_feeds_id)
        .filter(User.email.in_(UNLIMITED_USER_EMAILS))
        .all()
    )
    subscribed_feed_ids = set(
        feed_id for sublist in unlimited_user_subscribed_feed_ids for feed_id in sublist[0]
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
    subscribed_feed_ids = get_subscribed_feed_ids()
    sql_session = get_sql_db()
    # Get today's date at midnight (beginning of the day)
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    rss_feeds = (
        sql_session.query(RssFeed)
        .filter(
            RssFeed.id.in_(subscribed_feed_ids),
            RssFeed.last_crawl_time < today,
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
                    feed_obj = update_session.query(RssFeed).filter(RssFeed.id == rss_feed.id).first()
                    if feed_obj:
                        feed_obj.last_crawl_time = datetime.now()
                        update_session.commit()
                except Exception as e:
                    update_session.rollback()
                    logger.error(f"Error updating feed timestamp {rss_feed.feed_url}: {e}")
                finally:
                    update_session.close()
            except Exception as e:
                logger.error(f"Error crawling feed {rss_feed.feed_url}: {e}")
                error_count += 1
                logger.error(f"Stack trace: {traceback.format_exc()}")
            finished_count += 1
        logger.info(f"success count {success_count} error count {error_count}.")


# Defining main function
def main():
    crawl_news()
    # Summarize news every Saturday
    if datetime.now().weekday() == 5:  # 0 is Monday, 6 is Sunday
        summarize_news()


if __name__ == "__main__":
    main()
