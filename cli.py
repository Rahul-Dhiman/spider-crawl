"""Command-line interface for the web scraper."""

import argparse
import asyncio
import sys
from pathlib import Path

from config import ScraperConfig
from crawler import WebCrawler
from logger_config import setup_logger
from sitemap_parser import SitemapParser


def create_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser."""
    parser = argparse.ArgumentParser(
        description="Web scraper that extracts content from websites using sitemaps",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "sitemap_url",
        help="URL of the sitemap to crawl"
    )
    
    parser.add_argument(
        "--domain",
        required=True,
        help="Domain to restrict crawling to"
    )
    
    parser.add_argument(
        "--output", "-o",
        default="crawl_output.json",
        help="Output JSON file path (default: crawl_output.json)"
    )
    
    parser.add_argument(
        "--concurrency", "-c",
        type=int,
        default=20,
        help="Number of concurrent requests (default: 20)"
    )
    
    parser.add_argument(
        "--max-pages",
        type=int,
        default=1000000,
        help="Maximum number of pages to crawl (default: 1000000)"
    )
    
    parser.add_argument(
        "--delay",
        type=float,
        default=0.3,
        help="Delay between requests in seconds (default: 0.3)"
    )
    
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Run browser in headless mode (default: True)"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    return parser


async def run_scraper(args: argparse.Namespace) -> None:
    """Run the scraper with CLI arguments."""
    # Setup logging
    log_level = "DEBUG" if args.verbose else "INFO"
    logger = setup_logger("web-scraper-cli", level=log_level)
    
    # Create configuration from CLI args
    config = ScraperConfig(
        sitemap_seeds=[args.sitemap_url],
        domain_allow=args.domain,
        output_file=args.output,
        concurrency=args.concurrency,
        max_pages=args.max_pages,
        delay_between_pages_sec=args.delay,
        headless=args.headless
    )
    
    logger.info("Starting scraper with sitemap: %s", args.sitemap_url)
    
    # Initialize sitemap parser
    sitemap_parser = SitemapParser(
        domain=config.domain_allow,
        allow_subdomains=config.allow_subdomains,
        max_path_depth=config.max_path_depth
    )
    
    # Get URLs from sitemap
    urls = sitemap_parser.expand_sitemaps(
        seed_urls=config.sitemap_seeds,
        max_urls=config.max_pages
    )
    
    if not urls:
        logger.error("No URLs found in sitemap")
        sys.exit(1)
    
    logger.info("Found %d URLs to crawl", len(urls))
    
    # Run crawler
    crawler = WebCrawler(config)
    results = await crawler.crawl_urls(urls)
    
    logger.info("Scraping completed. Results saved to %s", args.output)
    print(f"Successfully scraped {len(results)} pages")


def main() -> None:
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    try:
        asyncio.run(run_scraper(args))
    except KeyboardInterrupt:
        print("\nScraping interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()