"""
Test script for the backoff strategy in RateLimitedFetcher.
"""
import logging
import sys
import time
import os
import django

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.agents.utils.rate_limited_fetcher import RateLimitedFetcher
from apps.agents.tools.web_crawler_tool.web_crawler_tool import crawl_website

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(name)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger("test_backoff_strategy")

def test_rate_limited_fetcher():
    """Test the RateLimitedFetcher with backoff strategy."""
    logger.info("Testing RateLimitedFetcher with backoff strategy")

    # Initialize rate limiting for a domain
    domain = "paradisefloorsandmore.com"
    RateLimitedFetcher.init_rate_limiting(domain, 1.0, None)

    # Test fetching a URL
    url = "https://paradisefloorsandmore.com/"
    logger.info(f"Fetching URL: {url}")

    result = RateLimitedFetcher.fetch_url(url, max_retries=3)

    if result.get("success", False):
        logger.info(f"Successfully fetched URL: {url}")
        logger.info(f"Content length: {len(result.get('content', ''))}")
    else:
        logger.error(f"Failed to fetch URL: {url}")
        logger.error(f"Error: {result.get('error')}")

    # Test the session timeout feature by manipulating the session start time
    logger.info("Testing session timeout feature")

    # Set the session start time to 55 minutes ago
    with RateLimitedFetcher._get_domain_lock(domain):
        RateLimitedFetcher._session_start_time[domain] = time.time() - 3300  # 55 minutes ago

    # Try fetching again - should trigger session cooldown
    logger.info(f"Fetching URL after session timeout: {url}")
    result = RateLimitedFetcher.fetch_url(url, max_retries=3)

    if result.get("success", False):
        logger.info(f"Successfully fetched URL after session timeout: {url}")
    else:
        logger.error(f"Failed to fetch URL after session timeout: {url}")
        logger.error(f"Error: {result.get('error')}")

def test_web_crawler():
    """Test the web crawler with backoff strategy."""
    logger.info("Testing web crawler with backoff strategy")

    # Test crawling a website
    url = "https://paradisefloorsandmore.com/"
    logger.info(f"Crawling website: {url}")

    result = crawl_website(
        start_url=url,
        max_pages=5,
        max_depth=1,
        output_format=["text", "links"],
        delay_seconds=2.0,  # Use a longer delay for testing
        mode="discovery"
    )

    if result and "results" in result:
        logger.info(f"Successfully crawled website: {url}")
        logger.info(f"Crawled {len(result['results'])} pages")

        # Print stats
        if "stats" in result:
            logger.info(f"Stats: {result['stats']}")
    else:
        logger.error(f"Failed to crawl website: {url}")
        logger.error(f"Result: {result}")

if __name__ == "__main__":
    # Run the tests
    test_rate_limited_fetcher()
    test_web_crawler()
