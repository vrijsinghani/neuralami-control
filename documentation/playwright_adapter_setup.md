# Setting Up the Playwright Adapter

This guide explains how to set up and use the Playwright adapter for web scraping in the NeuralAMI Control system.

## Overview

The Playwright adapter has been set as the default adapter in the `scrape_url.py` file. This adapter connects to a self-hosted Playwright service that provides comprehensive metadata extraction from web pages.

## Configuration

### Environment Variables

Add the following environment variables to your `.env` file:

```
PLAYWRIGHT_API_URL='https://playwright.neuralami.ai/api'
PLAYWRIGHT_API_KEY='your-playwright-api-key'
```

Replace `your-playwright-api-key` with the actual API key for your Playwright service.

### Django Settings

The adapter reads its configuration from Django settings, which are already set up to use the environment variables:

```python
# Playwright service configuration
PLAYWRIGHT_API_URL=os.getenv('PLAYWRIGHT_API_URL')
PLAYWRIGHT_API_KEY=os.getenv('PLAYWRIGHT_API_KEY')
```

## Using the Playwright Adapter

The `scrape_url` and `crawl_website` functions now use the Playwright adapter by default:

```python
from apps.agents.utils.scrape_url import scrape_url

# The Playwright adapter is used by default
result = scrape_url(
    url="https://example.com",
    output_type="text,html,metadata"
)
```

If you need to use a different adapter, you can still specify it:

```python
result = scrape_url(
    url="https://example.com",
    output_type="text,html",
    adapter_name="firecrawl"  # Use FireCrawl adapter instead
)
```

## Metadata Extraction

The Playwright adapter extracts comprehensive metadata from web pages, including:

- Basic metadata: title, URL, domain
- Meta tags: description, charset, viewport, robots
- Canonical link
- Open Graph tags: og:title, og:description, og:image
- Twitter Card tags: twitter:card, twitter:title, twitter:description, twitter:image
- Language and author information
- **ALL other meta tags** found on the page

The extracted metadata is available directly in the `meta` field of the result:

```python
result = scrape_url(url="https://example.com", output_type="metadata")
metadata = result['meta']

# Access metadata fields directly
title = metadata['title']
description = metadata.get('description', '')
og_image = metadata.get('og:image', '')
twitter_card = metadata.get('twitter:card', '')
viewport = metadata.get('viewport', '')
```

All metadata is returned in a flat structure with the original keys from the HTML meta tags. This simplified approach makes it easier to access all metadata from the page.

## Troubleshooting

If you encounter issues with the Playwright adapter:

1. Check that the Playwright service is running and accessible
2. Verify that the API URL and API key are correctly set in your environment
3. Check the logs for any error messages
4. Try using the debug endpoint of the Playwright service:
   ```
   https://playwright.neuralami.ai/debug/metadata?url=https://example.com
   ```

## Additional Resources

For more information about the Playwright service and adapter, see:

- [Playwright Adapter Guide](documentation/playwright_adapter_guide.md)
- [Playwright Service README](playwright_service/README.md)
