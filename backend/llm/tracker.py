from db.models import LlmUsageLog, User, UserTier
from sqlalchemy import func
from db.db import SqlSessionLocal, get_sql_db
from datetime import datetime
from constants import MAX_INPUT_TOKENS_PER_USER_PER_MONTH, MAX_OUTPUT_TOKENS_PER_USER_PER_MONTH
from utils.logger import logger
class LlmTracker:
    """
    A class to track LLM usage and other logs.
    """
    def __init__(self, user_id: int):
        self.__user_id = user_id
    
    def start(self) -> None:
        self.__usage_log = LlmUsageLog(
            user_id=self.__user_id)
        
    def log_usage(self, input_token_count: int | None, output_token_count: int | None) -> None:
        if not self.__usage_log.llm_input_token_count:
            self.__usage_log.llm_input_token_count = 0
        if not self.__usage_log.llm_output_token_count:
            self.__usage_log.llm_output_token_count = 0
        logger.info(f"Logging LLM usage for user {self.__user_id}: input tokens: {input_token_count}, output tokens: {output_token_count}")
        if input_token_count is not None:
            self.__usage_log.llm_input_token_count += input_token_count
        if output_token_count is not None:    
            self.__usage_log.llm_output_token_count += output_token_count

    def end(self) -> bool:
        with SqlSessionLocal() as db:
            db.add(self.__usage_log)
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
    ).filter(User.id == user_id).first()[0]
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

