from sqlalchemy import Column, Integer, String, DateTime, Interval
from datetime import datetime
from .base import Base

class ApiLatencyLog(Base):
    __tablename__ = "api_latency_log"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.now())
    api_path = Column(String)
    total_elapsed_time_ms = Column(Integer)
    llm_input_token_count = Column(Integer)
    llm_output_token_count = Column(Integer)
    llm_elapsed_time_ms = Column(Integer)

# One row for each LLM usage
class LlmUsageLog(Base):
    __tablename__ = "llm_usage_log"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.now())
    user_id = Column(Integer)
    llm_input_token_count = Column(Integer)
    llm_output_token_count = Column(Integer)
