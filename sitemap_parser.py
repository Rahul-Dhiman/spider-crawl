"""Sitemap parsing and URL extraction functionality."""

import gzip
import io
import logging
import xml.etree.ElementTree as ET
from typing import List, Set, Iterable

import requests

from utils import is_http_url, same_domain_and_path, url_path_depth

logger = logging.getLogger(__name__)


class SitemapParser:
    """Handles sitemap parsing and URL extraction."""
    
    def __init__(self, domain: str, allow_subdomains: bool, max_path_depth: int = None):
        self.domain = domain
        self.allow_subdomains = allow_subdomains
        self.max_path_depth = max_path_depth
    
    def fetch_sitemap_content(self, url: str) -> bytes:
        """Download and decompress sitemap content."""
        logger.info("Downloading sitemap: %s", url)
        
        try:
            response = requests.get(url, timeout=45)
            response.raise_for_status()
            
            content = response.content
            content_type = response.headers.get("Content-Type", "").lower()
            
            if "gzip" in content_type or url.lower().endswith(".gz"):
                logger.info("Detected gzip; decompressing")
                content = gzip.GzipFile(fileobj=io.BytesIO(content)).read()
            
            return content
            
        except Exception as e:
            logger.error("Failed to fetch sitemap %s: %s", url, e)
            raise
    
    def parse_xml_root(self, content: bytes) -> ET.Element:
        """Parse XML content and return root element."""
        return ET.fromstring(content)
    
    def get_tag_suffix(self, elem: ET.Element) -> str:
        """Extract local tag name from namespaced element."""
        if elem.tag.rfind("}") != -1:
            return elem.tag.split("}", 1)[1]
        return elem.tag
    
    def extract_locations(self, root: ET.Element) -> Iterable[str]:
        """Extract all <loc> element text content."""
        for loc in root.iter():
            if self.get_tag_suffix(loc) == "loc" and (loc.text or "").strip():
                yield loc.text.strip()
    
    def is_sitemap_index(self, root: ET.Element) -> bool:
        """Check if root element is a sitemap index."""
        return self.get_tag_suffix(root) == "sitemapindex"
    
    def is_urlset(self, root: ET.Element) -> bool:
        """Check if root element is a URL set."""
        return self.get_tag_suffix(root) == "urlset"
    
    def is_valid_page_url(self, url: str) -> bool:
        """Check if URL meets filtering criteria."""
        if not is_http_url(url):
            return False
        
        if not same_domain_and_path(url, self.domain, self.allow_subdomains):
            return False
        
        if (self.max_path_depth is not None and 
            url_path_depth(url) > self.max_path_depth):
            return False
        
        return True
    
    def expand_sitemaps(self, seed_urls: List[str], max_urls: int) -> List[str]:
        """Recursively expand sitemap indexes into page URLs."""
        queue: List[str] = list(seed_urls)
        seen_sitemaps: Set[str] = set()
        page_urls: List[str] = []
        
        while queue and len(page_urls) < max_urls:
            sitemap_url = queue.pop(0)
            
            if sitemap_url in seen_sitemaps:
                continue
            
            seen_sitemaps.add(sitemap_url)
            
            try:
                content = self.fetch_sitemap_content(sitemap_url)
                root = self.parse_xml_root(content)
            except Exception as e:
                logger.warning("Failed to process sitemap %s: %s", sitemap_url, e)
                continue
            
            root_kind = self.get_tag_suffix(root)
            locations = list(self.extract_locations(root))
            
            logger.info("Parsed %s: %s | <loc> count=%d", 
                       sitemap_url, root_kind, len(locations))
            
            if self.is_sitemap_index(root):
                child_sitemaps = [url for url in locations if is_http_url(url)]
                queue.extend(child_sitemaps)
                logger.info("Queued %d child sitemaps (queue size=%d)", 
                           len(child_sitemaps), len(queue))
            
            elif self.is_urlset(root):
                print(f"DEBUG: Processing urlset with {len(locations)} locations")
                logger.info("Processing urlset with %d locations", len(locations))
                accepted = self._process_urlset(locations, page_urls, max_urls)
                print(f"DEBUG: Accepted {accepted} URLs from this urlset")
                logger.info("Accepted %d URLs (total so far=%d)", 
                           accepted, len(page_urls))
            
            else:
                # Unknown root type - treat as best-effort URL set
                accepted = self._process_urlset(locations, page_urls, max_urls)
                logger.info("Unknown sitemap type; best-effort accepted %d (total=%d)", 
                           accepted, len(page_urls))
        
        return page_urls
    
    def _process_urlset(self, locations: List[str], page_urls: List[str], 
                       max_urls: int) -> int:
        """Process URLs from a urlset and add valid ones to page_urls."""
        accepted = 0
        rejected = 0
        
        for url in locations:
            if len(page_urls) >= max_urls:
                break
            
            if self.is_valid_page_url(url):
                page_urls.append(url)
                accepted += 1
                print(f"DEBUG: ACCEPTED: {url}")
            else:
                rejected += 1
                print(f"DEBUG: REJECTED: {url} (domain_match: {same_domain_and_path(url, self.domain, self.allow_subdomains)})")
        
        print(f"DEBUG: Final count - accepted={accepted}, rejected={rejected}")
        logger.info("URL processing: accepted=%d, rejected=%d", accepted, rejected)
        return accepted