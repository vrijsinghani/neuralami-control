"""
Playwright adapter for web scraping using an external Playwright service.
"""
import json
import logging
import requests
import re
import os
from typing import Dict, List, Any, Optional, Union
from urllib.parse import urlparse

from django.conf import settings
from .base import ScraperAdapter

logger = logging.getLogger(__name__)


class PlaywrightAdapter(ScraperAdapter):
    """Adapter for external Playwright web scraping service."""

    # Format mapping from internal formats to Playwright formats
    FORMAT_MAPPING = {
        'text': 'text',
        'html': 'html',
        'raw_html': 'raw_html',
        'links': 'links',
        'metadata': 'metadata',
        'screenshot': 'screenshot',
        'full': ['text', 'html', 'links', 'metadata', 'screenshot']
    }

    # Reverse mapping for response processing
    REVERSE_MAPPING = {
        'text': 'text',
        'html': 'html',
        'raw_html': 'raw_html',
        'links': 'links',
        'metadata': 'metadata',
        'screenshot': 'screenshot'
    }

    def __init__(self, api_url=None, api_key=None):
        """
        Initialize the Playwright adapter.

        Args:
            api_url: Playwright service API URL (defaults to settings.PLAYWRIGHT_API_URL)
            api_key: Playwright service API key (defaults to settings.PLAYWRIGHT_API_KEY)
        """
        self.api_url = api_url or getattr(settings, 'PLAYWRIGHT_API_URL', 'https://playwright-service.example.com/api')
        self.api_key = api_key or getattr(settings, 'PLAYWRIGHT_API_KEY', None)

    def get_supported_formats(self) -> List[str]:
        """Get the list of formats supported by Playwright."""
        return list(self.FORMAT_MAPPING.keys())

    def map_formats(self, formats: Union[str, List[str]]) -> List[str]:
        """Map internal format names to Playwright format names."""
        if isinstance(formats, str):
            # Handle comma-separated string
            formats = [fmt.strip() for fmt in formats.split(',')]

        # Ensure formats is a list
        if not isinstance(formats, list):
            formats = [formats]

        playwright_formats = []
        for fmt in formats:
            # Handle non-string formats
            if not isinstance(fmt, str):
                logger.warning(f"Non-string format: {fmt}, converting to string")
                fmt = str(fmt)

            # Strip whitespace if it's a string
            if isinstance(fmt, str):
                fmt = fmt.strip()

            if fmt in self.FORMAT_MAPPING:
                mapped_fmt = self.FORMAT_MAPPING[fmt]
                if isinstance(mapped_fmt, list):
                    playwright_formats.extend(mapped_fmt)
                else:
                    playwright_formats.append(mapped_fmt)
            else:
                logger.warning(f"Unknown format: {fmt}, ignoring")

        # Remove duplicates while preserving order
        return list(dict.fromkeys(playwright_formats))

    def _get_headers(self) -> Dict[str, str]:
        """Get headers for Playwright API request."""
        headers = {
            'Content-Type': 'application/json',
        }

        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
            logger.debug(f"Using API key: {self.api_key[:4]}...{self.api_key[-4:] if len(self.api_key) > 8 else ''}")
        else:
            logger.warning("No Playwright API key found. API calls may fail.")

        return headers

    def _clean_text(self, text: str) -> str:
        """
        Clean text content by removing non-breaking spaces and excessive whitespace.

        Args:
            text: The text to clean

        Returns:
            Cleaned text
        """
        if not text:
            return ""

        # Replace non-breaking space characters (Â, \xa0, etc.)
        cleaned = re.sub(r'\xa0|Â', ' ', text)

        # Replace multiple spaces with a single space
        cleaned = re.sub(r'\s+', ' ', cleaned)

        # Replace multiple newlines with a single newline
        cleaned = re.sub(r'\n+', '\n', cleaned)

        # Remove leading/trailing whitespace
        cleaned = cleaned.strip()

        return cleaned

    def _process_response(self, response_data: Dict[str, Any], requested_formats: List[str], url: str = None) -> Dict[str, Any]:
        """
        Process Playwright response and map it back to internal format names.

        Args:
            response_data: Playwright response data
            requested_formats: Original requested formats (internal names)

        Returns:
            Dictionary with internal format names as keys
        """
        if not response_data.get('success', False):
            error_msg = response_data.get('error', 'Unknown error')
            logger.error(f"Playwright scrape failed: {error_msg}")
            return {'error': error_msg}

        result = {}
        data = response_data.get('data', {})

        # Map Playwright response keys to internal format names
        for pw_key, internal_key in self.REVERSE_MAPPING.items():
            if pw_key in data and data[pw_key] is not None:
                # Clean text content if this is the text field
                if pw_key == 'text':
                    result[internal_key] = self._clean_text(data[pw_key])
                else:
                    result[internal_key] = data[pw_key]

        # Special handling for metadata
        if 'metadata' in data:
            metadata = data['metadata']

            # Ensure all required metadata fields are present
            # Standard metadata fields
            if 'url' not in metadata:
                metadata['url'] = url

            if 'domain' not in metadata:
                from urllib.parse import urlparse
                metadata['domain'] = urlparse(url).netloc

            # Ensure meta description is present
            if 'description' in metadata and 'meta_description' not in metadata:
                metadata['meta_description'] = metadata['description']

            # Ensure viewport is present
            if 'viewport' not in metadata and 'meta' in data and 'viewport' in data['meta']:
                metadata['viewport'] = data['meta']['viewport']

            # Ensure canonical is present
            if 'canonical' not in metadata and 'meta' in data and 'canonical' in data['meta']:
                metadata['canonical'] = data['meta']['canonical']

            # Ensure Open Graph metadata is present
            if 'og:title' in metadata and 'og_title' not in metadata:
                metadata['og_title'] = metadata['og:title']

            if 'og:description' in metadata and 'og_description' not in metadata:
                metadata['og_description'] = metadata['og:description']

            if 'og:image' in metadata and 'og_image' not in metadata:
                metadata['og_image'] = metadata['og:image']

            if 'og:type' in metadata and 'og_type' not in metadata:
                metadata['og_type'] = metadata['og:type']

            # Ensure Twitter Card metadata is present
            if 'twitter:card' in metadata and 'twitter_card' not in metadata:
                metadata['twitter_card'] = metadata['twitter:card']

            if 'twitter:title' in metadata and 'twitter_title' not in metadata:
                metadata['twitter_title'] = metadata['twitter:title']

            if 'twitter:description' in metadata and 'twitter_description' not in metadata:
                metadata['twitter_description'] = metadata['twitter:description']

            if 'twitter:image' in metadata and 'twitter_image' not in metadata:
                metadata['twitter_image'] = metadata['twitter:image']

            result['metadata'] = metadata

            # If title is in metadata, make sure it's also at the top level
            if 'title' in metadata and metadata['title']:
                result['title'] = metadata['title']

        # Check if we got all requested formats
        for fmt in requested_formats:
            if fmt not in result and fmt != 'full':
                logger.warning(f"Requested format '{fmt}' not found in Playwright response")

        return result

    def scrape(self,
               url: str,
               formats: Union[List[str], str] = None,
               timeout: int = 30000,
               wait_for: Optional[int] = None,
               css_selector: Optional[str] = None,
               headers: Optional[Dict[str, str]] = None,
               mobile: bool = False,
               stealth: bool = False,
               cache: bool = True,
               max_retries: int = 3,  # Add retry mechanism
               **kwargs) -> Dict[str, Any]:
        """
        Scrape a URL using Playwright and return the content in the requested formats.

        Args:
            url: The URL to scrape
            formats: List of formats to return (text, html, links, metadata, full)
            timeout: Timeout in milliseconds
            wait_for: Wait for element or time in milliseconds
            css_selector: CSS selector to extract content from
            headers: Custom headers to send with the request
            mobile: Whether to use mobile user agent
            stealth: Whether to use stealth mode
            cache: Whether to use cached results
            **kwargs: Additional Playwright-specific parameters

        Returns:
            Dictionary with the requested formats as keys and their content as values
        """
        # Handle default formats
        if formats is None:
            formats = ["text", "links"]

        # Map internal formats to Playwright formats
        logger.debug(f"Original formats: {formats}")

        # Remove duplicates while preserving order
        unique_formats = []
        for fmt in formats:
            if fmt not in unique_formats:
                unique_formats.append(fmt)

        # Map the formats
        playwright_formats = self.map_formats(unique_formats)
        logger.debug(f"Mapped formats: {playwright_formats}")

        # Build request payload
        payload = {
            "url": url,
            "formats": playwright_formats,
            "timeout": timeout,
            "cache": cache,
            "headers": {
                # Use a more common browser user agent
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0",
                # Add a referer to make it look like we're coming from Google
                "Referer": "https://www.google.com/"
            }
        }

        # Add optional parameters
        if wait_for:
            payload["waitFor"] = wait_for

        if css_selector:
            payload["selector"] = css_selector

        if mobile:
            payload["mobile"] = True

        if stealth:
            payload["stealth"] = True

        # Always enable JavaScript to handle potential Cloudflare challenges
        payload["javascript"] = True

        # Enable debug mode to get more information about the page
        payload["debug"] = True

        # Use a non-headless browser to avoid detection
        payload["headless"] = False

        # Add browser fingerprinting to make it look more like a real browser
        payload["browser"] = {
            "name": "chrome",
            "platform": "Windows",
            "version": "91.0.4472.124",
            "viewport": {
                "width": 1920,
                "height": 1080
            },
            "userAgent": payload["headers"]["User-Agent"]
        }

        # Add cookies to make it look like a returning visitor
        payload["cookies"] = [
            {
                "name": "visited",
                "value": "true",
                "domain": urlparse(url).netloc,
                "path": "/"
            }
        ]

        if headers:
            payload["headers"] = headers

        # Add any additional parameters
        for key, value in kwargs.items():
            if value is not None:
                # Convert snake_case to camelCase for API
                camel_key = ''.join(word.capitalize() if i > 0 else word
                                   for i, word in enumerate(key.split('_')))
                payload[camel_key] = value

        # Make the request
        #logger.info(f"Playwright scrape request for URL: {url} with payload: {json.dumps(payload)}")

        # Initialize retry counter
        retry_count = 0
        last_error = None

        while retry_count < max_retries:
            try:
                # Log detailed request information for debugging
                endpoint_url = f"{self.api_url}/scrape"
                headers = self._get_headers()

                #logger.debug(f"Making request to: {endpoint_url} (Attempt {retry_count + 1}/{max_retries})")
                #logger.debug(f"Headers: {headers}")
                #logger.debug(f"Payload: {json.dumps(payload, indent=2)}")

                response = requests.post(
                    endpoint_url,
                    headers=headers,
                    json=payload,
                    timeout=timeout/1000  # Convert to seconds for requests
                )

                # Log response information
                #logger.debug(f"Response status code: {response.status_code}")
                #logger.debug(f"Response headers: {response.headers}")

                try:
                    response_text = response.text
                    #logger.debug(f"Response text: {response_text}")
                except Exception as e:
                    logger.debug(f"Could not get response text: {str(e)}")

                # Check if the response is successful (2xx status code)
                if response.status_code >= 200 and response.status_code < 300:
                    response_data = response.json()

                    # Check if the Playwright service returned an error or if the response is empty
                    # Also check for social media domains that might block automated requests
                    social_media_domains = ['facebook.com', 'twitter.com', 'x.com', 'instagram.com', 'linkedin.com', 'tiktok.com', 'pinterest.com']
                    is_social_media = any(domain in urlparse(url).netloc for domain in social_media_domains)

                    # Use fallback for any of these conditions:
                    # 1. Response is not successful
                    # 2. Response data is empty
                    # 3. Response contains a 403 Forbidden message
                    # 4. URL is a social media domain
                    # 5. Any other error condition
                    should_use_fallback = (
                        not response_data.get('success', False) or
                        not response_data.get('data', {}) or
                        response_data.get('data', {}).get('text') == '403 Forbidden' or
                        is_social_media
                    )

                    if should_use_fallback:
                        if is_social_media:
                            logger.warning(f"URL is a social media domain that might block automated requests: {url}")
                        elif not response_data.get('success', False):
                            logger.warning(f"Playwright service failed for URL: {url} - Error: {response_data.get('error', 'Unknown error')}")
                        else:
                            logger.warning(f"Playwright service returned an error or empty response for URL: {url}")

                        # Immediately try RateLimitedFetcher as a fallback
                        logger.info(f"Immediately trying RateLimitedFetcher as a fallback: {url}")

                        try:
                            # Import here to avoid circular imports
                            from apps.agents.utils.rate_limited_fetcher import RateLimitedFetcher

                            # Use RateLimitedFetcher as a fallback
                            fetch_result = RateLimitedFetcher.fetch_url(url)

                            if fetch_result.get("success", False):
                                logger.info(f"Successfully fetched URL with RateLimitedFetcher: {url}")

                                # Create a result dictionary with the fetched content
                                fallback_result = {}

                                # Process all requested formats
                                from bs4 import BeautifulSoup
                                soup = BeautifulSoup(fetch_result.get("content", ""), "html.parser")

                                # Add text content if requested
                                if "text" in formats:
                                    # Extract text from HTML
                                    text_content = soup.get_text(separator=' ', strip=True)
                                    fallback_result["text"] = self._clean_text(text_content)

                                # Add HTML content if requested
                                if "html" in formats or "raw_html" in formats:
                                    fallback_result["html"] = fetch_result.get("content", "")
                                    if "raw_html" in formats:
                                        fallback_result["raw_html"] = fetch_result.get("content", "")

                                # Extract metadata if requested
                                if "metadata" in formats:
                                    metadata = {}

                                    # Extract title
                                    title_tag = soup.find("title")
                                    if title_tag:
                                        metadata["title"] = title_tag.text.strip()
                                        fallback_result["title"] = title_tag.text.strip()

                                    # Extract meta tags
                                    for meta in soup.find_all("meta"):
                                        if meta.get("name"):
                                            metadata[meta.get("name")] = meta.get("content", "")
                                        elif meta.get("property"):
                                            metadata[meta.get("property")] = meta.get("content", "")

                                    # Add standard metadata fields
                                    metadata["url"] = url
                                    metadata["domain"] = urlparse(url).netloc

                                    # Extract meta description
                                    meta_desc = soup.find("meta", attrs={"name": "description"})
                                    if meta_desc:
                                        metadata["meta_description"] = meta_desc.get("content", "")

                                    # Extract viewport
                                    viewport = soup.find("meta", attrs={"name": "viewport"})
                                    if viewport:
                                        metadata["viewport"] = viewport.get("content", "")

                                    # Extract robots
                                    robots = soup.find("meta", attrs={"name": "robots"})
                                    if robots:
                                        metadata["robots"] = robots.get("content", "")

                                    # Extract canonical
                                    canonical = soup.find("link", attrs={"rel": "canonical"})
                                    if canonical:
                                        metadata["canonical"] = canonical.get("href", "")

                                    # Add OpenGraph metadata
                                    og_title = soup.find("meta", property="og:title")
                                    if og_title:
                                        metadata["og_title"] = og_title.get("content", "")

                                    og_description = soup.find("meta", property="og:description")
                                    if og_description:
                                        metadata["og_description"] = og_description.get("content", "")

                                    og_image = soup.find("meta", property="og:image")
                                    if og_image:
                                        metadata["og_image"] = og_image.get("content", "")

                                    og_type = soup.find("meta", property="og:type")
                                    if og_type:
                                        metadata["og_type"] = og_type.get("content", "")

                                    # Add Twitter card metadata
                                    twitter_card = soup.find("meta", attrs={"name": "twitter:card"})
                                    if twitter_card:
                                        metadata["twitter_card"] = twitter_card.get("content", "")

                                    twitter_title = soup.find("meta", attrs={"name": "twitter:title"})
                                    if twitter_title:
                                        metadata["twitter_title"] = twitter_title.get("content", "")

                                    twitter_description = soup.find("meta", attrs={"name": "twitter:description"})
                                    if twitter_description:
                                        metadata["twitter_description"] = twitter_description.get("content", "")

                                    twitter_image = soup.find("meta", attrs={"name": "twitter:image"})
                                    if twitter_image:
                                        metadata["twitter_image"] = twitter_image.get("content", "")

                                    # Also check for property attributes for Twitter cards
                                    if not twitter_card:
                                        twitter_card = soup.find("meta", property="twitter:card")
                                        if twitter_card:
                                            metadata["twitter_card"] = twitter_card.get("content", "")

                                    if not twitter_title:
                                        twitter_title = soup.find("meta", property="twitter:title")
                                        if twitter_title:
                                            metadata["twitter_title"] = twitter_title.get("content", "")

                                    if not twitter_description:
                                        twitter_description = soup.find("meta", property="twitter:description")
                                        if twitter_description:
                                            metadata["twitter_description"] = twitter_description.get("content", "")

                                    if not twitter_image:
                                        twitter_image = soup.find("meta", property="twitter:image")
                                        if twitter_image:
                                            metadata["twitter_image"] = twitter_image.get("content", "")

                                    fallback_result["metadata"] = metadata

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
                                                base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}{os.path.dirname(urlparse(url).path)}/"
                                                href = f"{base_url}{href}"

                                            links.append({
                                                "href": href,
                                                "text": link.text.strip()
                                            })

                                    fallback_result["links"] = links

                                # Add screenshot placeholder if requested
                                if "screenshot" in formats:
                                    fallback_result["screenshot"] = "Screenshot not available in fallback mode"

                                # Add URL to the result
                                fallback_result["url"] = url

                                return fallback_result
                            else:
                                # If RateLimitedFetcher also fails, continue with the normal retry process
                                logger.warning(f"RateLimitedFetcher fallback failed for 403 error: {url}")
                                raise requests.exceptions.HTTPError("403 Forbidden response from website")
                        except Exception as fallback_error:
                            logger.error(f"Error using RateLimitedFetcher fallback for 403 error: {str(fallback_error)}")
                            raise requests.exceptions.HTTPError("403 Forbidden response from website")
                else:
                    # Raise exception for non-2xx status codes
                    response.raise_for_status()
                    response_data = response.json()

                logger.info(f"Successfully scraped URL with Playwright: {url}")

                # Process and return the response
                result = self._process_response(response_data, formats, url=url)

                # If we get here, the request was successful, so break out of the retry loop
                break

            except requests.exceptions.RequestException as e:
                retry_count += 1
                last_error = e
                logger.warning(f"Playwright request failed (attempt {retry_count}/{max_retries}): {str(e)}")

                if retry_count < max_retries:
                    # Check if this is a 403 error
                    is_403_error = False
                    if isinstance(last_error, requests.exceptions.HTTPError) and "403 Forbidden" in str(last_error):
                        is_403_error = True
                        logger.warning(f"Detected 403 Forbidden error, using special handling")

                    # Try different approaches on each retry
                    if is_403_error:
                        # Special handling for 403 errors
                        if retry_count == 1:
                            # First retry for 403: Try with a completely different browser profile
                            payload["headers"]["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                            payload["headers"]["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8"
                            payload["headers"]["Accept-Language"] = "en-US,en;q=0.9"
                            # Add cookies to bypass potential cookie checks
                            payload["cookies"] = [
                                {"name": "visited", "value": "true", "domain": urlparse(url).netloc, "path": "/"},
                                {"name": "cookieconsent_status", "value": "dismiss", "domain": urlparse(url).netloc, "path": "/"}
                            ]
                            # Use a different referer that looks like a search engine
                            payload["headers"]["Referer"] = "https://www.google.com/search?q=" + urlparse(url).netloc
                            # Disable headless mode
                            payload["headless"] = False
                            # Disable stealth mode (sometimes stealth mode is detected)
                            if "stealth" in payload:
                                del payload["stealth"]
                            logger.info(f"Retry {retry_count} for 403 error: Using different browser profile and cookies")
                        elif retry_count == 2:
                            # Second retry for 403: Try with mobile emulation and a different approach
                            payload["mobile"] = True
                            payload["headers"]["User-Agent"] = "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
                            # Add a delay before navigation to allow the page to fully load
                            payload["navigationDelay"] = 2000
                            # Add a wait for navigation to complete
                            payload["waitForNavigation"] = True
                            # Try to bypass Cloudflare by waiting for the page to load completely
                            payload["waitUntil"] = "networkidle"
                            logger.info(f"Retry {retry_count} for 403 error: Using mobile emulation with navigation delay")
                    else:
                        # Standard retry approach for non-403 errors
                        if retry_count == 1:
                            # First retry: Try with a different user agent
                            user_agents = [
                                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
                                "Mozilla/5.0 (X11; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0",
                                "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
                            ]
                            payload["headers"]["User-Agent"] = user_agents[0]
                            # Add a different referer
                            payload["headers"]["Referer"] = "https://www.bing.com/"
                            logger.info(f"Retry {retry_count}: Using different user agent and referer")
                        elif retry_count == 2:
                            # Second retry: Try with mobile emulation
                            payload["mobile"] = True
                            payload["headers"]["User-Agent"] = "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
                            # Remove headless mode
                            payload["headless"] = False
                            # Try without stealth mode
                            if "stealth" in payload:
                                del payload["stealth"]
                            logger.info(f"Retry {retry_count}: Using mobile emulation without stealth mode")

                    # Wait a bit before retrying
                    import time
                    time.sleep(1 * retry_count)  # Exponential backoff
                else:
                    # This was the last retry and it failed
                    logger.error(f"All {max_retries} Playwright requests failed for URL: {url}")

        # If we've exhausted all retries and still failed, try using RateLimitedFetcher as a fallback
        if retry_count >= max_retries and last_error is not None:
            logger.error(f"All {max_retries} Playwright requests failed for URL: {url}, last error: {str(last_error)}")
            logger.info(f"Trying RateLimitedFetcher as a fallback for URL: {url}")

            try:
                # Import here to avoid circular imports
                from apps.agents.utils.rate_limited_fetcher import RateLimitedFetcher

                # Use RateLimitedFetcher as a fallback
                fetch_result = RateLimitedFetcher.fetch_url(url)

                if fetch_result.get("success", False):
                    logger.info(f"Successfully fetched URL with RateLimitedFetcher: {url}")

                    # Create a result dictionary with the fetched content
                    result = {}

                    # Add text content if requested
                    if "text" in formats:
                        result["text"] = self._clean_text(fetch_result.get("content", ""))

                    # Add HTML content if requested
                    if "html" in formats:
                        result["html"] = fetch_result.get("content", "")

                    # Extract metadata if requested
                    if "metadata" in formats:
                        # Try to extract metadata from HTML
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(fetch_result.get("content", ""), "html.parser")

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

                    # Extract links if requested
                    if "links" in formats:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(fetch_result.get("content", ""), "html.parser")

                        links = []
                        for link in soup.find_all("a"):
                            href = link.get("href")
                            if href:
                                links.append({
                                    "href": href,
                                    "text": link.text.strip()
                                })

                        result["links"] = links

                    # Add URL to the result
                    result["url"] = url

                    return result
                else:
                    logger.error(f"RateLimitedFetcher fallback also failed for URL: {url}")
                    return {"error": f"Failed after {max_retries} retries with Playwright and RateLimitedFetcher fallback: {str(last_error)}"}
            except Exception as fallback_error:
                logger.error(f"Error using RateLimitedFetcher fallback: {str(fallback_error)}")
                return {"error": f"Failed after {max_retries} retries with Playwright and RateLimitedFetcher fallback: {str(last_error)}"}

        # Log the keys we got back if we have a result
        if 'result' in locals() and result:
            logger.debug(f"Successfully retrieved content with keys: {list(result.keys())}")
            return result

        # Fallback error if something unexpected happened
        logger.error(f"Unexpected error in Playwright scraping for URL: {url}")
        return {"error": "Unknown error"}
