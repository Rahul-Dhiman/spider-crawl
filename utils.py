"""Utility functions for URL processing and validation."""

import re
from urllib.parse import urlparse
from typing import List


def is_http_url(url: str) -> bool:
    """Check if URL is HTTP/HTTPS."""
    return url.startswith(("http://", "https://"))


def same_domain(url: str, allow: str, allow_subdomains: bool) -> bool:
    """Check if URL belongs to allowed domain."""
    netloc = urlparse(url).netloc.lower()
    allow = allow.lower()
    
    if allow_subdomains:
        return netloc == allow or netloc.endswith(f".{allow}")
    return netloc == allow


def url_path_depth(url: str) -> int:
    """Calculate URL path depth."""
    path = urlparse(url).path
    return len([seg for seg in path.split("/") if seg])


def extract_article_text(html: str) -> List[str]:
    """Extract text content from article tags."""
    matches = re.findall(r'(?is)<article\b[^>]*>(.*?)</article>', html)
    collected = []
    
    for inner in matches:
        text = re.sub(r'(?s)<[^>]+>', '', inner)
        text = text.replace('\n', ' ').replace('\t', ' ')
        text = re.sub(r' {3,}', '  ', text).strip()
        if text:
            collected.append(text)
    
    return collected


def find_next_page_url(html: str, current_url: str) -> str:
    """Find next page URL from pagination links."""
    from urllib.parse import urljoin
    
    patterns = [
        r'(?is)<a[^>]+class=["\'[^"\']*pageNav-jump--next[^"\']*["\'][^>]*href=["\']([^"\']+)["\']',
        r'(?is)<a[^>]*href=["\']([^"\']+)["\'][^>]*>\s*<[^>]*pageNav-jump--next'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return urljoin(current_url, match.group(1))
    
    return ""


def clean_text(text: str) -> str:
    """Clean and normalize text content."""
    text = text.replace('\n', ' ').replace('\t', ' ')
    return re.sub(r' {3,}', '  ', text).strip()