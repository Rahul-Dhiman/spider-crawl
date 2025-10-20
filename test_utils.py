"""Unit tests for utility functions."""

import unittest
from utils import is_http_url, same_domain, url_path_depth, clean_text


class TestUtils(unittest.TestCase):
    """Test cases for utility functions."""
    
    def test_is_http_url(self):
        """Test HTTP URL validation."""
        self.assertTrue(is_http_url("https://example.com"))
        self.assertTrue(is_http_url("http://example.com"))
        self.assertFalse(is_http_url("ftp://example.com"))
        self.assertFalse(is_http_url("example.com"))
    
    def test_same_domain(self):
        """Test domain matching logic."""
        # Exact domain match
        self.assertTrue(same_domain_and_path("https://example.com/path", "example.com", False))
        self.assertFalse(same_domain_and_path("https://sub.example.com/path", "example.com", False))
        
        # Subdomain matching
        self.assertTrue(same_domain_and_path("https://sub.example.com/path", "example.com", True))
        self.assertTrue(same_domain_and_path("https://example.com/path", "example.com", True))
        self.assertFalse(same_domain_and_path("https://other.com/path", "example.com", True))
    
    def test_url_path_depth(self):
        """Test URL path depth calculation."""
        self.assertEqual(url_path_depth("https://example.com/"), 0)
        self.assertEqual(url_path_depth("https://example.com/page"), 1)
        self.assertEqual(url_path_depth("https://example.com/path/to/page"), 3)
    
    def test_clean_text(self):
        """Test text cleaning functionality."""
        dirty_text = "Text\twith\n\n\nmultiple   spaces"
        expected = "Text with multiple  spaces"
        self.assertEqual(clean_text(dirty_text), expected)


if __name__ == "__main__":
    unittest.main()