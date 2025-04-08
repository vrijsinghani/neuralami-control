"""
FireCrawl Crawl adapter for web crawling.
"""
import json
import logging
import requests
import time
from typing import Dict, List, Any, Optional, Union

from django.conf import settings
from .base import ScraperAdapter

logger = logging.getLogger(__name__)


class FireCrawlCrawlAdapter(ScraperAdapter):
    """Adapter for FireCrawl web crawling service using the /crawl endpoint."""

    # Format mapping from internal formats to FireCrawl formats
    FORMAT_MAPPING = {
        'text': 'markdown',
        'html': 'html',
        'raw_html': 'rawHtml',
        'links': 'links',
        'metadata': 'metadata',
        'screenshot': 'screenshot',
        'full': ['markdown', 'html', 'links', 'metadata']
    }

    # Reverse mapping for response processing
    REVERSE_MAPPING = {
        'markdown': 'text',
        'html': 'html',
        'rawHtml': 'raw_html',
        'links': 'links',
        'metadata': 'metadata',
        'screenshot': 'screenshot'
    }

    def __init__(self, api_url=None, api_key=None):
        """
        Initialize the FireCrawl Crawl adapter.

        Args:
            api_url: FireCrawl API URL (defaults to settings.FIRECRAWL_URL)
            api_key: FireCrawl API key (defaults to settings.FIRECRAWL_API_KEY)
        """
        # Use the same URL construction as the original implementation
        self.api_url = getattr(settings, 'FIRECRAWL_URL', 'https://firecrawl.neuralami.ai')
        self.api_key = getattr(settings, 'FIRECRAWL_API_KEY', None)

    def get_supported_formats(self) -> List[str]:
        """Get the list of formats supported by FireCrawl."""
        return list(self.FORMAT_MAPPING.keys())

    def map_formats(self, formats: Union[str, List[str]]) -> List[str]:
        """Map internal format names to FireCrawl format names."""
        if isinstance(formats, str):
            # Handle comma-separated string
            formats = [fmt.strip() for fmt in formats.split(',')]

        firecrawl_formats = []
        for fmt in formats:
            if fmt in self.FORMAT_MAPPING:
                mapped_fmt = self.FORMAT_MAPPING[fmt]
                if isinstance(mapped_fmt, list):
                    firecrawl_formats.extend(mapped_fmt)
                else:
                    firecrawl_formats.append(mapped_fmt)
            else:
                logger.warning(f"Unknown format: {fmt}, ignoring")

        # Remove duplicates while preserving order
        return list(dict.fromkeys(firecrawl_formats))

    def _get_headers(self) -> Dict[str, str]:
        """Get headers for FireCrawl API request."""
        headers = {
            'Content-Type': 'application/json',
        }

        # The original implementation wasn't adding the API key to the headers
        # So we'll do the same here for compatibility

        return headers

    def _process_response(self, response_data: Dict[str, Any], requested_formats: List[str]) -> Dict[str, Any]:
        """
        Process FireCrawl response and map it back to internal format names.

        Args:
            response_data: FireCrawl response data
            requested_formats: Original requested formats (internal names)

        Returns:
            Dictionary with internal format names as keys
        """
        if not response_data.get('success', False):
            error_msg = response_data.get('error', 'Unknown error')
            logger.error(f"FireCrawl crawl failed: {error_msg}")
            return {'error': error_msg}

        result = {}

        # For crawl endpoint, the data is a list of pages
        pages_data = response_data.get('data', [])

        # Combine all pages into a single result
        for page in pages_data:
            url = page.get('url', '')

            # Skip if no URL
            if not url:
                continue

            # Create page entry if it doesn't exist
            if url not in result:
                result[url] = {}

            # Map FireCrawl response keys to internal format names
            for fc_key, internal_key in self.REVERSE_MAPPING.items():
                if fc_key in page and page[fc_key] is not None:
                    result[url][internal_key] = page[fc_key]

            # Special handling for metadata
            if 'metadata' in page:
                result[url]['metadata'] = page['metadata']

        return result

    def scrape(self,
               url: str,
               formats: List[str],
               timeout: int = 30000,
               wait_for: Optional[int] = None,
               css_selector: Optional[str] = None,
               headers: Optional[Dict[str, str]] = None,
               mobile: bool = False,
               stealth: bool = False,
               cache: bool = True,
               max_pages: int = 100,
               max_depth: int = 3,
               include_patterns: Optional[List[str]] = None,
               exclude_patterns: Optional[List[str]] = None,
               stay_within_domain: bool = True,
               **kwargs) -> Dict[str, Any]:
        """
        Crawl a website using FireCrawl and return the content in the requested formats.

        Args:
            url: The URL to crawl
            formats: List of formats to return (text, html, links, metadata, full)
            timeout: Timeout in milliseconds
            wait_for: Wait for element or time in milliseconds
            css_selector: CSS selector to extract content from
            headers: Custom headers to send with the request
            mobile: Whether to use mobile user agent
            stealth: Whether to use stealth mode
            cache: Whether to use cached results
            max_pages: Maximum number of pages to crawl
            max_depth: Maximum depth to crawl
            include_patterns: URL patterns to include in crawl
            exclude_patterns: URL patterns to exclude from crawl
            stay_within_domain: Whether to stay within the domain
            **kwargs: Additional FireCrawl-specific parameters

        Returns:
            Dictionary with the requested formats as keys and their content as values
        """
        # Map internal formats to FireCrawl formats
        firecrawl_formats = self.map_formats(formats)

        # Build request payload to match the original implementation
        payload = {
            "url": url,
            "limit": max_pages,
            "scrapeOptions": {
                "formats": firecrawl_formats
            }
        }

        # Add maxDepth if provided
        if max_depth > 0:
            payload["maxDepth"] = max_depth

        # Enable backward links to improve coverage (gets pages that aren't direct children)
        payload["allowBackwardLinks"] = True

        # Only stay on the same domain by default
        payload["allowExternalLinks"] = not stay_within_domain

        # Add optional parameters
        if wait_for:
            payload["scrapeOptions"]["waitFor"] = wait_for

        if css_selector:
            payload["scrapeOptions"]["includeTags"] = [css_selector]

        if mobile:
            payload["scrapeOptions"]["mobile"] = True

        # Handle stealth mode - in /crawl it might be a top-level parameter
        if stealth:
            # Try both locations to be safe
            payload["scrapeOptions"]["proxy"] = "stealth"

        if headers:
            payload["scrapeOptions"]["headers"] = headers

        # Add include/exclude patterns
        if include_patterns:
            payload["includePaths"] = include_patterns
        else:
            # Default to include all paths
            payload["includePaths"] = ["/.*"]

        if exclude_patterns:
            payload["excludePaths"] = exclude_patterns

        # We already set allowExternalLinks above, so no need to set it again

        # Add any additional parameters
        for key, value in kwargs.items():
            if value is not None:
                # Convert snake_case to camelCase for FireCrawl API
                camel_key = ''.join(word.capitalize() if i > 0 else word
                                   for i, word in enumerate(key.split('_')))
                payload[camel_key] = value

        # Make the request
        logger.info(f"FireCrawl crawl request for URL: {url} with payload: {json.dumps(payload)}")

        try:
            # Submit crawl task using the same URL construction as the original implementation
            endpoint_url = f"{self.api_url}/v1/crawl"
            headers = self._get_headers()

            # Log detailed request information for debugging
            logger.debug(f"Making request to: {endpoint_url}")
            logger.debug(f"Headers: {headers}")
            logger.debug(f"Payload: {json.dumps(payload, indent=2)}")

            response = requests.post(
                endpoint_url,
                headers=headers,
                json=payload,
                timeout=timeout/1000  # Convert to seconds for requests
            )

            # Log response information
            logger.debug(f"Response status code: {response.status_code}")
            logger.debug(f"Response headers: {response.headers}")

            try:
                response_text = response.text
                logger.debug(f"Response text: {response_text}")
            except Exception as e:
                logger.debug(f"Could not get response text: {str(e)}")

            # Raise exception for non-2xx status codes
            response.raise_for_status()
            task_data = response.json()

            if not task_data.get("success"):
                error_message = f"Failed to submit crawl task: {task_data.get('error', 'Unknown error')}"
                logger.error(error_message)
                return {"error": error_message}

            crawl_task_id = task_data.get("id")
            crawl_task_url = task_data.get("url")

            logger.info(f"Crawl task submitted, ID: {crawl_task_id}")

            # Poll for results
            polling_timeout = 1620  # seconds
            start_time = time.time()
            polling_interval = 5  # seconds between status checks

            # Poll for results of crawl
            while True:
                if time.time() - start_time > polling_timeout:
                    return {"error": f"Task {crawl_task_id} timed out after {polling_timeout} seconds"}

                result_response = requests.get(
                    crawl_task_url,
                    headers=self._get_headers()
                )
                result_response.raise_for_status()
                status = result_response.json()

                # Log status information for debugging
                logger.info(f"Crawl status: {status.get('status', 'unknown')}, Total: {status.get('total', 0)}, Completed: {status.get('completed', 0)}")

                # Check if crawl is complete
                if status.get("status") == "completed":
                    logger.info(f"Crawl completed: {crawl_task_id}")

                    # Process and return the response
                    result = self._process_response(status, formats)

                    # Log the keys we got back
                    logger.debug(f"Successfully retrieved content for {len(result)} pages")

                    return result

                # Check if crawl failed
                if status.get("status") == "failed":
                    error_message = f"Crawl failed: {status.get('error', 'Unknown error')}"
                    logger.error(error_message)
                    return {"error": error_message}

                # Wait before checking again
                time.sleep(polling_interval)

        except requests.exceptions.RequestException as e:
            logger.error(f"Error crawling URL with FireCrawl: {url}, error: {str(e)}")
            return {"error": str(e)}
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding FireCrawl response: {str(e)}")
            return {"error": f"Invalid JSON response: {str(e)}"}
        except Exception as e:
            logger.error(f"Unexpected error crawling URL with FireCrawl: {url}, error: {str(e)}")
            return {"error": str(e)}
