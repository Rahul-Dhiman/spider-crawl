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
from utils import same_domain, extract_article_text, find_next_page_url, clean_text

logger = logging.getLogger(__name__)


class WebCrawler:
    """Handles web crawling with login and pagination support."""
    
    def __init__(self, config: ScraperConfig):
        self.config = config
        self.results: List[Dict[str, str]] = []
    
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
    
    async def crawl_single_url(self, crawler: AsyncWebCrawler, url: str, 
                              semaphore: asyncio.Semaphore) -> None:
        """Crawl a single URL with pagination support."""
        async with semaphore:
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
                
                self.results.append({"url": url, "Body text content": body_text})
                await self._save_incremental_results()
                
                if self.config.delay_between_pages_sec > 0:
                    await asyncio.sleep(self.config.delay_between_pages_sec)
            
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
        """Crawl multiple URLs concurrently."""
        browser_config = BrowserConfig(headless=self.config.headless)
        semaphore = asyncio.Semaphore(self.config.concurrency)
        
        async with AsyncWebCrawler(config=browser_config) as crawler:
            crawler.crawler_strategy.set_hook("on_page_context_created", self.login_hook)
            await crawler.start()
            
            logger.info("Begin crawl of %d URLs (concurrency=%d)", 
                       len(urls), self.config.concurrency)
            
            tasks = [
                asyncio.create_task(self.crawl_single_url(crawler, url, semaphore))
                for url in urls
            ]
            
            await asyncio.gather(*tasks, return_exceptions=True)
            await crawler.close()
        
        logger.info("Crawl finished; collected %d pages", len(self.results))
        return self.results