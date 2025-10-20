"""Utility functions for URL processing and validation."""

import logging
import re
import hashlib
from urllib.parse import urlparse, urlunparse, urljoin, quote, unquote
from typing import List

logger = logging.getLogger(__name__)
 
def is_http_url(url: str) -> bool:
    """Check if URL is HTTP/HTTPS."""
    return url.startswith(("http://", "https://"))

def same_domain(url: str, allow: str, allow_subdomains: bool) -> bool:
    """
    Check if a URL belongs to an allowed domain and matches a specific path prefix.
    
    'allow' can be:
    - 'https://example.com' (matches any path on the domain)
    - 'example.com/path/v2' (matches 'example.com/path/v2' or 'example.com/path/v2/more')
    """
    try:
        # 1. Parse the target URL
        url_parts = urlparse(url.lower())
        url_netloc = url_parts.netloc
        # Normalize path: always start with '/', never end with one (unless it's just '/')
        url_path = '/' + url_parts.path.strip('/')

        # 2. Parse the 'allow' string
        # Add a dummy scheme if one is missing to help urlparse
        allow_to_parse = allow.lower()
        if not allow_to_parse.startswith(('http://', 'https://', '//')):
            allow_to_parse = f"//{allow_to_parse}"
            
        allow_parts = urlparse(allow_to_parse)
        allow_netloc = allow_parts.netloc
        # Normalize path
        allow_path = '/' + allow_parts.path.strip('/')

        # 3. Check Domain
        domain_match = False
        if allow_subdomains:
            # Allow 'example.com' OR 'sub.example.com'
            domain_match = (url_netloc == allow_netloc or url_netloc.endswith(f".{allow_netloc}"))
        else:
            # Allow ONLY 'example.com'
            domain_match = (url_netloc == allow_netloc)

        if not domain_match:
            return False

        # 4. Check Path
        # If domain matches, check if the URL path starts with the allowed path
        
        # If the allowed path is just '/', it's a wildcard for all paths
        if allow_path == '/':
            return True

        # Check if url_path starts with allow_path
        if not url_path.startswith(allow_path):
            return False
            
        # We need to ensure we're matching a full path segment.
        # This prevents '.../path/v2page' from matching '.../path/v2'
        
        # If paths are identical, it's a match
        if len(url_path) == len(allow_path):
            return True
            
        # If url_path is longer, the next character must be a '/'
        return url_path[len(allow_path)] == '/'

    except ValueError:
        # Handle potential malformed URLs
        return False

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


def normalize_url(url: str, base: str = "") -> str:
    """Normalize URL for dedupe: lower host, strip fragments, canonicalize path and query."""
    if base:
        url = urljoin(base, url)
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = quote(unquote(parsed.path or "/"))
    query = parsed.query
    # Remove default ports
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]
    return urlunparse((scheme, netloc, path, "", query, ""))


def compute_hash(content: str) -> str:
    """Stable SHA256 of a text for duplicate detection."""
    h = hashlib.sha256()
    h.update(content.encode("utf-8", errors="ignore"))
    return h.hexdigest()