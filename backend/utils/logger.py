from loguru import logger
import os

# Clear default handlers
logger.remove()
LOG_DIR = os.getenv("LOG_DIR", "/tmp/logs")
os.makedirs(LOG_DIR, exist_ok=True)
logger.add(f"{LOG_DIR}/fastapi.log", rotation="1 day", retention="10 days", level=os.getenv("LOG_LEVEL", "INFO"), compression="zip", encoding="utf-8")
