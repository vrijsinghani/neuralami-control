"""
Scraper adapters package.
"""
from .base import ScraperAdapter
from .firecrawl_adapter import FireCrawlAdapter
from .firecrawl_crawl_adapter import FireCrawlCrawlAdapter
from .playwright_adapter import PlaywrightAdapter

__all__ = ['ScraperAdapter', 'FireCrawlAdapter', 'FireCrawlCrawlAdapter', 'PlaywrightAdapter', 'get_adapter']

def get_adapter(adapter_type='playwright'):
    """
    Get a scraper adapter instance.

    Args:
        adapter_type: Type of adapter to get ('playwright', 'firecrawl', or 'firecrawl_crawl')

    Returns:
        ScraperAdapter instance
    """
    if adapter_type == 'playwright':
        return PlaywrightAdapter()
    elif adapter_type == 'firecrawl':
        return FireCrawlAdapter()
    elif adapter_type == 'firecrawl_crawl':
        return FireCrawlCrawlAdapter()
    else:
        raise ValueError(f"Unknown adapter type: {adapter_type}")
