import enum

# Experiment on how news entries are chunked before being summarized by LLM
# The rationale is that daily news text token count is too large for LLMs to handle
# and we need to chunk them into smaller pieces
class NewsChunkingExperiment(enum.Enum):
    # Summarize news every day and then summarize the daily summaries every week
    AGGREGATE_DAILY = "AGGREGATE_DAILY"
    # Cluster news entries based on their embeddings and summarize each cluster
    EMBEDDING_CLUSTERING = "EMBEDDING_CLUSTERING"

# Experiment on how user preferences are applied to the news summary in the LLM
class NewsPreferenceApplicationExperiment(enum.Enum):
    # Apply user preference 
    APPLY_PREFERENCE = "APPLY_PREFERENCE"
    # Not apply preference at all
    NO_PREFERENCE = "NO_PREFERENCE"
