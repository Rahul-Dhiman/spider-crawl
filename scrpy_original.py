import asyncio

import gzip

import io

import json

import logging

import sys

import time

from typing import List, Set, Tuple, Iterable

from urllib.parse import urlparse, urljoin

import requests

import xml.etree.ElementTree as ET

import re

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
import os
import tempfile

# ──────────────────────────────────────────────────────────────────────────────

# USER CONFIG — EDIT THESE

# ──────────────────────────────────────────────────────────────────────────────

SITEMAP_SEEDS = [

    "https://carders.biz/sitemap.xml",     # your top-level sitemap (can be .xml or .gz)

]

DOMAIN_ALLOW = "carders.biz"               # keep URLs on this domain

ALLOW_SUBDOMAINS = True                    # True => *.example.com allowed

# interpret "depth 10" as URL path depth ≤ 10. Set to None to disable depth filtering
MAX_PATH_DEPTH = None

# Crawl behavior

CONCURRENCY = 20

HEADLESS = True

BYPASS_CACHE = True

REQUEST_TIMEOUT_MS = 30000

MAX_PAGES = 100000000                         # safety cap
PAGINATION_LIMIT = 1000

OUTPUT_FILE = "crawl_output.json"

# Optional login (set USE_LOGIN=False if not needed)

USE_LOGIN = True

LOGIN_URL = "https://carders.biz/login/"

USERNAME = "aslamkhan2767@gmail.com"

PASSWORD = "aslan2767@"

USERNAME_SELECTOR = 'input[name="login"]'

PASSWORD_SELECTOR = 'input[name="password"]'

SUBMIT_SELECTOR   = '.button--icon--login'

POST_LOGIN_READY_SELECTOR = ".p-navgroup-link--user"   # appears only after successful login

# Politeness (optional)

DELAY_BETWEEN_PAGES_SEC = 0.3   # set small delay if the site is sensitive to load

# ──────────────────────────────────────────────────────────────────────────────

# LOGGING (compact; never logs body content)

# ──────────────────────────────────────────────────────────────────────────────

logger = logging.getLogger("sitemap-index-crawler")

handler = logging.StreamHandler(sys.stdout)

formatter = logging.Formatter("[%(levelname)s] %(asctime)s - %(message)s", datefmt="%H:%M:%S")

handler.setFormatter(formatter)

logger.addHandler(handler)

logger.setLevel(logging.INFO)

# ──────────────────────────────────────────────────────────────────────────────

# HELPERS

# ──────────────────────────────────────────────────────────────────────────────

def is_http_url(s: str) -> bool:

    return s.startswith("http://") or s.startswith("https://")

def same_domain_and_path(url: str, allow: str, allow_subdomains: bool) -> bool:

    netloc = urlparse(url).netloc.lower()

    allow = allow.lower()

    if allow_subdomains:

        return netloc == allow or netloc.endswith("." + allow)

    return netloc == allow

def url_path_depth(url: str) -> int:

    path = urlparse(url).path

    return len([seg for seg in path.split("/") if seg])

def fetch_bytes(url: str) -> bytes:

    logger.info("Downloading sitemap: %s", url)

    r = requests.get(url, timeout=45)

    r.raise_for_status()

    data = r.content

    ct = r.headers.get("Content-Type", "").lower()

    if "gzip" in ct or url.lower().endswith(".gz"):

        logger.info("Detected gzip; decompressing")

        data = gzip.GzipFile(fileobj=io.BytesIO(data)).read()

    return data

def parse_xml_root(content: bytes) -> ET.Element:

    # ElementTree gracefully handles namespaces; we’ll match by tag suffix

    return ET.fromstring(content)

def tag_suffix(elem: ET.Element) -> str:

    # '{namespace}localname' -> 'localname'

    if elem.tag.rfind("}") != -1:

        return elem.tag.split("}", 1)[1]

    return elem.tag

def extract_locs(root: ET.Element) -> Iterable[str]:

    # Return every text content of <loc> elements in document

    for loc in root.iter():

        if tag_suffix(loc) == "loc" and (loc.text or "").strip():

            yield loc.text.strip()

def is_sitemap_index(root: ET.Element) -> bool:

    return tag_suffix(root) == "sitemapindex"

def is_urlset(root: ET.Element) -> bool:

    return tag_suffix(root) == "urlset"

def expand_sitemaps(seed_urls: List[str],

                    domain: str,

                    allow_subdomains: bool,

                    max_urls: int) -> List[str]:

    """

    Recursively expands sitemap indexes into page URLs.

    Filters to same domain and MAX_PATH_DEPTH.

    """

    queue: List[str] = list(seed_urls)

    seen_sitemaps: Set[str] = set()

    page_urls: List[str] = []

    while queue and len(page_urls) < max_urls:

        sm_url = queue.pop(0)

        if sm_url in seen_sitemaps:

            continue

        seen_sitemaps.add(sm_url)

        try:

            content = fetch_bytes(sm_url)

            root = parse_xml_root(content)

        except Exception as e:

            logger.warning("Failed to read sitemap %s: %s", sm_url, e)

            continue

        root_kind = tag_suffix(root)

        locs = list(extract_locs(root))

        logger.info("Parsed %s: %s | <loc> count=%d", sm_url, root_kind, len(locs))

        if is_sitemap_index(root):

            # Each <loc> is another sitemap

            children = [u for u in locs if is_http_url(u)]

            queue.extend(children)

            logger.info("Queued %d child sitemaps (queue size=%d)", len(children), len(queue))

        elif is_urlset(root):

            accepted = 0

            for u in locs:

                if not is_http_url(u):

                    continue

                if not same_domain_and_path(u, domain, allow_subdomains):

                    continue

                if MAX_PATH_DEPTH is not None and url_path_depth(u) > MAX_PATH_DEPTH:

                    continue

                page_urls.append(u)

                accepted += 1

                if len(page_urls) >= max_urls:

                    break

            logger.info("Accepted %d URLs (total so far=%d)", accepted, len(page_urls))

        else:

            # Unknown root; best-effort treat all <loc> as pages

            accepted = 0

            for u in locs:

                if not is_http_url(u):

                    continue

                if not same_domain_and_path(u, domain, allow_subdomains):

                    continue

                if MAX_PATH_DEPTH is not None and url_path_depth(u) > MAX_PATH_DEPTH:

                    continue

                page_urls.append(u)

                accepted += 1

                if len(page_urls) >= max_urls:

                    break

            logger.info("Unknown sitemap type; best-effort accepted %d (total=%d)", accepted, len(page_urls))

    return page_urls

# ──────────────────────────────────────────────────────────────────────────────

# LOGIN HOOK (runs once per context)

# ──────────────────────────────────────────────────────────────────────────────

async def login_hook(page, context, **kwargs):
    if not USE_LOGIN:
        return page

    # Avoid re-running login on the same browser context
    try:
        if getattr(context, "_login_done", False):
            return page
    except Exception:
        # context proxies may not allow attribute access in some implementations
        pass

    logger.info("Starting login flow...")

    try:
        # navigate to login page and wait for the expected form
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT_MS)

        # ensure username field is present before filling
        await page.wait_for_selector(USERNAME_SELECTOR, timeout=REQUEST_TIMEOUT_MS)

        await page.fill(USERNAME_SELECTOR, USERNAME, timeout=REQUEST_TIMEOUT_MS)
        await page.fill(PASSWORD_SELECTOR, PASSWORD, timeout=REQUEST_TIMEOUT_MS)
        await page.click(SUBMIT_SELECTOR)

        # wait until some element that only appears after login is visible
        await page.wait_for_selector(POST_LOGIN_READY_SELECTOR, timeout=REQUEST_TIMEOUT_MS)

        cookies = await context.cookies()
        logger.info("Login successful; cookies=%d", len(cookies))

        # mark context as logged-in to avoid re-running for this context
        try:
            setattr(context, "_login_done", True)
        except Exception:
            pass

    except Exception as e:
        # Don't raise here; failing to login in a single context shouldn't break the crawl.
        logger.warning("Login flow failed for this context: %s", e)

    return page

# ──────────────────────────────────────────────────────────────────────────────

# CRAWL

# ──────────────────────────────────────────────────────────────────────────────

async def crawl_urls(urls: List[str]) -> List[dict]:

    """

    Crawl URLs concurrently and return:

      [{ "url": ..., "Body text content": ... }, ...]

    """

    results: List[dict] = []

    browser_conf = BrowserConfig(
        headless=HEADLESS,
    )


    run_conf = CrawlerRunConfig(

        cache_mode=CacheMode.BYPASS if BYPASS_CACHE else CacheMode.DEFAULT,

        js_code="try{window.scrollTo(0, document.body.scrollHeight);}catch(e){}",

    )

    sem = asyncio.Semaphore(CONCURRENCY)

    async def fetch_one(crawler: AsyncWebCrawler, url: str):

        async with sem:

            t0 = time.time()

            try:

                res = await crawler.arun(url, config=run_conf)

                if not res or not res.success:

                    logger.warning("FAILED: %s", url)

                    return

                html = res.html or ""
                collected: List[str] = []
                seen_pages: Set[str] = set()
                current_url = url
                first_html_len = 0
                first_markdown = ""
                pages_followed = 0

                while current_url and pages_followed < PAGINATION_LIMIT:
                    if current_url in seen_pages:
                        break
                    seen_pages.add(current_url)
                    pages_followed += 1

                    if pages_followed == 1:
                        page_res = res
                    else:
                        page_res = await crawler.arun(current_url, config=run_conf)

                    if not page_res or not page_res.success:
                        logger.warning("FAILED page: %s", current_url)
                        break

                    page_html = page_res.html or ""
                    if pages_followed == 1:
                        first_html_len = len(page_html)
                        first_markdown = (page_res.markdown.raw_markdown if page_res.markdown else "") or ""

                    if page_html:
                        matches = re.findall(r'(?is)<article\b[^>]*>(.*?)</article>', page_html)
                        for inner in matches:
                            text = re.sub(r'(?s)<[^>]+>', '', inner)
                            text = text.replace('\n', ' ').replace('\t', ' ')
                            text = re.sub(r' {3,}', '  ', text)
                            text = text.strip()
                            if text:
                                collected.append(text)

                    m = re.search(r'(?is)<a[^>]+class=["\'][^"\']*pageNav-jump--next[^"\']*["\'][^>]*href=["\']([^"\']+)["\']', page_html)
                    if not m:
                        m = re.search(r'(?is)<a[^>]*href=["\']([^"\']+)["\'][^>]*>\s*<[^>]*pageNav-jump--next', page_html)

                    if m:
                        next_href = m.group(1)
                        next_url = urljoin(current_url, next_href)
                        if not same_domain_and_path(next_url, DOMAIN_ALLOW, ALLOW_SUBDOMAINS):
                            break
                        current_url = next_url
                        if DELAY_BETWEEN_PAGES_SEC > 0:
                            await asyncio.sleep(DELAY_BETWEEN_PAGES_SEC)
                        continue
                    else:
                        break

                if collected:
                    body_text = "  ".join(collected).strip()
                else:
                    body_text = first_markdown.replace('\n', ' ').replace('\t', ' ')
                    body_text = re.sub(r' {3,}', '  ', body_text).strip()
                html_len = first_html_len

                dt = time.time() - t0

                logger.info("OK: %s | html_len=%d | body_len=%d | pages=%d | %.2fs",
                            url, html_len, len(body_text), pages_followed, dt)

                results.append({"url": url, "Body text content": body_text})
                # Persist incremental results to disk so output updates dynamically after each success.
                try:

                    fd, tmp_path = tempfile.mkstemp(prefix="crawl_", suffix=".json")
                    with os.fdopen(fd, "w", encoding="utf-8") as tf:
                        json.dump(results, tf, ensure_ascii=False, indent=2)
                    os.replace(tmp_path, OUTPUT_FILE)
                except Exception as e:
                    logger.warning("Failed to persist results after %s: %s", url, e)

                logger.info("Saved %d items (last=%s)", len(results), url)

                if DELAY_BETWEEN_PAGES_SEC > 0:

                    await asyncio.sleep(DELAY_BETWEEN_PAGES_SEC)

            except Exception as e:

                logger.warning("ERROR %s: %s", url, e)

    async with AsyncWebCrawler(config=browser_conf) as crawler:

        crawler.crawler_strategy.set_hook("on_page_context_created", login_hook)

        await crawler.start()

        urls = urls

        logger.info("Begin crawl of %d URLs (concurrency=%d)", len(urls), CONCURRENCY)

        tasks = [asyncio.create_task(fetch_one(crawler, u)) for u in urls]

        await asyncio.gather(*tasks, return_exceptions=True)

        await crawler.close()

    logger.info("Crawl finished; collected %d pages", len(results))

    return results

# ──────────────────────────────────────────────────────────────────────────────

# MAIN

# ──────────────────────────────────────────────────────────────────────────────

async def main():

    # 1) Expand all sitemap indexes into final page URLs (same domain + path depth)

    urls = expand_sitemaps(

        seed_urls=SITEMAP_SEEDS,

        domain=DOMAIN_ALLOW,

        allow_subdomains=ALLOW_SUBDOMAINS,

        max_urls=MAX_PAGES

    )

    logger.info("Sitemap expansion produced %d candidate URLs", len(urls))

    if not urls:

        logger.error("No URLs to crawl — check domain and depth filters.")

        return

    # 2) Crawl and collect body text

    data = await crawl_urls(urls)

    # 3) Write JSON to file & stdout (your requested shape)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:

        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info("Wrote JSON output to %s (items=%d)", OUTPUT_FILE, len(data))

    print(json.dumps(data, ensure_ascii=False))

if __name__ == "__main__":

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        logger.warning("Interrupted by user.")

    except Exception as e:

        logger.exception("Fatal error: %s", e)

        sys.exit(1)