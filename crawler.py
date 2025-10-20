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
                js_code="try{window.scrollTo(0, document.body.scrollHeight);}catch(e){}",
                page_timeout=self.config.request_timeout_ms,
                wait_for_images=False,
                exclude_all_images=True,
                only_text=True
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
            item = {"url": url, "Body text content": body_text, "hash": content_hash}
            await self._emit_result(item)
            
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
    
    async def _emit_result(self, item: Dict[str, str]) -> None:
        """Stream results to NDJSON to limit in-memory accumulation."""
        try:
            if getattr(self.config, "ndjson_output", True):
                with open(self.config.ndjson_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
                self.results.append(item)
                max_keep = getattr(self.config, "max_in_memory_results", 100)
                if len(self.results) > max_keep:
                    self.results = self.results[-max_keep:]
            else:
                # Legacy behavior: keep full list and atomically write JSON
                self.results.append(item)
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
        browser_config = BrowserConfig(
            headless=self.config.headless,
            text_mode=getattr(self.config, "text_mode", True),
            light_mode=getattr(self.config, "light_mode", True),
            viewport_width=getattr(self.config, "viewport_width", 1040),
            viewport_height=getattr(self.config, "viewport_height", 768),
            extra_args=[
                "--disable-dev-shm-usage",
                "--disable-background-networking",
                "--disable-background-timer-throttling",
                "--disable-breakpad",
                "--disable-client-side-phishing-detection",
                "--disable-default-apps",
                "--disable-extensions",
                "--disable-features=Translate,BackForwardCache,AcceptCHFrame,MediaRouter",
                "--disable-ipc-flooding-protection",
                "--disable-popup-blocking",
                "--disable-prompt-on-repost",
                "--disable-renderer-backgrounding",
                "--force-color-profile=srgb",
                "--metrics-recording-only",
                "--no-first-run",
                "--enable-features=NetworkService,NetworkServiceInProcess",
            ],
        )
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
                    finally:
                        await _asyncio.sleep(0)  # yield
            
            workers = [asyncio.create_task(worker(i)) for i in range(max(1, self.config.concurrency))]
            # Attendi che tutti i worker terminino quando la frontier si svuota
            await asyncio.gather(*workers)
        
        logger.info("Crawl finished; collected %d pages", len(self.results))
        return self.results