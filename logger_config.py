"""Logging configuration for the web scraper."""

import logging
import sys
from typing import Optional
from logging.handlers import RotatingFileHandler


def setup_logger(name: str, level: str = "INFO", 
                format_string: Optional[str] = None) -> logging.Logger:
    """Configure minimal logger with file and console output."""
    
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level))
    logger.handlers = []
    
    # Console handler - minimal format
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(console_handler)
    
    # File handler
    file_handler = RotatingFileHandler(
        'crawler.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    ))
    logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for the given name."""
    return logging.getLogger(name)