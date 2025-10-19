# Web Scraper

A modular Python web scraper that extracts content from websites using sitemaps with support for authentication and pagination.

## Features

- **Sitemap-based crawling**: Automatically discovers URLs from XML sitemaps
- **Authentication support**: Login to protected sites before crawling
- **Pagination handling**: Follows pagination links to collect complete content
- **Concurrent crawling**: Configurable concurrency for efficient scraping
- **Modular architecture**: Clean separation of concerns for maintainability
- **Environment-based configuration**: Secure credential management
- **Comprehensive logging**: Detailed logging with appropriate levels

## Installation

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your actual configuration
```

## Usage

### Basic Usage

```bash
python main.py
```

### Environment Variables

Key configuration options:

- `SITEMAP_SEED`: URL of the sitemap to crawl
- `DOMAIN_ALLOW`: Domain to restrict crawling to
- `USE_LOGIN`: Enable authentication (true/false)
- `USERNAME`/`PASSWORD`: Login credentials
- `CONCURRENCY`: Number of concurrent requests
- `OUTPUT_FILE`: Output JSON file path

See `.env.example` for all available options.

## Architecture

The application is structured into focused modules:

- `main.py`: Application entry point and orchestration
- `config.py`: Configuration management with environment variable support
- `sitemap_parser.py`: XML sitemap parsing and URL extraction
- `crawler.py`: Web crawling with authentication and pagination
- `utils.py`: Utility functions for URL processing and text extraction
- `logger_config.py`: Centralized logging configuration

## Output

Results are saved as JSON in the specified output file:

```json
[
  {
    "url": "https://example.com/page1",
    "Body text content": "Extracted content..."
  }
]
```

## Contributing

1. Follow PEP 8 style guidelines
2. Add type hints to all functions
3. Include docstrings for classes and functions
4. Write tests for new functionality
5. Update documentation as needed"# spider-crawl" 
"# spider-crawl" 
# spider-crawl
# spider-crawl
