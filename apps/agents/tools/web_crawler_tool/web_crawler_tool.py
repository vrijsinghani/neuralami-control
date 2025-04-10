"""
Web crawler tool for crawling websites.
This tool can use both sitemap-based and discovery-based crawling strategies.
"""
import logging
import json
import re
import time
from typing import Dict, List, Any, Optional, Union, Set, Type, Callable
from enum import Enum
from urllib.parse import urlparse, urljoin
from datetime import datetime

from pydantic import BaseModel, Field
from apps.agents.tools.base_tool import BaseTool
from apps.agents.utils.crawler_utils import init_crawler_rate_limiting, respect_rate_limit
from apps.agents.utils.scraper_adapters import get_adapter
from apps.agents.utils.scraper_adapters.playwright_adapter import PlaywrightAdapter
from apps.agents.tools.sitemap_retriever_tool.sitemap_retriever_tool import SitemapRetrieverTool

logger = logging.getLogger(__name__)

#
# Output Format Definitions
#
class CrawlOutputFormat(str, Enum):
    """Output formats for the web crawler."""
    TEXT = "text"
    HTML = "html"
    METADATA = "metadata"
    LINKS = "links"
    SCREENSHOT = "screenshot"
    FULL = "full"

class CrawlMode(str, Enum):
    """Crawl modes for the web crawler."""
    AUTO = "auto"
    SITEMAP = "sitemap"
    DISCOVERY = "discovery"

#
# Tool Schema
#
class WebCrawlerToolSchema(BaseModel):
    """Input schema for Web Crawler Tool."""
    start_url: str = Field(
        ...,
        description="The URL to start crawling from"
    )
    max_pages: int = Field(
        default=10,
        description="Maximum number of pages to crawl",
        gt=0
    )
    max_depth: int = Field(
        default=2,
        description="Maximum depth of links to follow",
        ge=0
    )
    output_format: str = Field(
        default="text",
        description="Format of the output (text, html, metadata, links, screenshot, full or comma-separated combination)"
    )
    include_patterns: Optional[List[str]] = Field(
        default=None,
        description="List of regex patterns to include URLs"
    )
    exclude_patterns: Optional[List[str]] = Field(
        default=None,
        description="List of regex patterns to exclude URLs"
    )
    stay_within_domain: bool = Field(
        default=True,
        description="Whether to stay within the same domain"
    )
    delay_seconds: float = Field(
        default=1.0,
        description="Delay between requests in seconds"
    )
    mode: CrawlMode = Field(
        default=CrawlMode.AUTO,
        description="Crawl mode (auto, sitemap, or discovery)"
    )
    respect_robots: bool = Field(
        default=True,
        description="Whether to respect robots.txt"
    )

#
# Base Crawler Classes
#
class CrawlerBase:
    """Base class for all crawlers with common functionality."""

    def __init__(self, respect_robots: bool = True, adapter_type: str = 'playwright'):
        """
        Initialize the crawler base.

        Args:
            respect_robots: Whether to respect robots.txt
            adapter_type: Type of adapter to use ('playwright', 'firecrawl', or 'firecrawl_crawl')
        """
        self.respect_robots = respect_robots
        self.adapter_type = adapter_type
        self.adapter = get_adapter(adapter_type)

        # Statistics for tracking fallbacks
        self.total_requests = 0
        self.fallback_count = 0
        self.consecutive_fallbacks = 0
        self.fallback_threshold = 3  # Switch adapters after this many fallbacks
        self.consecutive_threshold = 3  # Switch after this many consecutive fallbacks
        self.adapter_switched = False

    def init_rate_limiting(self, url: str, requests_per_second: float) -> tuple:
        """
        Initialize rate limiting based on robots.txt.

        Args:
            url: The URL to crawl
            requests_per_second: User-specified rate limit in requests per second

        Returns:
            Tuple of (domain, robots_crawl_delay)
        """
        if self.respect_robots:
            return init_crawler_rate_limiting(url, requests_per_second)
        else:
            # If not respecting robots.txt, just return the domain
            domain = urlparse(url).netloc
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain, None

    def apply_rate_limiting(self, domain: str):
        """
        Apply rate limiting for a domain.

        Args:
            domain: The domain to respect rate limit for
        """
        if self.respect_robots:
            respect_rate_limit(domain)

    def normalize_url(self, url: str) -> str:
        """
        Normalize a URL by removing trailing slashes and fragments.

        Args:
            url: The URL to normalize

        Returns:
            Normalized URL
        """
        parsed = urlparse(url)
        # Remove trailing slash
        path = parsed.path
        if path.endswith('/') and len(path) > 1:
            path = path[:-1]
        # Reconstruct URL without fragment
        normalized = f"{parsed.scheme}://{parsed.netloc}{path}"
        if parsed.query:
            normalized += f"?{parsed.query}"
        return normalized

    def extract_domain(self, url: str) -> str:
        """
        Extract and normalize the domain from a URL.

        Args:
            url: The URL to extract domain from

        Returns:
            Normalized domain
        """
        domain = urlparse(url).netloc
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain

    def is_same_domain(self, url1: str, url2: str) -> bool:
        """
        Check if two URLs have the same domain.

        Args:
            url1: First URL
            url2: Second URL

        Returns:
            True if the domains are the same, False otherwise
        """
        return self.extract_domain(url1) == self.extract_domain(url2)

    def fetch_content(self, url: str, formats: List[str], timeout: int = 30000, progress_callback=None) -> Dict[str, Any]:
        """
        Fetch content from a URL using the adapter.

        Args:
            url: The URL to fetch
            formats: List of content formats to fetch
            timeout: Timeout in milliseconds
            progress_callback: Optional callback to check for cancellation

        Returns:
            Dictionary with content in requested formats
        """
        try:
            # Check for cancellation if progress_callback is provided
            # But don't call the progress callback with a message to avoid double counting
            # Just check if the task has been cancelled by checking if progress_callback raises an exception
            if progress_callback:
                try:
                    # We don't actually call the progress_callback here anymore
                    # This is just a placeholder for future cancellation checking if needed
                    pass
                except Exception as e:
                    logger.warning(f"Task cancelled while fetching {url}: {str(e)}")
                    return {"error": "Task cancelled"}

            # Increment total requests counter
            self.total_requests += 1

            # Check if we should switch adapters based on fallback patterns
            if not self.adapter_switched:
                # Check for consecutive fallbacks first (fastest detection)
                if self.consecutive_fallbacks >= self.consecutive_threshold:
                    logger.warning(f"Switching to RateLimitedFetcher for all requests due to {self.consecutive_fallbacks} consecutive fallbacks")
                    self.adapter_switched = True
                # Then check overall fallback ratio if we have enough data
                elif self.total_requests >= 3 and self.fallback_count >= self.fallback_threshold:
                    fallback_ratio = self.fallback_count / self.total_requests

                    # If more than 50% of requests are falling back, switch to RateLimitedFetcher directly
                    if fallback_ratio >= 0.5:
                        logger.warning(f"Switching to RateLimitedFetcher for all requests due to high fallback ratio: {fallback_ratio:.2f} ({self.fallback_count}/{self.total_requests})")
                        self.adapter_switched = True
            # If we've decided to switch adapters, import and use RateLimitedFetcher
            if self.adapter_switched:
                # Import here to avoid circular imports
                from apps.agents.utils.rate_limited_fetcher import RateLimitedFetcher

                # Apply rate limiting
                domain = self.extract_domain(url)
                self.apply_rate_limiting(domain)

                # Use RateLimitedFetcher directly with retries
                fetch_result = RateLimitedFetcher.fetch_url(url, max_retries=3)

                if fetch_result.get("success", False):
                    # Process the result to match the expected format
                    result = self._process_rate_limited_result(fetch_result, formats, url)
                    return result
                else:
                    logger.error(f"RateLimitedFetcher failed for URL: {url}")
                    return {"error": fetch_result.get("error", "Unknown error")}

            # Apply rate limiting
            domain = self.extract_domain(url)
            self.apply_rate_limiting(domain)

            # Fetch content
            result = self.adapter.scrape(
                url=url,
                formats=formats,
                timeout=timeout,
                stealth=True
            )

            # Check if the result contains a fallback indicator
            if "_used_fallback" in result and result["_used_fallback"]:
                self.fallback_count += 1
                self.consecutive_fallbacks += 1
                logger.info(f"Fallback count increased to {self.fallback_count}/{self.total_requests} (consecutive: {self.consecutive_fallbacks})")
            else:
                # Reset consecutive fallbacks counter if this request didn't use a fallback
                self.consecutive_fallbacks = 0

            if "error" in result:
                logger.error(f"Error fetching URL {url}: {result['error']}")
                return {"error": result["error"]}

            return result
        except Exception as e:
            logger.error(f"Exception fetching URL {url}: {str(e)}")
            return {"error": str(e)}

    def _process_rate_limited_result(self, fetch_result: Dict[str, Any], formats: List[str], url: str) -> Dict[str, Any]:
        """
        Process the result from RateLimitedFetcher to match the format expected by the crawler.

        Args:
            fetch_result: Result from RateLimitedFetcher
            formats: List of requested formats
            url: The URL that was fetched

        Returns:
            Processed result in the expected format
        """
        result = {}
        result["_used_fallback"] = True  # Mark that this result used the fallback

        # Process content based on requested formats
        if fetch_result.get("content"):
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(fetch_result.get("content", ""), "html.parser")

            # Add text content if requested
            if "text" in formats:
                text_content = soup.get_text(separator=' ', strip=True)
                result["text"] = text_content

            # Add HTML content if requested
            if "html" in formats or "raw_html" in formats:
                result["html"] = fetch_result.get("content", "")
                if "raw_html" in formats:
                    result["raw_html"] = fetch_result.get("content", "")

            # Extract links if requested
            if "links" in formats:
                links = []
                for link in soup.find_all("a"):
                    href = link.get("href")
                    if href:
                        # Convert relative URLs to absolute
                        if href.startswith('/'):
                            base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
                            href = f"{base_url}{href}"
                        elif not href.startswith(('http://', 'https://', 'mailto:', 'tel:')):
                            # Handle relative URLs without leading slash
                            import os
                            base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}{os.path.dirname(urlparse(url).path)}/"
                            href = f"{base_url}{href}"

                        links.append({
                            "href": href,
                            "text": link.text.strip()
                        })
                result["links"] = links

            # Extract metadata if requested
            if "metadata" in formats:
                metadata = {}

                # Extract title
                title_tag = soup.find("title")
                if title_tag:
                    metadata["title"] = title_tag.text.strip()
                    result["title"] = title_tag.text.strip()

                # Extract meta tags
                for meta in soup.find_all("meta"):
                    if meta.get("name"):
                        metadata[meta.get("name")] = meta.get("content", "")
                    elif meta.get("property"):
                        metadata[meta.get("property")] = meta.get("content", "")

                result["metadata"] = metadata

            # Add placeholder for screenshot if requested
            if "screenshot" in formats:
                result["screenshot"] = "Screenshot not available in fallback mode"

        # Add URL to the result
        result["url"] = url

        return result

class CrawlStrategy:
    """Interface for crawling strategies."""

    def find_urls(self, start_url: str, max_urls: int) -> List[str]:
        """
        Find URLs to crawl.

        Args:
            start_url: The starting URL
            max_urls: Maximum number of URLs to find

        Returns:
            List of URLs to crawl
        """
        raise NotImplementedError

    def crawl(self, urls: List[str], formats: List[str], max_depth: int, **kwargs) -> Dict[str, Any]:
        """
        Crawl the given URLs.

        Args:
            urls: List of URLs to crawl
            formats: List of content formats to fetch
            max_depth: Maximum crawl depth
            **kwargs: Additional arguments

        Returns:
            Dictionary with crawl results
        """
        raise NotImplementedError

#
# Specific Crawl Strategies
#
class SitemapCrawlStrategy(CrawlStrategy, CrawlerBase):
    """Strategy for crawling websites using sitemaps."""

    def __init__(self, respect_robots: bool = True):
        """
        Initialize the sitemap crawl strategy.

        Args:
            respect_robots: Whether to respect robots.txt
        """
        CrawlerBase.__init__(self, respect_robots)
        self.sitemap_retriever = SitemapRetrieverTool()
        self.last_result = None  # Store the last result from the sitemap retriever

    def find_urls(self, start_url: str, max_urls: int, **kwargs) -> List[str]:
        """
        Find URLs to crawl from the sitemap.

        Args:
            start_url: The starting URL
            max_urls: Maximum number of URLs to find

        Returns:
            List of URLs to crawl
        """
        logger.info(f"Finding URLs from sitemap for {start_url} (max: {max_urls})")

        try:
            # Use SitemapRetrieverTool to find URLs
            sitemap_result = self.sitemap_retriever._run(
                url=start_url,
                user_id=1,  # Default user ID
                max_pages=max_urls,  # Maximum number of pages to retrieve
                requests_per_second=1.0  # Default RPS
            )

            # Store the result for later use
            self.last_result = sitemap_result

            # Parse the result
            parsed_result = None

            # Handle string result (JSON string)
            if isinstance(sitemap_result, str):
                try:
                    parsed_result = json.loads(sitemap_result)
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse sitemap result as JSON: {sitemap_result[:100]}...")
            # Handle dictionary result (already parsed)
            elif isinstance(sitemap_result, dict):
                parsed_result = sitemap_result

            # Extract URLs from the parsed result
            if parsed_result:
                urls = []

                # Extract URLs from the result
                if "urls" in parsed_result and isinstance(parsed_result["urls"], list):
                    # Handle list of URL strings
                    if len(parsed_result["urls"]) > 0 and isinstance(parsed_result["urls"][0], str):
                        urls = parsed_result["urls"]
                        logger.debug(f"Found {len(urls)} string URLs in sitemap result")
                    # Handle list of URL dictionaries
                    elif len(parsed_result["urls"]) > 0 and isinstance(parsed_result["urls"][0], dict):
                        # Extract 'loc' field from sitemap entries
                        extracted_urls = []
                        for item in parsed_result["urls"]:
                            if "loc" in item:
                                extracted_urls.append(item["loc"])
                            elif "url" in item:
                                extracted_urls.append(item["url"])
                        urls = extracted_urls
                        logger.debug(f"Found {len(urls)} dictionary URLs in sitemap result")
                elif "results" in parsed_result:
                    urls = [item.get("url") for item in parsed_result["results"] if "url" in item]
                    logger.debug(f"Found {len(urls)} URLs in 'results' field")

                # Log the first few URLs for debugging
                if urls:
                    logger.debug(f"First few URLs: {urls[:3]}")

                    # Apply include patterns if specified
                    include_patterns = kwargs.get("include_patterns")
                    if include_patterns:
                        logger.info(f"Filtering sitemap URLs with include patterns: {include_patterns}")
                        # Log the type of include_patterns to help debug
                        logger.info(f"Include patterns type: {type(include_patterns)}")
                        # Make sure include_patterns is a list
                        if isinstance(include_patterns, str):
                            include_patterns = [include_patterns]

                        # Convert glob patterns to regex patterns
                        def glob_to_regex(pattern):
                            # Replace * with .* for regex
                            if '*' in pattern:
                                # Escape dots in the pattern
                                pattern = pattern.replace('.', '\\.')
                                # Convert glob * to regex .*
                                pattern = pattern.replace('*', '.*')
                                # Make sure it matches anywhere in the URL
                                #logger.info(f"Converted glob pattern to regex: {pattern}")
                            return pattern

                        # Convert glob patterns to regex
                        regex_patterns = [glob_to_regex(pattern) for pattern in include_patterns]
                        logger.info(f"Using regex patterns: {regex_patterns}")

                        # Log each pattern and whether it matches any URLs
                        for pattern in regex_patterns:
                            matching_urls = [url for url in urls if re.search(pattern, url)]
                            logger.info(f"Pattern '{pattern}' matches {len(matching_urls)} URLs")
                            if len(matching_urls) > 0:
                                logger.info(f"Sample matches: {matching_urls[:3]}")

                        # Filter URLs that match any of the patterns
                        filtered_urls = [url for url in urls if any(re.search(pattern, url) for pattern in regex_patterns)]
                        logger.info(f"After filtering with include patterns: {len(filtered_urls)} URLs remain")
                        urls = filtered_urls

                    # Apply exclude patterns if specified
                    exclude_patterns = kwargs.get("exclude_patterns")
                    if exclude_patterns:
                        logger.info(f"Filtering sitemap URLs with exclude patterns: {exclude_patterns}")
                        # Make sure exclude_patterns is a list
                        if isinstance(exclude_patterns, str):
                            exclude_patterns = [exclude_patterns]

                        # Convert glob patterns to regex patterns
                        regex_exclude_patterns = [glob_to_regex(pattern) for pattern in exclude_patterns]
                        logger.info(f"Using regex exclude patterns: {regex_exclude_patterns}")

                        # Log each pattern and whether it matches any URLs
                        for pattern in regex_exclude_patterns:
                            matching_urls = [url for url in urls if re.search(pattern, url)]
                            logger.info(f"Exclude pattern '{pattern}' matches {len(matching_urls)} URLs")

                        # Filter URLs that don't match any of the patterns
                        filtered_urls = [url for url in urls if not any(re.search(pattern, url) for pattern in regex_exclude_patterns)]
                        logger.info(f"After filtering with exclude patterns: {len(filtered_urls)} URLs remain")
                        urls = filtered_urls

                    logger.info(f"Found {len(urls)} URLs in sitemap for {start_url} after filtering")
                    return urls[:max_urls]

            logger.warning(f"No URLs found in sitemap for {start_url}")
            return []
        except Exception as e:
            logger.error(f"Error finding URLs from sitemap for {start_url}: {str(e)}")
            return []

    def crawl(self, urls: List[str], formats: List[str], max_depth: int, **kwargs) -> Dict[str, Any]:
        """
        Crawl the given URLs found in the sitemap.

        Args:
            urls: List of URLs to crawl
            formats: List of content formats to fetch
            max_depth: Maximum crawl depth (not used in sitemap crawling)
            **kwargs: Additional arguments

        Returns:
            Dictionary with crawl results
        """
        logger.info(f"Crawling {len(urls)} URLs from sitemap with formats: {formats}")

        # Initialize rate limiting for the first URL (if any)
        if urls:
            domain, robots_crawl_delay = self.init_rate_limiting(urls[0], kwargs.get("requests_per_second", 1.0))
            logger.info(f"Initialized rate limiting for domain '{domain}'. Robots Delay={robots_crawl_delay}")

        # Crawl each URL
        results = []
        for i, url in enumerate(urls):
            logger.info(f"Crawling URL {i+1}/{len(urls)}: {url}")

            # Call progress callback if provided
            progress_callback = kwargs.get("progress_callback")
            if progress_callback:
                try:
                    # Use the actual number of URLs as the denominator
                    # This ensures consistent progress reporting with the SEO audit tool
                    progress_callback(i + 1, len(urls), url)
                except Exception as e:
                    logger.warning(f"Task cancelled or error in progress callback: {e}")
                    # Stop the entire crawl if the task has been cancelled
                    logger.info("Stopping crawl due to cancellation or error")
                    return {"status": "cancelled", "message": "Crawl was cancelled", "results": results}

            # Apply rate limiting before fetching
            domain = self.extract_domain(url)
            self.apply_rate_limiting(domain)

            # Fetch content with progress callback for cancellation checking
            result = self.fetch_content(url, formats, kwargs.get("timeout", 30000), progress_callback=progress_callback)

            # Add URL to result if not already present
            if "url" not in result:
                result["url"] = url

            # Add to results
            results.append(result)

        return {
            "results": results,
            "stats": {
                "total_urls": len(urls),
                "crawled_urls": len(results),
                "success_count": sum(1 for r in results if "error" not in r),
                "error_count": sum(1 for r in results if "error" in r)
            }
        }

class DiscoveryCrawlStrategy(CrawlStrategy, CrawlerBase):
    """Strategy for crawling websites by discovering links."""

    def __init__(self, respect_robots: bool = True):
        """
        Initialize the discovery crawl strategy.

        Args:
            respect_robots: Whether to respect robots.txt
        """
        CrawlerBase.__init__(self, respect_robots)

    def find_urls(self, start_url: str, max_urls: int) -> List[str]:
        """
        Find URLs to crawl by discovering links.

        Args:
            start_url: The starting URL
            max_urls: Maximum number of URLs to find

        Returns:
            List of URLs to crawl
        """
        logger.info(f"Finding URLs by discovery for {start_url} (max: {max_urls})")

        # For discovery strategy, we start with just the start URL
        # and discover more URLs during crawling
        return [start_url]

    def crawl(self, urls: List[str], formats: List[str], max_depth: int, **kwargs) -> Dict[str, Any]:
        """
        Crawl the given URLs and discover more URLs by following links.

        Args:
            urls: List of URLs to crawl
            formats: List of content formats to fetch
            max_depth: Maximum crawl depth
            **kwargs: Additional arguments

        Returns:
            Dictionary with crawl results
        """
        logger.info(f"Crawling with discovery strategy. Starting URLs: {len(urls)}, max_depth: {max_depth}")

        # Make sure "links" is in formats for discovery
        if "links" not in formats:
            formats = formats + ["links"]

        # Initialize variables
        visited_urls = set()
        urls_to_visit = [(url, 0) for url in urls]  # (url, depth)
        results = []
        max_pages = kwargs.get("max_pages", 10)
        start_domain = self.extract_domain(urls[0]) if urls else None

        # Initialize rate limiting
        if urls:
            domain, robots_crawl_delay = self.init_rate_limiting(urls[0], kwargs.get("requests_per_second", 1.0))
            logger.info(f"Initialized rate limiting for domain '{domain}'. Robots Delay={robots_crawl_delay}")

        # Crawl loop
        while urls_to_visit and len(visited_urls) < max_pages:
            # Get next URL to visit
            url, depth = urls_to_visit.pop(0)
            normalized_url = self.normalize_url(url)

            # Skip if already visited
            if normalized_url in visited_urls:
                continue

            # Mark as visited
            visited_urls.add(normalized_url)

            # Use the actual number of URLs to visit as the denominator for progress reporting
            # This ensures consistent progress reporting with the SEO audit tool
            total_urls_to_visit = min(max_pages, len(urls_to_visit) + len(visited_urls))
            logger.info(f"Crawling URL {len(visited_urls)}/{total_urls_to_visit} (depth {depth}): {url}")

            # Call progress callback if provided
            progress_callback = kwargs.get("progress_callback")
            if progress_callback:
                try:
                    progress_callback(len(visited_urls), total_urls_to_visit, url)
                except Exception as e:
                    logger.warning(f"Task cancelled or error in progress callback: {e}")
                    # Return immediately if the task has been cancelled
                    logger.info("Stopping crawl due to cancellation or error")
                    return {"status": "cancelled", "message": "Crawl was cancelled", "results": results}

            # Fetch content with progress callback for cancellation checking
            result = self.fetch_content(url, formats, kwargs.get("timeout", 30000), progress_callback=progress_callback)

            # Add URL to result if not already present
            if "url" not in result:
                result["url"] = url

            # Add to results
            results.append(result)

            # If we've reached max depth, don't extract more links
            if depth >= max_depth:
                continue

            # Extract links for further crawling
            if "links" in result and isinstance(result["links"], list):
                # Process links
                for link in result["links"]:
                    link_url = None

                    # Extract URL from link
                    if isinstance(link, dict) and "href" in link:
                        link_url = link["href"]
                    elif isinstance(link, str):
                        link_url = link

                    if not link_url:
                        continue

                    # Convert relative URLs to absolute
                    if not link_url.startswith(('http://', 'https://')):
                        link_url = urljoin(url, link_url)

                    # Skip non-HTTP(S) URLs
                    if not link_url.startswith(('http://', 'https://')):
                        continue

                    # Skip URLs from different domains if same_domain is True
                    if kwargs.get("same_domain", True) and not self.is_same_domain(link_url, url):
                        continue

                    # Apply include patterns if specified
                    include_patterns = kwargs.get("include_patterns")
                    if include_patterns:
                        # Make sure include_patterns is a list
                        if isinstance(include_patterns, str):
                            include_patterns = [include_patterns]

                        # Convert glob patterns to regex patterns
                        def glob_to_regex(pattern):
                            # Replace * with .* for regex
                            if '*' in pattern:
                                # Escape dots in the pattern
                                pattern = pattern.replace('.', '\\.')
                                # Convert glob * to regex .*
                                pattern = pattern.replace('*', '.*')
                                # Make sure it matches anywhere in the URL
                                logger.debug(f"Converted glob pattern to regex: {pattern}")
                            return pattern

                        # Convert glob patterns to regex
                        regex_patterns = [glob_to_regex(pattern) for pattern in include_patterns]

                        # Check if the URL matches any of the patterns
                        matches = False
                        for pattern in regex_patterns:
                            if re.search(pattern, link_url):
                                matches = True
                                #logger.debug(f"URL {link_url} matches pattern '{pattern}'")
                                break
                        if not matches:
                            logger.debug(f"Skipping URL {link_url} - does not match any include pattern")
                            continue

                    # Apply exclude patterns if specified
                    exclude_patterns = kwargs.get("exclude_patterns")
                    if exclude_patterns:
                        # Make sure exclude_patterns is a list
                        if isinstance(exclude_patterns, str):
                            exclude_patterns = [exclude_patterns]

                        # Convert glob patterns to regex patterns if not already done
                        # Reuse the glob_to_regex function defined above
                        regex_exclude_patterns = [glob_to_regex(pattern) for pattern in exclude_patterns]

                        # Check if the URL matches any of the exclude patterns
                        if any(re.search(pattern, link_url) for pattern in regex_exclude_patterns):
                            logger.debug(f"Skipping URL {link_url} - matches an exclude pattern")
                            continue

                    # Skip already visited or queued URLs
                    normalized_link = self.normalize_url(link_url)
                    if normalized_link in visited_urls or any(normalized_link == self.normalize_url(u) for u, _ in urls_to_visit):
                        continue

                    # Add to queue
                    urls_to_visit.append((link_url, depth + 1))

        return {
            "results": results,
            "stats": {
                "total_urls": len(visited_urls),
                "crawled_urls": len(results),
                "success_count": sum(1 for r in results if "error" not in r),
                "error_count": sum(1 for r in results if "error" in r)
            }
        }

#
# Unified Web Crawler
#
class UnifiedWebCrawler:
    """Unified web crawler that combines sitemap and discovery-based crawling."""

    def __init__(self, respect_robots: bool = True):
        """
        Initialize the unified web crawler.

        Args:
            respect_robots: Whether to respect robots.txt
        """
        self.sitemap_strategy = SitemapCrawlStrategy(respect_robots)
        self.discovery_strategy = DiscoveryCrawlStrategy(respect_robots)

    def crawl(self,
              start_url: str,
              mode: Union[str, CrawlMode] = CrawlMode.AUTO,
              max_pages: int = 10,
              max_depth: int = 1,
              formats: Optional[List[str]] = None,
              same_domain: bool = True,
              delay_seconds: float = 1.0,
              timeout: int = 30000,
              progress_callback: Optional[Callable[[int, int, str], None]] = None,
              **kwargs) -> Dict[str, Any]:
        """
        Crawl a website using the specified mode.

        Args:
            start_url: The starting URL
            mode: Crawl mode (auto, sitemap, or discovery)
            max_pages: Maximum number of pages to crawl
            max_depth: Maximum crawl depth
            formats: List of content formats to fetch
            same_domain: Whether to stay on the same domain
            delay_seconds: Delay between requests in seconds
            timeout: Timeout for each request in milliseconds
            **kwargs: Additional arguments

        Returns:
            Dictionary with crawl results
        """
        # Default formats
        if formats is None:
            formats = ["text", "links", "metadata"]

        # Convert string mode to enum
        if isinstance(mode, str):
            try:
                mode = CrawlMode(mode.lower())
            except ValueError:
                logger.warning(f"Invalid mode: {mode}. Using AUTO mode.")
                mode = CrawlMode.AUTO

        logger.info(f"Starting unified crawl for URL: {start_url}, mode: {mode}, max_pages: {max_pages}, max_depth: {max_depth}")

        # Common parameters for all strategies
        common_params = {
            "max_pages": max_pages,
            "requests_per_second": 1.0 / delay_seconds if delay_seconds > 0 else None,
            "timeout": timeout,
            "same_domain": same_domain,
            "progress_callback": progress_callback
        }

        # Add include_patterns and exclude_patterns if provided in kwargs
        if 'include_patterns' in kwargs and kwargs['include_patterns']:
            common_params['include_patterns'] = kwargs['include_patterns']
            logger.info(f"Using include patterns: {kwargs['include_patterns']}")

        if 'exclude_patterns' in kwargs and kwargs['exclude_patterns']:
            common_params['exclude_patterns'] = kwargs['exclude_patterns']
            logger.info(f"Using exclude patterns: {kwargs['exclude_patterns']}")

        start_time = time.time()

        if mode == CrawlMode.AUTO:
            # Try sitemap first
            logger.info(f"AUTO mode: Trying sitemap strategy first for {start_url}")
            urls = self.sitemap_strategy.find_urls(start_url, max_pages, **kwargs)

            # Check if the sitemap retriever found a crawl-delay in robots.txt
            robots_crawl_delay = None
            if hasattr(self.sitemap_strategy, 'last_result') and self.sitemap_strategy.last_result:
                robots_crawl_delay = self.sitemap_strategy.last_result.get('robots_crawl_delay_found')
                if robots_crawl_delay:
                    logger.info(f"Found crawl-delay in robots.txt: {robots_crawl_delay}s. Updating rate limiting.")
                    # Update the common_params with the robots crawl-delay
                    if robots_crawl_delay > delay_seconds:
                        common_params["requests_per_second"] = 1.0 / robots_crawl_delay
                        logger.info(f"Using stricter robots.txt crawl-delay: {robots_crawl_delay}s instead of user delay: {delay_seconds}s")

            if urls:
                # If we only found the base URL in the sitemap and we have include patterns,
                # use discovery mode to find additional pages that match the patterns
                if len(urls) == 1 and urls[0] == start_url and 'include_patterns' in kwargs and kwargs['include_patterns']:
                    logger.info(f"Only found base URL in sitemap with include patterns. Using discovery strategy to find matching pages.")
                    result = self.discovery_strategy.crawl([start_url], formats, max_depth, **common_params)
                    result["crawl_mode"] = "discovery (pattern matching)"
                else:
                    logger.info(f"Found {len(urls)} URLs in sitemap. Using sitemap strategy.")
                    # Update max_pages to match the actual number of URLs found in the sitemap
                    # This ensures consistent progress reporting
                    sitemap_params = common_params.copy()
                    sitemap_params["max_pages"] = len(urls)
                    result = self.sitemap_strategy.crawl(urls, formats, max_depth, **sitemap_params)
                    result["crawl_mode"] = "sitemap"
            else:
                logger.info(f"No URLs found in sitemap. Falling back to discovery strategy.")
                result = self.discovery_strategy.crawl([start_url], formats, max_depth, **common_params)
                result["crawl_mode"] = "discovery"

        elif mode == CrawlMode.SITEMAP:
            # Use sitemap only
            logger.info(f"SITEMAP mode: Using sitemap strategy for {start_url}")
            urls = self.sitemap_strategy.find_urls(start_url, max_pages, **kwargs)

            # Check if the sitemap retriever found a crawl-delay in robots.txt
            robots_crawl_delay = None
            if hasattr(self.sitemap_strategy, 'last_result') and self.sitemap_strategy.last_result:
                robots_crawl_delay = self.sitemap_strategy.last_result.get('robots_crawl_delay_found')
                if robots_crawl_delay:
                    logger.info(f"Found crawl-delay in robots.txt: {robots_crawl_delay}s. Updating rate limiting.")
                    # Update the common_params with the robots crawl-delay
                    if robots_crawl_delay > delay_seconds:
                        common_params["requests_per_second"] = 1.0 / robots_crawl_delay
                        logger.info(f"Using stricter robots.txt crawl-delay: {robots_crawl_delay}s instead of user delay: {delay_seconds}s")

            if urls:
                # Update max_pages to match the actual number of URLs found in the sitemap
                # This ensures consistent progress reporting
                sitemap_params = common_params.copy()
                sitemap_params["max_pages"] = len(urls)
                result = self.sitemap_strategy.crawl(urls, formats, max_depth, **sitemap_params)
                result["crawl_mode"] = "sitemap"
            else:
                logger.warning(f"No URLs found in sitemap for {start_url}")
                result = {
                    "error": "No sitemap found or sitemap is empty",
                    "crawl_mode": "sitemap",
                    "results": []
                }

        elif mode == CrawlMode.DISCOVERY:
            # Use discovery only
            logger.info(f"DISCOVERY mode: Using discovery strategy for {start_url}")

            # Try to get robots.txt crawl-delay using the sitemap retriever
            # This is a bit of a hack, but it allows us to respect robots.txt even in discovery mode
            try:
                sitemap_result = self.sitemap_strategy.sitemap_retriever._run(
                    url=start_url,
                    user_id=1,
                    max_pages=1,
                    requests_per_second=1.0
                )

                if isinstance(sitemap_result, dict) and 'robots_crawl_delay_found' in sitemap_result:
                    robots_crawl_delay = sitemap_result.get('robots_crawl_delay_found')
                    if robots_crawl_delay and robots_crawl_delay > delay_seconds:
                        logger.info(f"Found crawl-delay in robots.txt: {robots_crawl_delay}s. Updating rate limiting.")
                        common_params["requests_per_second"] = 1.0 / robots_crawl_delay
                        logger.info(f"Using stricter robots.txt crawl-delay: {robots_crawl_delay}s instead of user delay: {delay_seconds}s")
            except Exception as e:
                logger.warning(f"Error checking robots.txt in discovery mode: {str(e)}")

            result = self.discovery_strategy.crawl([start_url], formats, max_depth, **common_params)
            result["crawl_mode"] = "discovery"

        # Add timing information
        elapsed_time = time.time() - start_time
        result["elapsed_time"] = elapsed_time
        logger.info(f"Crawl completed in {elapsed_time:.2f} seconds. Mode: {result.get('crawl_mode')}")

        return result

#
# Web Crawler Tool
#
class WebCrawlerTool(BaseTool):
    """Tool for crawling websites."""
    name: str = "Web Crawler Tool"
    description: str = "Crawl a website and extract content from multiple pages"
    args_schema: Type[BaseModel] = WebCrawlerToolSchema

    def _run(
        self,
        start_url: str,
        max_pages: int = 10,
        max_depth: int = 2,
        output_format: Union[CrawlOutputFormat, str, List[str]] = CrawlOutputFormat.TEXT,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        stay_within_domain: bool = True,
        delay_seconds: float = 1.0,
        mode: str = "auto",
        respect_robots: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Run the web crawler tool.

        Args:
            start_url: The URL to start crawling from
            max_pages: Maximum number of pages to crawl
            max_depth: Maximum depth of links to follow
            output_format: Format of the output (text, html, metadata, links, screenshot, full)
            include_patterns: List of regex patterns to include URLs
            exclude_patterns: List of regex patterns to exclude URLs
            stay_within_domain: Whether to stay within the same domain
            delay_seconds: Delay between requests in seconds
            mode: Crawl mode (auto, sitemap, or discovery)
            respect_robots: Whether to respect robots.txt
            **kwargs: Additional arguments, including:
                progress_callback: Optional callback function for progress updates

        Returns:
            Dictionary with the crawl results
        """
        # Extract progress_callback from kwargs if present
        progress_callback = kwargs.pop('progress_callback', None)

        # Call the crawl_website function
        result = crawl_website(
            start_url=start_url,
            max_pages=max_pages,
            max_depth=max_depth,
            output_format=output_format,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            stay_within_domain=stay_within_domain,
            delay_seconds=delay_seconds,
            mode=mode,
            respect_robots=respect_robots,
            progress_callback=progress_callback,
            **kwargs
        )

        return result

#
# Main Function
#
def crawl_website(
    start_url: str,
    max_pages: int = 10,
    max_depth: int = 2,
    output_format: Union[CrawlOutputFormat, str, List[str]] = CrawlOutputFormat.TEXT,
    include_patterns: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None,
    stay_within_domain: bool = True,
    delay_seconds: float = 1.0,
    mode: str = "auto",
    respect_robots: bool = True,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Crawl a website starting from the given URL and extract content from multiple pages.

    Args:
        start_url: The URL to start crawling from
        max_pages: Maximum number of pages to crawl
        max_depth: Maximum depth of links to follow
        output_format: Format of the output (text, html, metadata, links, screenshot, full)
        include_patterns: List of regex patterns to include URLs
        exclude_patterns: List of regex patterns to exclude URLs
        stay_within_domain: Whether to stay within the same domain
        delay_seconds: Delay between requests in seconds
        mode: Crawl mode (auto, sitemap, or discovery)
        respect_robots: Whether to respect robots.txt
        **kwargs: Additional arguments

    Returns:
        Dictionary with the crawl results
    """
    logger.info(f"Starting crawl for URL: {start_url}, max_pages: {max_pages}, max_depth: {max_depth}, delay: {delay_seconds}s, mode: {mode}")

    # Normalize output_format to list
    formats = []
    if isinstance(output_format, str):
        if ',' in output_format:
            formats = [fmt.strip() for fmt in output_format.split(',')]
        else:
            formats = [output_format]
    elif isinstance(output_format, list):
        formats = output_format
    elif isinstance(output_format, CrawlOutputFormat):
        formats = [output_format.value]
    else:
        # Default to text only if no format is specified
        formats = ["text"]

    # Validate formats
    valid_formats = [fmt.value for fmt in CrawlOutputFormat]
    formats = [fmt for fmt in formats if fmt in valid_formats or fmt in valid_formats]

    if not formats:
        # Default to text only if no valid format is found
        formats = ["text"]

    logger.debug(f"Using formats: {formats}")

    # Process include/exclude patterns
    # Convert comma-separated strings to lists if needed
    if include_patterns and isinstance(include_patterns, str):
        include_patterns = [pattern.strip() for pattern in include_patterns.split(',')]
        logger.info(f"Converted include_patterns string to list: {include_patterns}")

    if exclude_patterns and isinstance(exclude_patterns, str):
        exclude_patterns = [pattern.strip() for pattern in exclude_patterns.split(',')]
        logger.info(f"Converted exclude_patterns string to list: {exclude_patterns}")

    # Convert glob patterns to regex patterns
    def glob_to_regex(pattern):
        # Replace * with .* for regex
        if '*' in pattern:
            # Escape dots in the pattern
            pattern = pattern.replace('.', '\\.')
            # Convert glob * to regex .*
            pattern = pattern.replace('*', '.*')
            # Make sure it's a full match pattern
            if not pattern.startswith('^'):
                pattern = f".*{pattern}"
            if not pattern.endswith('$'):
                pattern = f"{pattern}.*"
            #logger.info(f"Converted glob pattern to regex: {pattern}")
        return pattern

    # Compile regex patterns
    compiled_include = None
    compiled_exclude = None

    if include_patterns:
        try:
            # Convert glob patterns to regex
            regex_include_patterns = [glob_to_regex(pattern) for pattern in include_patterns]
            compiled_include = [re.compile(pattern) for pattern in regex_include_patterns]
            logger.info(f"Compiled include patterns: {regex_include_patterns}")
        except re.error as e:
            logger.error(f"Invalid include pattern: {e}")

    if exclude_patterns:
        try:
            # Convert glob patterns to regex
            regex_exclude_patterns = [glob_to_regex(pattern) for pattern in exclude_patterns]
            compiled_exclude = [re.compile(pattern) for pattern in regex_exclude_patterns]
            logger.info(f"Compiled exclude patterns: {regex_exclude_patterns}")
        except re.error as e:
            logger.error(f"Invalid exclude pattern: {e}")

    # Use the unified crawler
    crawler = UnifiedWebCrawler(respect_robots=respect_robots)
    result = crawler.crawl(
        start_url=start_url,
        mode=mode,
        max_pages=max_pages,
        max_depth=max_depth,
        formats=formats,
        same_domain=stay_within_domain,
        delay_seconds=delay_seconds,
        timeout=kwargs.get("timeout", 60000),
        progress_callback=progress_callback,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns
    )

    # Apply include/exclude patterns to results if needed
    if compiled_include or compiled_exclude:
        filtered_results = []
        for i, item in enumerate(result.get("results", [])):
            url = item.get("url", "")

            # Apply include/exclude patterns
            if compiled_include and not any(pattern.search(url) for pattern in compiled_include):
                continue

            if compiled_exclude and any(pattern.search(url) for pattern in compiled_exclude):
                continue

            filtered_results.append(item)

            # Call progress callback for filtering progress
            if progress_callback:
                try:
                    progress_callback(i + 1, len(result.get("results", [])), f"Filtering: {url}")
                except Exception as e:
                    logger.error(f"Error in progress callback during filtering: {e}")

        # Update the results
        result["results"] = filtered_results

        # Update stats
        result["stats"] = {
            "total_urls": len(filtered_results),
            "crawled_urls": len(filtered_results),
            "success_count": sum(1 for r in filtered_results if "error" not in r),
            "error_count": sum(1 for r in filtered_results if "error" in r)
        }

    logger.info(f"Completed crawl with {len(result.get('results', []))} pages")

    return result
