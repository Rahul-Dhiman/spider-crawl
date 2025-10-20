"""Configuration settings for the web scraper."""

import os
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class ScraperConfig:
    """Configuration class for the web scraper."""
    
    # Sitemap settings
    sitemap_seeds: List[str]
    domain_allow: str
    allow_subdomains: bool = True
    max_path_depth: Optional[int] = None
    
    # Crawl behavior
    concurrency: int = 20
    headless: bool = True
    bypass_cache: bool = True
    request_timeout_ms: int = 30000
    max_pages: int = 100000
    pagination_limit: int = 300
    output_file: str = "crawl_output.json"
    user_agent: str = "SpiderCrawl/1.0 (+https://example.com/bot)"
    politeness_jitter_ms: int = 150
    recycle_every_n_pages: int = 200
    
    # Login settings
    use_login: bool = False
    login_url: str = ""
    username: str = ""
    password: str = ""
    username_selector: str = 'input[name="login"]'
    password_selector: str = 'input[name="password"]'
    submit_selector: str = '.button--icon--login'
    post_login_ready_selector: str = ".p-navgroup-link--user"
    
    # Politeness
    delay_between_pages_sec: float = 0.3
    max_depth: int = 3
    frontier_db_path: str = "frontier.db"
    enable_metrics: bool = True


def load_config() -> ScraperConfig:
    """Load configuration from environment variables or defaults."""
    return ScraperConfig(
        sitemap_seeds=[
            os.getenv("SITEMAP_SEED", "https://carders.biz/sitemap.xml")
        ],
        domain_allow=os.getenv("DOMAIN_ALLOW", "carders.biz"),
        allow_subdomains=os.getenv("ALLOW_SUBDOMAINS", "true").lower() == "true",
        max_path_depth=int(os.getenv("MAX_PATH_DEPTH")) if os.getenv("MAX_PATH_DEPTH") else None,
        concurrency=int(os.getenv("CONCURRENCY", "20")),
        headless=os.getenv("HEADLESS", "true").lower() == "true",
        bypass_cache=os.getenv("BYPASS_CACHE", "true").lower() == "true",
        request_timeout_ms=int(os.getenv("REQUEST_TIMEOUT_MS", "30000")),
        max_pages=int(os.getenv("MAX_PAGES", "100000000")),
        pagination_limit=int(os.getenv("PAGINATION_LIMIT", "1000")),
        output_file=os.getenv("OUTPUT_FILE", "crawl_output.json"),
        user_agent=os.getenv("USER_AGENT", "SpiderCrawl/1.0 (+https://example.com/bot)"),
        politeness_jitter_ms=int(os.getenv("POLITENESS_JITTER_MS", "150")),
        recycle_every_n_pages=int(os.getenv("RECYCLE_EVERY_N_PAGES", "200")),
        use_login=os.getenv("USE_LOGIN", "false").lower() == "true",
        login_url=os.getenv("LOGIN_URL", ""),
        username=os.getenv("USERNAME", ""),
        password=os.getenv("PASSWORD", ""),
        username_selector=os.getenv("USERNAME_SELECTOR", 'input[name="login"]'),
        password_selector=os.getenv("PASSWORD_SELECTOR", 'input[name="password"]'),
        submit_selector=os.getenv("SUBMIT_SELECTOR", '.button--icon--login'),
        post_login_ready_selector=os.getenv("POST_LOGIN_READY_SELECTOR", ".p-navgroup-link--user"),
        delay_between_pages_sec=float(os.getenv("DELAY_BETWEEN_PAGES_SEC", "0.3")),
        max_depth=int(os.getenv("MAX_DEPTH", "3")),
        frontier_db_path=os.getenv("FRONTIER_DB_PATH", "frontier.db"),
        enable_metrics=os.getenv("ENABLE_METRICS", "true").lower() == "true"
    )