from .clients import langchain_gemini_client
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from sqlalchemy.orm import Session
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from db.models import NewsEntry, NewsPreferenceApplicationExperiment, NewsChunkingExperiment, NewsSummaryPeriod, NewsSummaryEntry
from datetime import datetime

SUMMARY_PROMPT = """
    {user_preferences}
    Merge and summarize the following news entries. If some news entries are similar, summarize and merge them into one while keeping their reference urls
    For example, if the following two news entries are similar:
    {title: "Title 1", url: "https://example.com/1"}
    {title: "Title 2", url: "https://example.com/2"}
    then the output should be:
    {title: "title summary", url: ["https://example.com/1", "https://example.com/2"]}
"""

SUMMARY_PER_GROUP_PROMPT = """
    Summarize and merge the following news entries per group.
    [
        # group 1
        [news_entry_1, news_entry_2, ...],
        # group 2
        [news_entry_3, news_entry_4, ...],
        ...
    }]
        

    """
class NewsSummaryOutput(BaseModel):
    title : str | None = Field(
        default=None,
        description="""The title of the news summary. """)
    content: str | None = Field(
        default=None,
        description="""The summary of the news entries. """)
    reference_urls: list[str] | None = Field(
        default=None,
        description="""The list of urls referenced in the summary. """)
    should_expand: bool = Field(
        default=False,
        description="""True if the summary should be expanded based on user preference. """)
    failed_to_expand: bool = Field(
        default=False,
        description="""True if it fails to crawl and summarize the content in the reference urls. """)    

def summarize_news(news_preference_application_experiment: NewsPreferenceApplicationExperiment, news_chunking_experiment: NewsChunkingExperiment, user_id: int, start_time: datetime, period: NewsSummaryPeriod):
    # if in the middle of a period, we will just summarize the news entries from the start of the period to the current time
    pass

# NewsChunkingExperiment.AGGREGATE_DAILY
def __chunk_and_summarize_news(news_entry_list: list[NewsEntry], chunking_period_type: NewsSummaryPeriod) -> list[NewsSummaryOutput]:
    # based on news entry token count, chunk them per smaller period, summarize them per chunk and then merge the summaries
    # into one summary. Currently, we only support daily chunking
    pass

# NewsChunkingExperiment.EMBEDDING_CLUSTERING
def __cluster_and_summarize_news(news_entry_list: list[NewsEntry]) -> list[NewsSummaryOutput]:
    # based on news entry embedding, cluster them and summarize each cluster
    pass

# For NewsPreferenceApplicationExperiment.WITH_SUMMARIZATION_PROMPT experiment   
def __summarize_rank_expand_news(news_entry_list: list[NewsEntry])-> list[NewsSummaryOutput]:
    pass

# For NewsPreferenceApplicationExperiment.AFTER_NEW_SUMMARIZATION experiment
def __summarize_news(news_entry_list: list[NewsEntry]) -> list[NewsSummaryOutput]:
    pass

def __rank_expand_news(news_entry_list: list[NewsEntry])-> list[NewsSummaryOutput]:
    pass

def _expand_news(news_summary_list:  list[NewsSummaryOutput]):
    # If llm decide to expand the summary but fail to crawl it, we will crawl the reference urls and ask llm to summarize them
    # If we also fail to crawl the reference urls, we will just ask llm to search the title on the web and summarize the content
    pass
