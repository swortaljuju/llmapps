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
