"""Web crawler implementation with login support and pagination handling."""

import asyncio
import logging
import gc
import tempfile
import os
from typing import List, Dict, Set

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from playwright.async_api import async_playwright, Browser, Page

from config import ScraperConfig
from utils import same_domain_and_path, extract_article_text, find_next_page_url, clean_text
from system_monitor import get_system_health
from resource_manager import ResourceManager

logger = logging.getLogger(__name__)


class WebCrawler:
    """Handles web crawling with login and pagination support."""
    
    def __init__(self, config: ScraperConfig):
        self.config = config
        self.results: List[Dict[str, str]] = []
        self.login_completed = False
        self.browser = None
        self.context = None
        self.urls_processed = 0
        self.resource_manager = ResourceManager(initial_concurrency=config.concurrency)
        
        # Log configuration details
        logger.info("Initializing WebCrawler with configuration:")
        logger.info("Domain: %s (allow_subdomains=%s)", 
                    config.domain_allow, config.allow_subdomains)
        logger.info("Concurrency: %d, Max Pages: %d", 
                    config.concurrency, config.max_pages)
        logger.info("Headless Mode: %s, Bypass Cache: %s", 
                    config.headless, config.bypass_cache)
        logger.info("Login Enabled: %s", config.use_login)
        logger.info("Pagination Limit: %d, Delay Between Pages: %.2f sec", 
                    config.pagination_limit, config.delay_between_pages_sec)
        logger.info("Output File: %s", config.output_file)
        logger.info("Request Timeout: %d ms", config.request_timeout_ms)
        
        if config.max_path_depth:
            logger.info("Max Path Depth: %d", config.max_path_depth)
    
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
    
    def _is_valid_url(self, url: str) -> bool:
        """Validate URL against domain and path requirements"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            
            # Check domain
            if not parsed.netloc.endswith(self.config.domain_allow.split('/')[0]):
                return False
                
            # Check if path contains /threads
            if '/threads' not in parsed.path:
                return False
                
            return True
        except Exception as e:
            logger.error(f"URL validation error for {url}: {e}")
            return False
    
    async def crawl_single_url(self, crawler: AsyncWebCrawler, url: str, 
                              semaphore: asyncio.Semaphore) -> None:
        """Crawl a single URL with pagination support."""
        if not self._is_valid_url(url):
            return
            
        async with semaphore:
            try:
                self.urls_processed += 1
                
                # Check system health and cleanup every 100 URLs
                if self.urls_processed % 100 == 0:
                    stats = get_system_health()
                    logger.info(f"=== Progress: {self.urls_processed} URLs processed ===")
                    logger.info(f"CPU Usage: {stats['cpu_percent']}%")
                    logger.info(f"Memory Usage: {stats['memory_percent']}%")
                    logger.info(f"Chrome Instances: {stats['chrome_processes']}")
                    logger.info(f"Chrome Memory: {stats['chrome_memory_mb']:.0f}MB")
                    
                    # Aggressive cleanup if memory usage is high
                    if stats['memory_percent'] > 70:
                        logger.warning("High memory usage - forcing cleanup")
                        gc.collect()
                        await crawler.cleanup()  # Add this method to AsyncWebCrawler
                        await asyncio.sleep(5)  # Cool-down period
                
                    # Save incremental results
                    await self._save_incremental_results()

                run_config = CrawlerRunConfig(
                    cache_mode=CacheMode.BYPASS if self.config.bypass_cache else CacheMode.DEFAULT,
                    js_code="try{window.scrollTo(0, document.body.scrollHeight);}catch(e){}"
                )
                
                result = await crawler.arun(url, config=run_config)
                
                if not result or not result.success:
                    return
                
                body_text = await self._process_pagination(crawler, url, result, run_config)
                self.results.append({"url": url, "Body text content": body_text})
                
                if self.config.delay_between_pages_sec > 0:
                    await asyncio.sleep(self.config.delay_between_pages_sec)
    
            except Exception as e:
                logger.error(f"Error processing {url}: {str(e)}")
    
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
        """Save results incrementally with proper temp file handling."""
        try:
            with tempfile.NamedTemporaryFile(mode='w', 
                                           delete=False, 
                                           suffix='.json',
                                           encoding='utf-8') as tf:
                json.dump(self.results, tf, ensure_ascii=False, indent=2)
                temp_name = tf.name

            # Atomic replace
            os.replace(temp_name, self.config.output_file)
            logger.info(f"Saved {len(self.results)} items")
        except Exception as e:
            logger.warning(f"Failed to persist results: {e}")
            if 'temp_name' in locals():
                try:
                    os.unlink(temp_name)
                except:
                    pass

    async def crawl_urls(self, urls: List[str]) -> List[Dict[str, str]]:
        """Crawl multiple URLs concurrently."""
        browser_config = BrowserConfig(headless=self.config.headless)
        semaphore = asyncio.Semaphore(self.config.concurrency)
        
        async with AsyncWebCrawler(config=browser_config) as crawler:
            crawler.crawler_strategy.set_hook("on_page_context_created", self.login_hook)
            await crawler.start()
            
            logger.info("Begin crawl of %d URLs (concurrency=%d)", 
                       len(urls), self.config.concurrency)
            
            try:
                tasks = [
                    asyncio.create_task(self.crawl_single_url(crawler, url, semaphore))
                    for url in urls
                ]
                
                await asyncio.gather(*tasks, return_exceptions=True)
            finally:
                # Cleanup
                await crawler.close()
                gc.collect()
                
                # Optional: Suggest system cleanup
                if psutil.virtual_memory().percent > 90:
                    logger.warning("System needs cleanup - consider running: sync; echo 3 > /proc/sys/vm/drop_caches")
    
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
        """Process a single page with proper cleanup."""
        try:
            result = await page.goto(url, wait_until="networkidle")
            if not result:
                return None

            # Extract needed data
            content = await page.content()
            title = await page.title()

            # Important: Clear browser cache and memory
            await page.context.clear_cookies()
            await page.close()
            
            return {
                "url": url,
                "title": title,
                "content": content
            }
        except Exception as e:
            logger.error(f"Error processing {url}: {str(e)}")
            return None
        finally:
            try:
                await page.close()
            except:
                pass
            gc.collect()