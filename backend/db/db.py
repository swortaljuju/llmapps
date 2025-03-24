import redis.asyncio as redis
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from typing import Annotated
from fastapi import Depends
from sqlalchemy.orm import Session



# Get Redis config from environment variables
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

redis_client = None

# Redis client setup
def get_redis() -> redis.Redis:
    if redis_client is None:
        redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
    return redis_client

RedisClient = Annotated[redis.Redis, Depends(get_redis)]

SQLALCHEMY_DATABASE_URL = os.getenv("SQLALCHEMY_DATABASE_URL", "")

sql_engine = create_engine(SQLALCHEMY_DATABASE_URL)
SqlSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sql_engine)

sql_client = None
def get_sql_db() -> Session:
    if sql_client is None:
        sql_client = SqlSessionLocal()
    return sql_client

SqlClient = Annotated[Session, Depends(get_sql_db)]
