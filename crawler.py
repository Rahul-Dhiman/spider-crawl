"""Web crawler implementation with login support and pagination handling."""

import asyncio
import json
import logging
import os
import tempfile
import time
from typing import List, Dict, Set

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from playwright.async_api import async_playwright, Browser, Page

from config import ScraperConfig
from utils import same_domain_and_path, extract_article_text, find_next_page_url, clean_text

logger = logging.getLogger(__name__)


class WebCrawler:
    """Handles web crawling with login and pagination support."""
    
    def __init__(self, config: ScraperConfig):
        self.config = config
        self.results: List[Dict[str, str]] = []
        self.login_completed = False
        self.browser = None
        self.context = None
    
    async def __aenter__(self):
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=True)
        self.context = await self.browser.new_context()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
    
    async def login_hook(self, page, context, **kwargs):
        """Login hook that runs only once globally."""
        if not self.config.use_login or self.login_completed:
            return page
        
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
            self.login_completed = True
        
        except Exception as e:
            logger.warning("Login flow failed: %s", e)
        
        return page
    
    async def crawl_single_url(self, crawler: AsyncWebCrawler, url: str, 
                              semaphore: asyncio.Semaphore) -> None:
        """Crawl a single URL with pagination support."""
        async with semaphore:
            start_time = time.time()
            if self.results and len(self.results) % 10 == 0:
                self.results.append({"url": url, "Body text content": body_text})
                await self._save_incremental_results()
            
            if len(self.results) >= 1735:
                continue

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
                    same_domain_and_path(next_url, self.config.domain_allow, 
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
    
    async def _crawl_single_url_with_semaphore(self, url: str, semaphore: asyncio.Semaphore):
        """Crawl a single URL with semaphore control."""
        async with semaphore:
            try:
                page = await self.context.new_page()
                try:
                    result = await self._process_page(page, url)
                    return result
                except Exception as e:
                    logger.error(f"Failed to crawl URL {url}: {str(e)}")
                    return None
                finally:
                    await page.close()
            except Exception as e:
                logger.error(f"Failed to create page for URL {url}: {str(e)}")
                return None
    
    async def _process_page(self, page: Page, url: str) -> Dict[str, str]:
        """Process a single page and extract data."""
        try:
            logger.debug(f"Starting to process URL: {url}")
            
            logger.debug(f"Navigating to {url}")
            response = await page.goto(url, wait_until="networkidle")
            
            # Log response status
            status = response.status if response else 'unknown'
            logger.debug(f"Page load status for {url}: {status}")

            # Log page title
            title = await page.title()
            logger.debug(f"Page title: {title}")

            # Log memory usage of the page
            try:
                metrics = await page.evaluate("() => performance.memory")
                logger.debug(f"Page memory usage: {metrics.get('usedJSHeapSize', 'N/A')} bytes")
            except Exception:
                logger.debug("Memory metrics not available")

            # Add your page processing logic here
            # ...

            result = {"url": url, "status": "success", "title": title}
            logger.debug(f"Successfully processed {url}")
            return result

        except Exception as e:
            logger.error(f"Error processing {url}: {str(e)}", exc_info=True)
            # Log additional context about the failure
            try:
                current_url = page.url
                if current_url != url:
                    logger.debug(f"Failed URL redirected to: {current_url}")
            except Exception:
                pass
            return None
        finally:
            logger.debug(f"Finished processing URL: {url}")