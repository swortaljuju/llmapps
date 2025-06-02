import redis.asyncio as redis
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Annotated
from fastapi import Depends
from contextvars import ContextVar


# Get Redis config from environment variables
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

redis_client = None

# Redis client setup
def get_redis() -> redis.Redis:
    global redis_client
    if redis_client is None:
        redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
    return redis_client

RedisClient = Annotated[redis.Redis, Depends(get_redis)]

SQLALCHEMY_DATABASE_URL = os.getenv("SQLALCHEMY_DATABASE_URL", "")

sql_engine = create_engine(SQLALCHEMY_DATABASE_URL)
SqlSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sql_engine)

db_session_context: ContextVar[Session] = ContextVar("db_session", default=None)

def get_sql_db() -> Session:
    db = db_session_context.get()
    if db is None:
        db = SqlSessionLocal()
        db_session_context.set(db)
    return db

SqlClient = Annotated[Session, Depends(get_sql_db)]
