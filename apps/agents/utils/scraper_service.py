"""
Scraper service for web scraping.
"""
import logging
from typing import Dict, List, Any, Optional, Union, Type

from django.conf import settings
from .scraper_adapters import ScraperAdapter, FireCrawlAdapter, FireCrawlCrawlAdapter, PlaywrightAdapter

logger = logging.getLogger(__name__)


class ScraperService:
    """
    Service for web scraping using different adapters.
    """

    # Default adapter to use if not specified
    DEFAULT_ADAPTER = 'firecrawl'

    # Map of adapter names to adapter classes
    ADAPTERS = {
        'firecrawl': FireCrawlAdapter,
        'firecrawl_crawl': FireCrawlCrawlAdapter,
        'playwright': PlaywrightAdapter,
    }

    def __init__(self, adapter_name=None):
        """
        Initialize the scraper service.

        Args:
            adapter_name: Name of the adapter to use (defaults to settings.DEFAULT_SCRAPER_ADAPTER or 'firecrawl')
        """
        self.adapter_name = adapter_name or getattr(settings, 'DEFAULT_SCRAPER_ADAPTER', self.DEFAULT_ADAPTER)
        self.adapter = self._get_adapter(self.adapter_name)

    def _get_adapter(self, adapter_name: str) -> ScraperAdapter:
        """
        Get an instance of the specified adapter.

        Args:
            adapter_name: Name of the adapter to use

        Returns:
            Instance of the adapter

        Raises:
            ValueError: If the adapter is not found
        """
        adapter_class = self.ADAPTERS.get(adapter_name.lower())
        if not adapter_class:
            raise ValueError(f"Unknown scraper adapter: {adapter_name}")

        return adapter_class()

    def register_adapter(self, name: str, adapter_class: Type[ScraperAdapter]):
        """
        Register a new adapter.

        Args:
            name: Name of the adapter
            adapter_class: Adapter class
        """
        self.ADAPTERS[name.lower()] = adapter_class

    def get_supported_formats(self) -> List[str]:
        """
        Get the list of formats supported by the current adapter.

        Returns:
            List of supported format names
        """
        return self.adapter.get_supported_formats()

    def scrape(self,
               url: str,
               output_types: Union[str, List[str]],
               timeout: int = 30000,
               wait_for: Optional[int] = None,
               css_selector: Optional[str] = None,
               headers: Optional[Dict[str, str]] = None,
               mobile: bool = False,
               stealth: bool = False,
               cache: bool = True,
               adapter_name: Optional[str] = None,
               **kwargs) -> Dict[str, Any]:
        """
        Scrape a URL and return the content in the requested formats.

        Args:
            url: The URL to scrape
            output_types: List of formats to return or comma-separated string
                         (text, html, links, metadata, full)
            timeout: Timeout in milliseconds
            wait_for: Wait for element or time in milliseconds
            css_selector: CSS selector to extract content from
            headers: Custom headers to send with the request
            mobile: Whether to use mobile user agent
            stealth: Whether to use stealth mode
            adapter_name: Name of the adapter to use (overrides the default)
            **kwargs: Additional provider-specific parameters

        Returns:
            Dictionary with the requested formats as keys and their content as values
        """
        # Use specified adapter if provided
        adapter = self._get_adapter(adapter_name) if adapter_name else self.adapter

        # Normalize output_types to a list
        if isinstance(output_types, str):
            if ',' in output_types:
                formats = [fmt.strip() for fmt in output_types.split(',')]
            else:
                formats = [output_types]
        else:
            formats = output_types

        # Validate formats
        supported_formats = adapter.get_supported_formats()
        for fmt in formats:
            if fmt not in supported_formats:
                logger.warning(f"Format '{fmt}' not supported by adapter '{adapter_name or self.adapter_name}', ignoring")

        # Filter to only supported formats
        valid_formats = [fmt for fmt in formats if fmt in supported_formats]

        if not valid_formats:
            logger.error(f"No valid formats specified. Supported formats: {supported_formats}")
            return {"error": f"No valid formats specified. Supported formats: {supported_formats}"}

        # Scrape the URL
        return adapter.scrape(
            url=url,
            formats=valid_formats,
            timeout=timeout,
            wait_for=wait_for,
            css_selector=css_selector,
            headers=headers,
            mobile=mobile,
            stealth=stealth,
            cache=cache,
            **kwargs
        )
