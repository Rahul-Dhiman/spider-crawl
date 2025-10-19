"""Main entry point for the web scraper application."""

import asyncio
import json
import sys
from typing import List, Dict

from config import load_config
from crawler import WebCrawler
from logger_config import setup_logger
from sitemap_parser import SitemapParser


async def main() -> None:
    """Main application entry point."""
    # Setup logging
    logger = setup_logger("web-scraper", level="DEBUG")
    setup_logger("sitemap_parser", level="DEBUG")
    setup_logger("crawler", level="DEBUG")
    
    try:
        # Load configuration
        config = load_config()
        logger.info("Configuration loaded successfully")
        
        # Initialize sitemap parser
        sitemap_parser = SitemapParser(
            domain=config.domain_allow,
            allow_subdomains=config.allow_subdomains,
            max_path_depth=config.max_path_depth
        )
        
        # Expand sitemaps to get URLs
        logger.info("Starting sitemap expansion...")
        urls = sitemap_parser.expand_sitemaps(
            seed_urls=config.sitemap_seeds,
            max_urls=config.max_pages
        )
        
        logger.info("Sitemap expansion produced %d candidate URLs", len(urls))
        
        if not urls:
            logger.error("No URLs to crawl — check domain and depth filters.")
            return
        
        # Initialize and run crawler
        crawler = WebCrawler(config)
        data = await crawler.crawl_urls(urls)
        
        # Save final results
        await save_final_results(data, config.output_file, logger)
        
        # Output to stdout as requested
        print(json.dumps(data, ensure_ascii=False))
        
    except KeyboardInterrupt:
        logger.warning("Interrupted by user.")
    except Exception as e:
        logger.exception("Fatal error: %s", e)
        sys.exit(1)


async def save_final_results(data: List[Dict[str, str]], output_file: str, 
                           logger) -> None:
    """Save final crawl results to file."""
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("Wrote JSON output to %s (items=%d)", output_file, len(data))
    except Exception as e:
        logger.error("Failed to save final results: %s", e)
        raise


if __name__ == "__main__":
    asyncio.run(main())