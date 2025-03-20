import redis.asyncio as redis
from dotenv import load_dotenv
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


# Load environment variables from .env
load_dotenv()

# Get Redis config from environment variables
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))



# Redis client setup
async def get_redis():
    client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
    try:
        yield client
    finally:
        await client.close()

SQLALCHEMY_DATABASE_URL = os.getenv("SQLALCHEMY_DATABASE_URL", "")

sql_engine = create_engine(SQLALCHEMY_DATABASE_URL)
SqlSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sql_engine)

def get_sql_db():
    db = SqlSessionLocal()
    try:
        yield db
    finally:
        db.close()