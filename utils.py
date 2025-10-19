"""Utility functions for URL processing and validation."""

import re
from urllib.parse import urlparse
from typing import List


def is_http_url(url: str) -> bool:
    """Check if URL is HTTP/HTTPS."""
    return url.startswith(("http://", "https://"))

def same_domain_and_path(url: str, allow: str, allow_subdomains: bool) -> bool:
    """
    Check if a URL belongs to the allowed domain (and optionally subdomains)
    and starts with the allowed path.
    
    Example:
        same_domain_and_path(
            "https://carders.biz/members/123",
            "carders.biz/members/",
            allow_subdomains=False
        ) -> True
    """
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    path = parsed.path.lower()
    
    # Split allowed into domain + path
    allow = allow.lower()
    if "/" in allow:
        domain, allowed_path = allow.split("/", 1)
        allowed_path = "/" + allowed_path  # ensure it starts with '/'
    else:
        domain, allowed_path = allow, "/"
    
    # Domain check
    if allow_subdomains:
        domain_ok = netloc == domain or netloc.endswith(f".{domain}")
    else:
        domain_ok = netloc == domain

    # Path check (must start with allowed_path)
    path_ok = path.startswith(allowed_path)
    
    return domain_ok and path_ok


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