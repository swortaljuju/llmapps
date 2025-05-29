from db.models import LlmUsageLog, User, UserTier
from sqlalchemy.orm import Session, Query
from sqlalchemy import func
from db.db import get_sql_db, SqlSessionLocal
import os
from datetime import datetime, date
from constants import MAX_INPUT_TOKENS_PER_USER_PER_MONTH, MAX_OUTPUT_TOKENS_PER_USER_PER_MONTH
from langchain.callbacks.base import BaseCallbackHandler

def track_usage(
    user_id: int,
    usage_metadata: dict
) -> None:
    """
    Track the usage of an LLM model by logging the prompt, completion, and total tokens used.
    """
    usage_metadata_per_model = usage_metadata[os.getenv("GEMINI_MODEL", "gemini-2.0-flash")]
    usage_log = LlmUsageLog(
        user_id=user_id,
        llm_input_token_count=usage_metadata_per_model["input_tokens"],
        llm_output_token_count=usage_metadata_per_model["output_tokens"],
    )
    with SqlSessionLocal() as db:
        db.add(usage_log)
        db.commit()

def exceed_llm_token_limit(
    user_id: int
) -> bool:
    """
    Check if the user's LLM token usage exceeds the limit.
    """
    sql_client = get_sql_db()
    user_tier = sql_client.query(
        User.user_tier
    ).filter(User.id == user_id).first()
    if user_tier == UserTier.UNLIMITED:
        return False
    now = datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # Calculate the sum of input and output tokens
    result = sql_client.query(
        func.sum(LlmUsageLog.llm_input_token_count).label("total_input_tokens"),
        func.sum(LlmUsageLog.llm_output_token_count).label("total_output_tokens")
    ).filter(
        LlmUsageLog.user_id == user_id, 
        LlmUsageLog.created_at >= month_start
    ).first()
    
    if result is not None and (
        (result.total_input_tokens and result.total_input_tokens >= MAX_INPUT_TOKENS_PER_USER_PER_MONTH) or 
        (result.total_output_tokens and result.total_output_tokens >= MAX_OUTPUT_TOKENS_PER_USER_PER_MONTH)):
        return True
    return False

class LlmApiTracker(BaseCallbackHandler):
    def on_llm_start(self, serialized, prompts, **kwargs):
        self.kwargs = kwargs

    def on_llm_end(self, response, **kwargs):
        self.response = response
        self.response_kwargs = kwargs
