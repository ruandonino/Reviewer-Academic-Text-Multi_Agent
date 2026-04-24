import sys
from loguru import logger

# Remove default handler
logger.remove()

# Add console handler
logger.add(sys.stdout, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")

# Add file handler for persistent logs (Traceability - RNF05)
logger.add("logs/system.log", rotation="10 MB", retention="10 days", level="INFO")

def get_logger():
    return logger
