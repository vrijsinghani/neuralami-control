import unittest
from unittest.mock import patch, MagicMock
import json
from django.test import TestCase
from django.contrib.auth.models import User

from .web_crawler_tool import WebCrawlerTool, CrawlOutputFormat

class WebCrawlerToolTests(TestCase):
    """Tests for the WebCrawlerTool"""
    
    def setUp(self):
        """Set up test environment"""
        # Create a test user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='password'
        )
        
        # Create an instance of the tool
        self.crawler_tool = WebCrawlerTool()
        
        # Test URL
        self.test_url = "https://example.com"
    
    @patch('apps.agents.tools.scrapper_tool.ScrapperTool._run')
    def test_basic_crawl(self, mock_scrapper_run):
        """Test basic crawling functionality"""
        # Mock ScrapperTool response for initial page
        mock_scrapper_run.side_effect = [
            # First call - TEXT content
            json.dumps({
                "url": self.test_url,
                "domain": "example.com",
                "title": "Example Domain",
                "text": "This is an example website.",
            }),
            # Second call - LINKS content
            json.dumps({
                "url": self.test_url,
                "domain": "example.com",
                "title": "Example Domain",
                "links": [
                    {"url": "https://example.com/page1", "text": "Page 1"},
                    {"url": "https://example.com/page2", "text": "Page 2"},
                ]
            }),
            # Third call - TEXT content for page1
            json.dumps({
                "url": "https://example.com/page1",
                "domain": "example.com",
                "title": "Page 1",
                "text": "This is page 1.",
            }),
            # Fourth call - LINKS content for page1
            json.dumps({
                "url": "https://example.com/page1",
                "domain": "example.com",
                "title": "Page 1",
                "links": [
                    {"url": "https://example.com/page3", "text": "Page 3"},
                ]
            }),
            # Fifth call - TEXT content for page2
            json.dumps({
                "url": "https://example.com/page2",
                "domain": "example.com",
                "title": "Page 2",
                "text": "This is page 2.",
            }),
            # Sixth call - LINKS content for page2
            json.dumps({
                "url": "https://example.com/page2",
                "domain": "example.com",
                "title": "Page 2",
                "links": []
            }),
        ]
        
        # Run crawler with limited settings
        result = self.crawler_tool._run(
            start_url=self.test_url,
            user_id=self.user.id,
            max_pages=3,
            max_depth=1
        )
        
        # Check that result is valid JSON
        result_data = json.loads(result)
        
        # Validate the result
        self.assertEqual(result_data["status"], "success")
        self.assertEqual(result_data["start_url"], self.test_url)
        self.assertEqual(result_data["total_pages"], 3)
        
        # Verify that ScrapperTool was called the expected number of times
        self.assertEqual(mock_scrapper_run.call_count, 6)
    
    @patch('apps.agents.tools.scrapper_tool.ScrapperTool._run')
    def test_crawl_with_patterns(self, mock_scrapper_run):
        """Test crawling with include/exclude patterns"""
        # Mock ScrapperTool response
        mock_scrapper_run.side_effect = [
            # First call - TEXT content
            json.dumps({
                "url": self.test_url,
                "domain": "example.com",
                "title": "Example Domain",
                "text": "This is an example website.",
            }),
            # Second call - LINKS content
            json.dumps({
                "url": self.test_url,
                "domain": "example.com",
                "title": "Example Domain",
                "links": [
                    {"url": "https://example.com/blog/post1", "text": "Blog Post 1"},
                    {"url": "https://example.com/products/item1", "text": "Product 1"},
                    {"url": "https://example.com/blog/post2", "text": "Blog Post 2"},
                ]
            }),
            # Third call - TEXT content for blog/post1
            json.dumps({
                "url": "https://example.com/blog/post1",
                "domain": "example.com",
                "title": "Blog Post 1",
                "text": "This is blog post 1.",
            }),
            # Fourth call - LINKS content for blog/post1
            json.dumps({
                "url": "https://example.com/blog/post1",
                "domain": "example.com",
                "title": "Blog Post 1",
                "links": []
            }),
            # Fifth call - TEXT content for blog/post2
            json.dumps({
                "url": "https://example.com/blog/post2",
                "domain": "example.com",
                "title": "Blog Post 2",
                "text": "This is blog post 2.",
            }),
            # Sixth call - LINKS content for blog/post2
            json.dumps({
                "url": "https://example.com/blog/post2",
                "domain": "example.com",
                "title": "Blog Post 2",
                "links": []
            }),
        ]
        
        # Run crawler with include pattern for blog posts only
        result = self.crawler_tool._run(
            start_url=self.test_url,
            user_id=self.user.id,
            max_pages=5,
            max_depth=1,
            include_patterns=["blog"]
        )
        
        # Check that result is valid JSON
        result_data = json.loads(result)
        
        # Validate the result - should only have the main page and 2 blog posts
        self.assertEqual(result_data["status"], "success")
        self.assertEqual(result_data["total_pages"], 3)
        
        # All results should be either the main page or have "blog" in the URL
        for page_result in result_data["results"]:
            self.assertTrue(page_result["url"] == self.test_url or "blog" in page_result["url"])
    
    @patch('apps.agents.tools.scrapper_tool.ScrapperTool._run')
    def test_error_handling(self, mock_scrapper_run):
        """Test error handling during crawling"""
        # Mock ScrapperTool to return error for some URLs
        def side_effect_func(url, **kwargs):
            if url == self.test_url:
                # Main page succeeds
                return json.dumps({
                    "url": self.test_url,
                    "domain": "example.com",
                    "title": "Example Domain",
                    "text": "This is an example website.",
                })
            elif url == "https://example.com/page1":
                # Page 1 succeeds with links
                if kwargs.get('output_type') == 'links':
                    return json.dumps({
                        "url": url,
                        "domain": "example.com",
                        "links": [
                            {"url": "https://example.com/error", "text": "Error Page"},
                        ]
                    })
                else:
                    return json.dumps({
                        "url": url,
                        "domain": "example.com",
                        "title": "Page 1",
                        "text": "This is page 1."
                    })
            elif url == "https://example.com/error":
                # Error page fails
                return json.dumps({
                    "success": False,
                    "error": "Failed to load page",
                    "url": url
                })
            else:
                # Default page with no links
                if kwargs.get('output_type') == 'links':
                    return json.dumps({
                        "url": url,
                        "domain": "example.com",
                        "links": []
                    })
                else:
                    return json.dumps({
                        "url": url,
                        "domain": "example.com",
                        "title": f"Page at {url}",
                        "text": f"Content at {url}"
                    })
        
        mock_scrapper_run.side_effect = side_effect_func
        
        # Run crawler
        result = self.crawler_tool._run(
            start_url=self.test_url,
            user_id=self.user.id,
            max_pages=5,
            max_depth=2
        )
        
        # Check that result is valid JSON
        result_data = json.loads(result)
        
        # Validate the result
        self.assertEqual(result_data["status"], "success")
        # Should only have successfully crawled pages
        self.assertGreaterEqual(result_data["total_pages"], 1)
        
        # Verify the error page is not in the results
        error_page_found = False
        for page_result in result_data["results"]:
            if page_result["url"] == "https://example.com/error":
                error_page_found = True
                break
        
        self.assertFalse(error_page_found, "Error page should not be in results")

if __name__ == "__main__":
    unittest.main() 