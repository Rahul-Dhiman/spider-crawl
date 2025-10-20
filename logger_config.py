"""Logging configuration for the web scraper."""

import logging
import sys
from typing import Optional


def setup_logger(name: str, level: str = "INFO", 
                format_string: Optional[str] = None) -> logging.Logger:
    """Set up and configure logger with appropriate handlers and formatting."""
    
    if format_string is None:
        format_string = "[%(levelname)s] %(asctime)s - %(name)s - %(message)s"
    
    logger = logging.getLogger(name)
    
    # Avoid adding multiple handlers if logger already configured
    if logger.handlers:
        return logger
    
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(format_string, datefmt="%H:%M:%S")
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper()))

    # Ensure module-level loggers also emit at the same level so their INFO logs are visible
    # This helps surface messages from e.g. sitemap expansion steps
    for module_name in ("sitemap_parser", "crawler", "utils", "frontier"):
        module_logger = logging.getLogger(module_name)
        if not module_logger.handlers:
            module_logger.addHandler(handler)
        module_logger.setLevel(getattr(logging, level.upper()))
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for the given name."""
    return logging.getLogger(name)