"""
FireCrawl adapter for web scraping.
"""
import json
import logging
import requests
from typing import Dict, List, Any, Optional, Union

from django.conf import settings
from .base import ScraperAdapter

logger = logging.getLogger(__name__)


class FireCrawlAdapter(ScraperAdapter):
    """Adapter for FireCrawl web scraping service."""

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
        Initialize the FireCrawl adapter.

        Args:
            api_url: FireCrawl API URL (defaults to settings.FIRECRAWL_URL)
            api_key: FireCrawl API key (defaults to settings.FIRECRAWL_API_KEY)
        """
        # Use the same URL construction as the original implementation
        self.api_url = getattr(settings, 'FIRECRAWL_URL', 'https://firecrawl.neuralami.ai')

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
            logger.error(f"FireCrawl scrape failed: {error_msg}")
            return {'error': error_msg}

        result = {}
        data = response_data.get('data', {})

        # Map FireCrawl response keys to internal format names
        for fc_key, internal_key in self.REVERSE_MAPPING.items():
            if fc_key in data and data[fc_key] is not None:
                result[internal_key] = data[fc_key]

        # Special handling for metadata
        if 'metadata' in data:
            result['metadata'] = data['metadata']

        # Check if we got all requested formats
        for fmt in requested_formats:
            if fmt not in result and fmt != 'full':
                logger.warning(f"Requested format '{fmt}' not found in FireCrawl response")

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
               **kwargs) -> Dict[str, Any]:
        """
        Scrape a URL using FireCrawl and return the content in the requested formats.

        Args:
            url: The URL to scrape
            formats: List of formats to return (text, html, links, metadata, full)
            timeout: Timeout in milliseconds
            wait_for: Wait for element or time in milliseconds
            css_selector: CSS selector to extract content from
            headers: Custom headers to send with the request
            mobile: Whether to use mobile user agent
            stealth: Whether to use stealth mode
            **kwargs: Additional FireCrawl-specific parameters

        Returns:
            Dictionary with the requested formats as keys and their content as values
        """
        # Map internal formats to FireCrawl formats
        firecrawl_formats = self.map_formats(formats)

        # Build request payload
        payload = {
            "url": url,
            "formats": firecrawl_formats,
            "timeout": timeout
            # FireCrawl v1 API doesn't support the 'cache' parameter
        }

        # Add optional parameters
        if wait_for:
            payload["waitFor"] = wait_for

        if css_selector:
            payload["includeTags"] = [css_selector]

        if mobile:
            payload["mobile"] = True

        if stealth:
            payload["proxy"] = "stealth"

        if headers:
            payload["headers"] = headers

        # Add any additional parameters
        for key, value in kwargs.items():
            if value is not None:
                # Convert snake_case to camelCase for FireCrawl API
                camel_key = ''.join(word.capitalize() if i > 0 else word
                                   for i, word in enumerate(key.split('_')))
                payload[camel_key] = value

        # Make the request
        logger.info(f"FireCrawl scrape request for URL: {url} with payload: {json.dumps(payload)}")

        try:
            # Submit scrape task using the same URL construction as the original implementation
            endpoint_url = f"{self.api_url}/v1/scrape"
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
            response_data = response.json()

            logger.info(f"Successfully scraped URL with FireCrawl: {url}")

            # Process and return the response
            result = self._process_response(response_data, formats)

            # Log the keys we got back
            logger.debug(f"Successfully retrieved content with keys: {list(result.keys())}")

            return result

        except requests.exceptions.RequestException as e:
            logger.error(f"Error scraping URL with FireCrawl: {url}, error: {str(e)}")
            return {"error": str(e)}
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding FireCrawl response: {str(e)}")
            return {"error": f"Invalid JSON response: {str(e)}"}
        except Exception as e:
            logger.error(f"Unexpected error scraping URL with FireCrawl: {url}, error: {str(e)}")
            return {"error": str(e)}
