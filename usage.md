# Spider Crawl - Usage Guide

This guide explains how to install, configure and run the crawler, how to tune performance and politeness, and how to resume or scale runs safely.

## 1) Requirements

- Python 3.9+
- A POSIX-like environment (Linux/macOS recommended)
- Network access to the target site(s)

Install dependencies:

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 2) Quick Start

Run with environment-based configuration (recommended for automation):

```bash
export SITEMAP_SEED="https://example.com/sitemap.xml"
export DOMAIN_ALLOW="example.com"
python main.py
```

Run via the CLI (single sitemap):

```bash
python cli.py \
  --domain example.com \
  --concurrency 8 \
  --max-pages 5000 \
  --delay 0.5 \
  https://example.com/sitemap.xml
```

Output is written to the file configured by `OUTPUT_FILE` (default: `crawl_output.json`) and also printed to stdout.

## 3) Configuration (environment variables)

The crawler is configured through environment variables read by `config.py`. Key options:

- SITEMAP_SEED: Seed sitemap URL. Example: `https://example.com/sitemap.xml`
- DOMAIN_ALLOW: Allowed domain for filtering. Example: `example.com`
- ALLOW_SUBDOMAINS: `true|false` (default: `true`)
- MAX_PATH_DEPTH: Optional integer to limit URL path depth.
- CONCURRENCY: Number of parallel workers (default: 20)
- HEADLESS: `true|false` (default: `true`)
- BYPASS_CACHE: `true|false` (default: `true`)
- REQUEST_TIMEOUT_MS: Page request timeout (default: 30000)
- MAX_PAGES: Global limit of pages from sitemaps (default: very high)
- PAGINATION_LIMIT: Max intra-page pagination steps (default: 1000)
- OUTPUT_FILE: JSON output path (default: `crawl_output.json`)
- USER_AGENT: Custom UA string (default: `SpiderCrawl/1.0 (+https://example.com/bot)`)
- POLITENESS_JITTER_MS: Random jitter added to delays (default: 150)
- DELAY_BETWEEN_PAGES_SEC: Base politeness delay between page fetches (default: 0.3)
- RECYCLE_EVERY_N_PAGES: Recycle browser every N processed pages (default: 200)
- MAX_DEPTH: Crawl depth used by the frontier when adding new links (default: 3)
- FRONTIER_DB_PATH: SQLite file for the persistent URL frontier (default: `frontier.db`)
- ENABLE_METRICS: `true|false` toggle for future system metrics logging (default: `true`)

Tip: You can place these in a shell script or `.env` and `source` it before running.

## 4) What the crawler does

1. Expands the provided sitemap(s), filtering to the allowed domain and optional max path depth.
2. Enqueues normalized URLs into a persistent SQLite frontier (`frontier.db`).
3. Crawls with a bounded worker pool (concurrency), using polite delays with jitter.
4. Extracts main content (from `<article>` blocks and/or page markdown) and saves JSON items with `{ url, "Body text content", hash }`.
5. Periodically writes incremental results and recycles the browser to avoid long-running memory growth.

## 5) Politeness and User-Agent

- A clear User-Agent is sent for HTTP requests (sitemaps and helpers). You can customize with `USER_AGENT`.
- Delays: The crawler applies `DELAY_BETWEEN_PAGES_SEC` plus a small random jitter (`POLITENESS_JITTER_MS`) to spread load.
- Consider increasing `DELAY_BETWEEN_PAGES_SEC` and lowering `CONCURRENCY` for sensitive servers.

## 6) Persistent URL Frontier

- The frontier is backed by SQLite (`FRONTIER_DB_PATH`). This enables:
  - Durability across restarts
  - Dedupe-by-URL before fetching
  - Depth tracking (used when you add new links into the queue)
- You can inspect the queue with any SQLite viewer if needed.

## 7) Output format

`crawl_output.json` example:

```json
[
  {
    "url": "https://example.com/page1",
    "Body text content": "Extracted content...",
    "hash": "<sha256>"
  }
]
```

The `hash` field helps detect duplicate content across pages or runs.

## 8) Resuming a run

Because the URL frontier is persistent, you can stop the process and start it again later. Already visited URLs remain marked; pending ones stay queued.

Practical flow:

```bash
# First run
python main.py

# Stop at any time (Ctrl+C)

# Resume later with the same FRONTIER_DB_PATH
python main.py
```

## 9) Performance and memory tips

- Prefer a modest `CONCURRENCY` (e.g., 5–10) for heavy JavaScript sites.
- Increase `DELAY_BETWEEN_PAGES_SEC` on smaller servers.
- Leave `RECYCLE_EVERY_N_PAGES` at a reasonable cadence (100–500) to minimize long-run memory accumulation.
- If you observe many Chrome/Playwright processes, reduce `CONCURRENCY` and/or raise delay settings.

## 10) Troubleshooting

- Import errors for `crawl4ai`: Ensure the virtual environment is active and dependencies are installed: `pip install -r requirements.txt`.
- "No URLs to crawl": Verify `SITEMAP_SEED`, `DOMAIN_ALLOW`, and any depth filters.
- Large memory usage: Lower `CONCURRENCY`, raise `DELAY_BETWEEN_PAGES_SEC`, and keep `RECYCLE_EVERY_N_PAGES` enabled.
- HTTP errors on sitemap fetch: Check that the sitemap is publicly accessible; customize `USER_AGENT` if necessary.

## 11) Respect site policies

Always follow the target site’s Terms of Service and robots.txt rules. Keep concurrency and delays conservative unless you have explicit permission from the site owner.

## 12) Extending the crawler

- Depth-limited discovery: When adding in-page link discovery, use `MAX_DEPTH` to prevent traps and loops.
- Status code handling: Integrate per-request logging of HTTP status codes if your fetcher exposes them. `crawl4ai` already signals success/failure.
- System metrics: With `psutil` installed, you can periodically log CPU/RAM/disk/network metrics for capacity planning.

---

If you run into issues or want to add features (e.g., robots.txt parsing, advanced prioritization, or distributed crawling), open an issue or extend the modules in place:
`config.py`, `sitemap_parser.py`, `frontier.py`, `crawler.py`, and `utils.py`.


