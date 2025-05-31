import sys
import os


# Add the parent directory to sys.path so that we can import modules correctly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.models import NewsEntry
from llm.client_proxy_factory import get_default_client_proxy

EMBEDDING_RATE_LIMIT = 100

def _empty_for_none(value):
    if value is None:
        return ""
    return value

def generate_embedding(news_entry_list: list[NewsEntry]):

    chunked_news_entry_list = [
        news_entry_list[i : i + EMBEDDING_RATE_LIMIT]
        for i in range(0, len(news_entry_list), EMBEDDING_RATE_LIMIT)
    ]
        
    for news_entry_list_chunk in chunked_news_entry_list:
        embedding_input_list = [
            f"{_empty_for_none(news_entry.title)} {_empty_for_none(news_entry.description)} {_empty_for_none(news_entry.content)}"
            for news_entry in news_entry_list_chunk
        ]
        embedding = get_default_client_proxy().embed_documents(
            embedding_input_list
        )
        for j, embedding_vector in enumerate(embedding):
            news_entry = news_entry_list_chunk[j]
            news_entry.summary_embedding = embedding_vector
