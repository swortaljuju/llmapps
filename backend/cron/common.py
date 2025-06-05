import sys
import os


# Add the parent directory to sys.path so that we can import modules correctly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.models import NewsEntry
from llm.client_proxy_factory import get_default_client_proxy
from llm.client_proxy import EmbeddingTaskType

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
        clustering_embedding = get_default_client_proxy().embed_content(
            embedding_input_list, task_type=EmbeddingTaskType.CLUSTERING
        )
        document_retrieval_embedding = get_default_client_proxy().embed_content(
            embedding_input_list, task_type=EmbeddingTaskType.RETRIEVAL_DOCUMENT
        )
        for j, news_entry in enumerate(news_entry_list_chunk):
            news_entry.summary_clustering_embedding = clustering_embedding[j]
            news_entry.summary_document_retrieval_embedding = document_retrieval_embedding[j]
