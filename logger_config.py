"""Logging configuration for the web scraper."""

import logging
import sys
from typing import Optional
from logging.handlers import RotatingFileHandler


def setup_logger(name: str, level: str = "INFO", 
                format_string: Optional[str] = None) -> logging.Logger:
    """Set up and configure logger with appropriate handlers and formatting."""
    
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level))
    
    # Clear any existing handlers
    logger.handlers = []
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    logger.addHandler(console_handler)
    
    # File handler for crawler.log
    file_handler = RotatingFileHandler(
        'crawler.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    logger.addHandler(file_handler)
    
    # Special handler for failed URLs
    if name == "crawler":
        failed_handler = logging.FileHandler('failed.log')
        failed_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(message)s'
        ))
        failed_handler.setLevel(logging.ERROR)
        logger.addHandler(failed_handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for the given name."""
    return logging.getLogger(name)