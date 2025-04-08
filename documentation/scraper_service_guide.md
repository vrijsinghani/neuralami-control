# Scraper Service Architecture Guide

## Overview

The Scraper Service is a flexible architecture for web scraping that allows you to:

1. Request any combination of output formats (text, HTML, links, metadata, etc.)
2. Easily switch between different crawling engines through adapters
3. Map internal format types to provider-specific formats

This document explains how to use the Scraper Service and how to extend it with new adapters.

## Architecture

```
┌─────────────────┐     ┌───────────────────┐     ┌───────────────────────┐
│                 │     │                   │     │                       │
│  Web Crawler    │────▶│  Scraper Service  │────▶│  Scraper Adapter      │
│                 │     │                   │     │  (FireCrawl, etc.)    │
└─────────────────┘     └───────────────────┘     └───────────────────────┘
```

### Components

1. **ScraperAdapter Interface** (`apps/agents/utils/scraper_adapters/base.py`):
   - Defines the common interface for all scraper adapters
   - Methods for scraping, format mapping, and supported formats

2. **FireCrawlAdapter** (`apps/agents/utils/scraper_adapters/firecrawl_adapter.py`):
   - Implementation for FireCrawl's `/scrape` endpoint
   - Maps internal formats to FireCrawl formats
   - Handles FireCrawl-specific parameters

3. **FireCrawlCrawlAdapter** (`apps/agents/utils/scraper_adapters/firecrawl_crawl_adapter.py`):
   - Implementation for FireCrawl's `/crawl` endpoint
   - Supports multi-page crawling with depth and page limits
   - Handles include/exclude patterns and domain restrictions

4. **ScraperService** (`apps/agents/utils/scraper_service.py`):
   - Central service that manages adapters
   - Validates formats and parameters
   - Routes requests to the appropriate adapter

5. **scrape_url.py** (`apps/agents/utils/scrape_url.py`):
   - High-level API for scraping
   - Handles special cases like YouTube and PDF
   - Uses the ScraperService internally

## Using the Scraper Service

### Basic Usage

The simplest way to use the Scraper Service is through the `scrape_url` function for single pages or the `crawl_website` function for multi-page crawling:

```python
from apps.agents.utils.scrape_url import scrape_url, crawl_website

# Basic usage with default parameters (single page)
result = scrape_url(url="https://example.com")

# Request specific output formats
result = scrape_url(
    url="https://example.com",
    output_type="text,html,links"
)

# With additional parameters
result = scrape_url(
    url="https://example.com",
    output_type="text,metadata",
    cache=True,
    stealth=True,
    timeout=60000,
    device="mobile"
)

# Multi-page crawling
result = crawl_website(
    url="https://example.com",
    output_type="text,links",
    max_pages=100,
    max_depth=3,
    include_patterns=["/blog/.*"],
    exclude_patterns=["/admin/.*"],
    stay_within_domain=True
)
```

### Using ScraperService Directly

For more control, you can use the ScraperService directly:

```python
from apps.agents.utils.scraper_service import ScraperService

# Initialize the service (uses default adapter)
scraper_service = ScraperService()

# Or specify an adapter
scraper_service = ScraperService(adapter_name="firecrawl")

# Scrape a URL
result = scraper_service.scrape(
    url="https://example.com",
    output_types=["text", "html", "links"],
    timeout=30000,
    stealth=True
)
```

### Available Output Formats

The following output formats are supported:

- `text`: Plain text content
- `html`: HTML content
- `raw_html`: Raw HTML content (unprocessed)
- `links`: Links found on the page
- `metadata`: Page metadata (title, description, etc.)
- `full`: All of the above combined

You can request multiple formats by providing a comma-separated string or a list:

```python
# As a comma-separated string
result = scrape_url(url="https://example.com", output_type="text,links,metadata")

# Or as a list when using ScraperService directly
result = scraper_service.scrape(url="https://example.com", output_types=["text", "links", "metadata"])
```

### Response Format

The response is a dictionary with the following structure:

```python
{
    'url': 'https://example.com',
    'domain': 'example.com',
    'title': 'Example Domain',
    'byline': 'Author Name',
    'content': '<html>...</html>',  # HTML content
    'textContent': 'This is the text content...',  # Text content
    'excerpt': 'This is a brief description...',
    'length': 1234,
    'meta': {
        'general': {
            'author': 'Author Name',
            'description': 'Page description',
            'language': 'en',
            'statusCode': 200
        },
        'contentType': 'html',
        'links': ['https://example.com/page1', 'https://example.com/page2']
    }
}
```

## Adding a New Adapter

To add a new adapter for a different scraping engine:

1. Create a new adapter class that implements the `ScraperAdapter` interface
2. Register the adapter with the `ScraperService`

### Step 1: Create a New Adapter

Create a new file in `apps/agents/utils/scraper_adapters/` (e.g., `playwright_adapter.py`):

```python
"""
Playwright adapter for web scraping.
"""
import logging
from typing import Dict, List, Any, Optional, Union

from .base import ScraperAdapter

logger = logging.getLogger(__name__)

class PlaywrightAdapter(ScraperAdapter):
    """Adapter for Playwright web scraping."""

    # Format mapping from internal formats to Playwright formats
    FORMAT_MAPPING = {
        'text': 'text',
        'html': 'html',
        'raw_html': 'raw_html',
        'links': 'links',
        'metadata': 'metadata',
        'full': ['text', 'html', 'links', 'metadata']
    }

    def __init__(self, config=None):
        """Initialize the Playwright adapter."""
        self.config = config or {}

    def get_supported_formats(self) -> List[str]:
        """Get the list of formats supported by Playwright."""
        return list(self.FORMAT_MAPPING.keys())

    def map_formats(self, formats: Union[str, List[str]]) -> List[str]:
        """Map internal format names to Playwright format names."""
        if isinstance(formats, str):
            # Handle comma-separated string
            formats = [fmt.strip() for fmt in formats.split(',')]

        playwright_formats = []
        for fmt in formats:
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
        Scrape a URL using Playwright and return the content in the requested formats.

        Args:
            url: The URL to scrape
            formats: List of formats to return
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
        try:
            # Implement Playwright scraping logic here
            # This is just a placeholder - you would need to implement the actual Playwright logic

            # Example implementation:
            from playwright.sync_api import sync_playwright

            result = {}

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36" if not mobile else None,
                    viewport={"width": 1280, "height": 720} if not mobile else {"width": 375, "height": 667}
                )

                if headers:
                    context.set_extra_http_headers(headers)

                page = context.new_page()

                # Navigate to the URL
                page.goto(url, timeout=timeout)

                # Wait for content to load
                if wait_for:
                    page.wait_for_timeout(wait_for)

                # Extract content based on requested formats
                for fmt in formats:
                    if fmt == 'text':
                        if css_selector:
                            result['text'] = page.text_content(css_selector)
                        else:
                            result['text'] = page.text_content('body')

                    elif fmt == 'html' or fmt == 'raw_html':
                        result['html'] = page.content()

                    elif fmt == 'links':
                        # Extract all links
                        links = page.eval_on_selector_all('a[href]', 'elements => elements.map(el => el.href)')
                        result['links'] = links

                    elif fmt == 'metadata':
                        # Extract metadata
                        metadata = {
                            'title': page.title(),
                            'description': page.eval_on_selector('meta[name="description"]', 'el => el.content') if page.query_selector('meta[name="description"]') else '',
                            'language': page.eval_on_selector('html', 'el => el.lang') if page.query_selector('html[lang]') else '',
                            'statusCode': 200  # Playwright doesn't expose status code directly
                        }
                        result['metadata'] = metadata

                browser.close()

            return result

        except Exception as e:
            logger.error(f"Error scraping URL with Playwright: {url}, error: {str(e)}")
            return {"error": str(e)}
```

### Step 2: Register the Adapter

Update `apps/agents/utils/scraper_adapters/__init__.py` to include your new adapter:

```python
"""
Scraper adapters package.
"""
from .base import ScraperAdapter
from .firecrawl_adapter import FireCrawlAdapter
from .playwright_adapter import PlaywrightAdapter  # Add your new adapter

__all__ = ['ScraperAdapter', 'FireCrawlAdapter', 'PlaywrightAdapter']
```

Then register it with the ScraperService in `apps/agents/utils/scraper_service.py`:

```python
class ScraperService:
    """
    Service for web scraping using different adapters.
    """

    # Default adapter to use if not specified
    DEFAULT_ADAPTER = 'firecrawl'

    # Map of adapter names to adapter classes
    ADAPTERS = {
        'firecrawl': FireCrawlAdapter,
        'playwright': PlaywrightAdapter,  # Add your new adapter
    }
```

### Step 3: Use the New Adapter

Now you can use your new adapter:

```python
from apps.agents.utils.scraper_service import ScraperService

# Use the new adapter
scraper_service = ScraperService(adapter_name="playwright")

# Or specify it when calling scrape_url
from apps.agents.utils.scrape_url import scrape_url

result = scrape_url(
    url="https://example.com",
    output_type="text,html",
    adapter_name="playwright"
)
```

## Best Practices

1. **Error Handling**: Always handle exceptions in your adapter and return an error message in the result.
2. **Logging**: Use the logger to log important information and errors.
3. **Format Mapping**: Make sure your adapter correctly maps internal formats to provider-specific formats.
4. **Parameter Validation**: Validate parameters before passing them to the underlying scraping engine.
5. **Caching**: Implement caching to improve performance and reduce API calls.
6. **Stealth Mode**: Implement stealth mode to avoid detection by anti-bot measures.
7. **Timeouts**: Set appropriate timeouts to avoid hanging requests.

## Troubleshooting

### Common Issues

1. **Missing Dependencies**: Make sure you have installed all required dependencies for your adapter.
2. **API Keys**: Some scraping services require API keys. Make sure they are properly configured.
3. **Rate Limiting**: Be aware of rate limits imposed by the scraping service.
4. **Format Compatibility**: Not all adapters support all formats. Check the supported formats before using them.

### Debugging

To enable debug logging, add the following to your settings:

```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'apps.agents.utils.scraper_service': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
        'apps.agents.utils.scraper_adapters': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
}
```

## Conclusion

The Scraper Service provides a flexible and extensible architecture for web scraping. By following this guide, you can easily use the service and extend it with new adapters to support different scraping engines.

For more information, refer to the source code in the following files:

- `apps/agents/utils/scraper_adapters/base.py`
- `apps/agents/utils/scraper_adapters/firecrawl_adapter.py`
- `apps/agents/utils/scraper_service.py`
- `apps/agents/utils/scrape_url.py`
