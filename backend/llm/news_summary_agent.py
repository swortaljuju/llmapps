from .clients import langchain_gemini_client
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from sqlalchemy.orm import Session
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from db.models import NewsEntry, NewsPreferenceApplicationExperiment, NewsChunkingExperiment, NewsSummaryPeriod, NewsSummaryEntry
from datetime import datetime

### Prompt templates for summarizing news entries
SUMMARY_WITH_USER_PREFERENCE_AND_CHUNKED_DATA_PROMPT = """
    {user_preferences}
    Merge and summarize the following news entries. If some news entries are similar, summarize and merge them into one while keeping their reference urls
    For example, if the following two news entries are similar:
    {title: "Title 1", url: "https://example.com/1"}
    {title: "Title 2", url: "https://example.com/2"}
    then the output should be:
    {title: "title summary", url: ["https://example.com/1", "https://example.com/2"]}
"""

# Summary without user preference prompt
SUMMARY_WITH_CHUNKED_DATA_PROMPT = """
"""

RANK_AND_EXPAND_CHUNKED_DATA_PROMPT = """
    {user_preferences}
"""

SUMMARY_WITH_USER_PREFERENCE_PER_CLUSTERING_GROUP_PROMPT = """
    Summarize and merge the following news entries per group.
    [
        # group 1
        [news_entry_1, news_entry_2, ...],
        # group 2
        [news_entry_3, news_entry_4, ...],
        ...
    }]
    """

# Summary without user preference prompt
SUMMARY_PER_CLUSTERING_GROUP_PROMPT = """
"""

RANK_AND_EXPAND_PER_CLUSTERING_GROUP_PROMPT = """
    {user_preferences}
"""

# News summary without user preference output    
class NewsSummaryOutput(BaseModel):
    summary : str | None = Field(
        default=None,
        description="""The title of the news summary. """)
    reference_urls: list[str] | None = Field(
        default=None,
        description="""The list of urls referenced in the summary. """)


class NewsSummaryWithPreferenceAppliedOutput(BaseModel):
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
def __chunk_and_summarize_news(news_entry_list: list[NewsEntry], chunking_period_type: NewsSummaryPeriod) -> list[NewsSummaryWithPreferenceAppliedOutput]:
    # based on news entry token count, chunk them per smaller period, summarize them per chunk and then merge the summaries
    # into one summary. Currently, we only support daily chunking
    pass

# NewsChunkingExperiment.EMBEDDING_CLUSTERING
def __cluster_and_summarize_news(news_entry_list: list[NewsEntry]) -> list[NewsSummaryWithPreferenceAppliedOutput]:
    # based on news entry embedding, cluster them and summarize each cluster
    pass

# For NewsPreferenceApplicationExperiment.WITH_SUMMARIZATION_PROMPT experiment   
def __summarize_rank_expand_news(news_entry_list: list[NewsEntry])-> list[NewsSummaryWithPreferenceAppliedOutput]:
    pass

# For NewsPreferenceApplicationExperiment.AFTER_NEW_SUMMARIZATION experiment and NewsPreferenceApplicationExperiment.NO_PREFERENCE experiment
def __summarize_news(news_entry_list: list[NewsEntry]) -> list[NewsSummaryOutput]:
    # summarize the news entries without user preference. Save a copy of this output to db under NO_PREFERENCE experiment
    pass

def __rank_expand_news(news_entry_list: list[NewsEntry])-> list[NewsSummaryWithPreferenceAppliedOutput]:
    pass

def _expand_news(news_summary_list:  list[NewsSummaryWithPreferenceAppliedOutput]):
    # If llm decide to expand the summary but fail to crawl it, we will crawl the reference urls and ask llm to summarize them
    # If we also fail to crawl the reference urls, we will just ask llm to search the title on the web and summarize the content
    pass
