import enum

# Experiment on how news entries are chunked before being summarized by LLM
# The rationale is that daily news text token count is too large for LLMs to handle
# and we need to chunk them into smaller pieces
class NewsChunkingExperiment(enum.Enum):
    # Summarize news every day and then summarize the daily summaries every week
    AGGREGATE_DAILY = "aggregate_daily"
    # Cluster news entries based on their embeddings and summarize each cluster
    EMBEDDING_CLUSTERING = "embedding_clustering"

# Experiment on how user preferences are applied to the news summary in the LLM
class NewsPreferenceApplicationExperiment(enum.Enum):
    # Apply user preference together with the news summarization prompt in one step
    WITH_SUMMARIZATION_PROMPT = "with_summarization_prompt"
    # Apply user preference after the news summarization is done
    AFTER_NEW_SUMMARIZATION = "after_new_summarization"
    # Not apply preference at all
    NO_PREFERENCE = "no_preference"
