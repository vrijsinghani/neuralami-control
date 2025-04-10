"""
Common utilities for web crawlers.
"""
import logging
import time
from urllib.parse import urlparse
from typing import Optional, Tuple

from apps.agents.utils.rate_limited_fetcher import RateLimitedFetcher

logger = logging.getLogger(__name__)

def init_crawler_rate_limiting(url: str, user_rate_limit: float) -> Tuple[str, Optional[float]]:
    """
    Initialize rate limiting for a crawler based on robots.txt and user settings.

    Args:
        url: The URL to crawl
        user_rate_limit: User-specified rate limit in requests per second

    Returns:
        Tuple of (normalized_domain, robots_crawl_delay)
    """
    try:
        # Parse and normalize the URL
        parsed_url = urlparse(url)
        domain = parsed_url.netloc

        # Normalize domain (remove www. if present)
        if domain.startswith('www.'):
            domain = domain[4:]

        # Check robots.txt for crawl-delay
        robots_crawl_delay = None

        # Try to get robots.txt from both www and non-www versions
        robots_urls = [
            f"https://{domain}/robots.txt",
            f"https://www.{domain}/robots.txt",
            f"http://{domain}/robots.txt",
            f"http://www.{domain}/robots.txt"
        ]

        for robots_url in robots_urls:
            try:
                logger.debug(f"Checking robots.txt at: {robots_url}")
                robots_result = RateLimitedFetcher.fetch_url(robots_url, max_retries=2)

                if robots_result.get("success", False):
                    robots_content = robots_result.get("content", "")
                    logger.debug(f"Successfully fetched robots.txt content from {robots_url}")

                    # Manual check for Crawl-delay directive
                    for line in robots_content.splitlines():
                        line = line.strip()
                        if line.lower().startswith("crawl-delay:"):
                            try:
                                # Extract the delay value
                                delay_value = line.split(":", 1)[1].strip()
                                robots_crawl_delay = float(delay_value)
                                logger.info(f"Found Crawl-delay: {robots_crawl_delay} in {robots_url}")
                                break
                            except (ValueError, IndexError) as e:
                                logger.warning(f"Error parsing Crawl-delay in {robots_url}: {e}")

                    # If we found a crawl-delay, no need to check other robots.txt files
                    if robots_crawl_delay is not None:
                        break
            except Exception as e:
                logger.warning(f"Error fetching robots.txt from {robots_url}: {e}")

        # Initialize rate limiting
        logger.info(f"Initializing rate limiting for domain '{domain}'. User RPS={user_rate_limit}, Robots Delay={robots_crawl_delay}")
        RateLimitedFetcher.init_rate_limiting(
            domain=domain,
            rate_limit=user_rate_limit,
            crawl_delay=robots_crawl_delay
        )

        return domain, robots_crawl_delay

    except Exception as e:
        logger.error(f"Error initializing rate limiting: {e}", exc_info=True)
        # Return default values
        return urlparse(url).netloc, None

def respect_rate_limit(domain: str):
    """
    Respect the rate limit for a domain by sleeping if necessary.

    Args:
        domain: The domain to respect rate limit for
    """
    # Use the RateLimitedFetcher's _apply_rate_limit method
    RateLimitedFetcher._apply_rate_limit(domain)
