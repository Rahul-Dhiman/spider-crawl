"""Web crawler implementation with login support and pagination handling."""

import asyncio
import json
import logging
import os
import tempfile
import time
from typing import List, Dict, Set

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

from config import ScraperConfig
from frontier import SQLiteFrontier
from utils import normalize_url, compute_hash
try:
    from utils import same_domain, extract_article_text, find_next_page_url, clean_text
except Exception:
    import re
    from urllib.parse import urlparse, urljoin
    
    def same_domain(url: str, allow: str, allow_subdomains: bool) -> bool:
        netloc = urlparse(url).netloc.lower()
        allow_l = allow.lower()
        if allow_subdomains:
            return netloc == allow_l or netloc.endswith(f".{allow_l}")
        return netloc == allow_l
    
    def extract_article_text(html: str):
        matches = re.findall(r'(?is)<article\\b[^>]*>(.*?)</article>', html)
        collected = []
        for inner in matches:
            text = re.sub(r'(?s)<[^>]+>', '', inner)
            text = text.replace('\n', ' ').replace('\t', ' ')
            text = re.sub(r' {3,}', '  ', text).strip()
            if text:
                collected.append(text)
        return collected
    
    def find_next_page_url(html: str, current_url: str) -> str:
        patterns = [
            r'(?is)<a[^>]+class=["\'[^"\']*pageNav-jump--next[^"\']*["\'][^>]*href=["\']([^"\']+)["\']',
            r'(?is)<a[^>]*href=["\']([^"\']+)["\'][^>]*>\s*<[^>]*pageNav-jump--next'
        ]
        for pattern in patterns:
            m = re.search(pattern, html)
            if m:
                return urljoin(current_url, m.group(1))
        return ""
    
    def clean_text(text: str) -> str:
        text = text.replace('\n', ' ').replace('\t', ' ')
        return re.sub(r' {3,}', '  ', text).strip()

logger = logging.getLogger(__name__)


class WebCrawler:
    """Handles web crawling with login and pagination support."""
    
    def __init__(self, config: ScraperConfig):
        self.config = config
        self.results: List[Dict[str, str]] = []
        self.pages_processed: int = 0
    
    async def login_hook(self, page, context, **kwargs):
        """Login hook that runs once per browser context."""
        if not self.config.use_login:
            return page
        
        # Avoid re-running login on the same browser context
        try:
            if getattr(context, "_login_done", False):
                return page
        except Exception:
            pass
        
        logger.info("Starting login flow...")
        
        try:
            await page.goto(self.config.login_url, 
                          wait_until="domcontentloaded", 
                          timeout=self.config.request_timeout_ms)
            
            await page.wait_for_selector(self.config.username_selector, 
                                       timeout=self.config.request_timeout_ms)
            
            await page.fill(self.config.username_selector, self.config.username, 
                          timeout=self.config.request_timeout_ms)
            await page.fill(self.config.password_selector, self.config.password, 
                          timeout=self.config.request_timeout_ms)
            await page.click(self.config.submit_selector)
            
            await page.wait_for_selector(self.config.post_login_ready_selector, 
                                       timeout=self.config.request_timeout_ms)
            
            cookies = await context.cookies()
            logger.info("Login successful; cookies=%d", len(cookies))
            
            try:
                setattr(context, "_login_done", True)
            except Exception:
                pass
        
        except Exception as e:
            logger.warning("Login flow failed for this context: %s", e)
        
        return page
    
    async def crawl_single_url(self, crawler: AsyncWebCrawler, url: str) -> None:
        """Crawl a single URL with pagination support."""
        start_time = time.time()
        
        try:
            run_config = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS if self.config.bypass_cache else CacheMode.DEFAULT,
                js_code="try{window.scrollTo(0, document.body.scrollHeight);}catch(e){}"
            )
            
            result = await crawler.arun(url, config=run_config)
            
            if not result or not result.success:
                logger.warning("FAILED: %s", url)
                return
            
            body_text = await self._process_pagination(crawler, url, result, run_config)
            
            elapsed_time = time.time() - start_time
            logger.info("OK: %s | body_len=%d | %.2fs", 
                       url, len(body_text), elapsed_time)
            
            # Dedup by content hash (lightweight)
            content_hash = compute_hash(body_text) if body_text else ""
            self.results.append({"url": url, "Body text content": body_text, "hash": content_hash})
            await self._save_incremental_results()
            
            if self.config.delay_between_pages_sec > 0:
                # politeness with jitter
                import random
                jitter = random.randint(0, max(0, self.config.politeness_jitter_ms)) / 1000.0
                await asyncio.sleep(self.config.delay_between_pages_sec + jitter)
        
        except Exception as e:
            logger.warning("ERROR %s: %s", url, e)
    
    async def _process_pagination(self, crawler: AsyncWebCrawler, initial_url: str, 
                                 initial_result, run_config) -> str:
        """Process pagination and collect content from all pages."""
        collected_text: List[str] = []
        seen_pages: Set[str] = set()
        current_url = initial_url
        pages_followed = 0
        first_markdown = ""
        
        while current_url and pages_followed < self.config.pagination_limit:
            if current_url in seen_pages:
                break
            
            seen_pages.add(current_url)
            pages_followed += 1
            
            if pages_followed == 1:
                page_result = initial_result
            else:
                page_result = await crawler.arun(current_url, config=run_config)
            
            if not page_result or not page_result.success:
                logger.warning("FAILED page: %s", current_url)
                break
            
            page_html = page_result.html or ""
            
            if pages_followed == 1:
                first_markdown = (page_result.markdown.raw_markdown 
                                if page_result.markdown else "") or ""
            
            if page_html:
                article_texts = extract_article_text(page_html)
                collected_text.extend(article_texts)
                
                next_url = find_next_page_url(page_html, current_url)
                if (next_url and 
                    same_domain(next_url, self.config.domain_allow, 
                               self.config.allow_subdomains)):
                    current_url = next_url
                    if self.config.delay_between_pages_sec > 0:
                        await asyncio.sleep(self.config.delay_between_pages_sec)
                    continue
            
            break
        
        if collected_text:
            return "  ".join(collected_text).strip()
        else:
            return clean_text(first_markdown)
    
    async def _save_incremental_results(self) -> None:
        """Save results incrementally to avoid data loss."""
        try:
            fd, tmp_path = tempfile.mkstemp(prefix="crawl_", suffix=".json")
            with os.fdopen(fd, "w", encoding="utf-8") as temp_file:
                json.dump(self.results, temp_file, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.config.output_file)
            logger.info("Saved %d items", len(self.results))
        except Exception as e:
            logger.warning("Failed to persist results: %s", e)
    
    async def crawl_urls(self, urls: List[str]) -> List[Dict[str, str]]:
        """Crawl multiple URLs with a bounded worker pool.
        
        Usare una coda con N worker limita davvero il numero di task vivi
        e riduce la pressione di memoria e il numero di processi Chrome.
        """
        browser_config = BrowserConfig(headless=self.config.headless)
        # Persistent frontier with normalization and depth
        frontier = SQLiteFrontier(self.config.frontier_db_path)
        for u in urls:
            nu = normalize_url(u)
            frontier.put(nu, depth=0)
        
        async with AsyncWebCrawler(config=browser_config) as crawler:
            crawler.crawler_strategy.set_hook("on_page_context_created", self.login_hook)
            await crawler.start()
            
            logger.info("Begin crawl (frontier size=%d, concurrency=%d)", 
                       frontier.size(), self.config.concurrency)
            
            async def worker(worker_id: int) -> None:
                import asyncio as _asyncio
                while True:
                    item = frontier.get()
                    if not item:
                        return
                    url, depth = item
                    try:
                        await self.crawl_single_url(crawler, url)
                        self.pages_processed += 1
                        # Recycle browser periodically to avoid leaks
                        if self.pages_processed % max(1, self.config.recycle_every_n_pages) == 0:
                            logger.info("Recycling browser after %d pages", self.pages_processed)
                            await crawler.close()
                            await _asyncio.sleep(0.2)
                            await crawler.start()
                    finally:
                        await _asyncio.sleep(0)  # yield
            
            workers = [asyncio.create_task(worker(i)) for i in range(max(1, self.config.concurrency))]
            for w in workers:
                w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            await crawler.close()
        
        logger.info("Crawl finished; collected %d pages", len(self.results))
        return self.results
