"""
Logging configuration for Upload Service
"""

import logging
import logging.handlers
from config import Config

def setup_logger(name, log_level=None):
    """
    Setup logger with file and console handlers
    
    Args:
        name: Logger name
        log_level: Logging level (default from config)
        
    Returns:
        Configured logger instance
    """
    
    log_level = log_level or Config.LOG_LEVEL
    
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level))
    
    # Ensure folder exists
    import os
    os.makedirs(os.path.dirname(Config.LOG_FILE) or '.', exist_ok=True)
    
    # File handler
    file_handler = logging.handlers.RotatingFileHandler(
        Config.LOG_FILE,
        maxBytes=10485760,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(getattr(logging, log_level))
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level))
    
    # Formatter
    formatter = logging.Formatter(
        '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger
