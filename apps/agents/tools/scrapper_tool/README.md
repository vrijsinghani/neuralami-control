# ScrapperTool

A reliable and feature-rich web scraping tool designed to extract content from web pages in various formats. This tool serves as a robust replacement for the crawl4ai service and utilizes the new `scrape_url` utility functions for efficient content extraction.

## Features

- **Multiple Output Formats**: Extract content in various formats:
  - `HTML`: Raw HTML from the page
  - `CLEANED_HTML`: Cleaned HTML with unnecessary elements removed
  - `METADATA`: Page metadata including title, description, og tags, etc.
  - `TEXT`: Plain text content with formatting removed
  - `LINKS`: All links found on the page with text and URLs
  - `FULL`: Comprehensive data including all formats for complete analysis

- **Configurable Parameters**:
  - `cache`: Enable/disable caching of results
  - `stealth`: Use stealth mode to avoid detection
  - `timeout`: Customize request timeout
  - `device`: Emulate specific devices (desktop, mobile, tablet, or specific models)
  - `wait_until`: Control when to consider page loading complete

- **Smart Device Handling**: Translate simple device names (`desktop`, `mobile`, `tablet`) into specific device profiles.

- **Robust Error Handling**: Clear error messages in JSON format for connection issues, invalid responses, and other common problems.

- **Format-Specific Processing**: Uses the appropriate scraper endpoints based on the requested output type.

## Usage Examples

### Basic Usage

```python
from apps.agents.tools.scrapper_tool import ScrapperTool

# Initialize the tool
scrapper = ScrapperTool()

# Basic scrape with text output (default)
result = scrapper._run(
    url="https://example.com",
    user_id=1
)

# Parse the result
import json
data = json.loads(result)
print(f"Extracted content: {data['text']}")
```

### Advanced Usage with Different Output Types

```python
# Get page links
links_result = scrapper._run(
    url="https://news.example.com",
    user_id=1,
    output_type="links"
)

# Get HTML content
html_result = scrapper._run(
    url="https://blog.example.com/article",
    user_id=1,
    output_type="html",
    cache=True,
    stealth=True
)

# Get comprehensive data with mobile emulation
full_result = scrapper._run(
    url="https://store.example.com/product",
    user_id=1,
    output_type="full",
    device="mobile",
    timeout=120000,  # 2 minute timeout
    wait_until="networkidle0"  # Wait until network is idle
)
```

### Device Emulation Examples

```python
# Use preset device types
mobile_result = scrapper._run(
    url="https://example.com",
    user_id=1,
    device="mobile"  # Automatically uses iPhone 12
)

tablet_result = scrapper._run(
    url="https://example.com",
    user_id=1,
    device="tablet"  # Automatically uses iPad Pro
)

# Use specific device
custom_device_result = scrapper._run(
    url="https://example.com",
    user_id=1,
    device="iPhone 13 Pro Max"
)
```

## Response Formats

### Text Format Response

```json
{
  "url": "https://example.com",
  "text": "This is the extracted text content from the page..."
}
```

### Links Format Response

```json
{
  "url": "https://example.com",
  "domain": "example.com",
  "title": "Example Website",
  "links_count": 24,
  "links": [
    {
      "url": "https://example.com/page1",
      "text": "Page 1 Title"
    },
    {
      "url": "https://example.com/page2",
      "text": "Page 2 Title"
    }
  ]
}
```

### Full Format Response

```json
{
  "url": "https://example.com",
  "domain": "example.com",
  "title": "Example Website",
  "excerpt": "Brief description of the page content",
  "html": "<html>Full HTML content...</html>",
  "cleaned_html": "<div>Cleaned HTML content...</div>",
  "text": "Plain text content extracted from the page",
  "links": [
    {
      "url": "https://example.com/page1",
      "text": "Page 1 Title"
    }
  ],
  "meta": {
    "description": "Meta description from the page",
    "og:title": "Open Graph title",
    "og:image": "https://example.com/image.jpg"
  }
}
```

## Implementation Details

The ScrapperTool follows a modular design that separates content extraction logic from format processing:

1. **URL Processing**: Validates and processes input URLs before scraping.
2. **Content Retrieval**: Uses `scrape_url` or `get_url_links` utility functions based on output type.
3. **Format Processing**: Formats the retrieved data according to the specified output type.
4. **Error Handling**: Provides detailed error information in JSON format.

The tool offers two main approaches to content retrieval:
- **Document Approach**: Uses the article endpoint for HTML, cleaned HTML, metadata, and text content.
- **Links Approach**: Uses the links endpoint specifically for extracting links from a page.

For the `FULL` output type, both approaches are combined to provide comprehensive data.

## Comparison with WebCrawlerTool

While the ScrapperTool is designed to extract content from a single page, the WebCrawlerTool builds on it to crawl multiple pages by following links. If you need to:

- Extract content from a single URL: Use **ScrapperTool**
- Follow links and extract content from multiple pages: Use **WebCrawlerTool**

The WebCrawlerTool uses ScrapperTool internally, following the composition pattern for clean separation of concerns. 