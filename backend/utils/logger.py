from loguru import logger
import os

# Clear default handlers
LOG_DIR = os.getenv("LOG_DIR", "/tmp/logs")

def setup_logger(module: str):
    """
    Setup logger for a specific module.
    """
    logger.remove()
    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = f"{LOG_DIR}/{module}.log"
    logger.add(log_file, rotation="1 day", retention="10 days", level=os.getenv("LOG_LEVEL", "INFO"), compression="zip", encoding="utf-8")
