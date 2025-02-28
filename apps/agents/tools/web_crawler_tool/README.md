# WebCrawlerTool

A powerful web crawling tool built on top of the ScrapperTool that crawls websites, follows links, and extracts content in various formats. This tool provides a reliable way to gather content from multiple pages of a website, respecting domain boundaries and URL patterns.

## Features

- **Multiple Output Formats**: Extract content in text, HTML, links, metadata, or comprehensive data.
- **Configurable Crawling Parameters**: Control depth, page limits, domain boundaries, and URL patterns.
- **Integration with ScrapperTool**: Uses ScrapperTool internally for reliable content extraction.
- **Progress Tracking**: Supports real-time progress updates via task system.
- **Error Handling**: Robust error handling with retry logic and timeout protection.
- **Asynchronous Execution**: Supports Celery task-based execution for long-running crawls.

## Usage Examples

### Basic Usage

```python
from apps.agents.tools.web_crawler_tool import WebCrawlerTool

# Initialize the tool
crawler = WebCrawlerTool()

# Basic crawl with defaults (10 pages max, depth 2, text output)
result = crawler._run(
    start_url="https://example.com",
    user_id=1
)

# Parse the result
import json
data = json.loads(result)
print(f"Crawled {data['total_pages']} pages")
```

### Advanced Usage

```python
# Crawl with specific configuration
result = crawler._run(
    start_url="https://blog.example.com",
    user_id=1,
    max_pages=20,  # Crawl up to 20 pages
    max_depth=3,   # Follow links up to 3 levels deep
    output_format="full",  # Get comprehensive data
    include_patterns=["blog", "article"],  # Only pages with these patterns
    exclude_patterns=["category", "tag"],  # Skip pages with these patterns
    stay_within_domain=True,  # Don't leave the starting domain
    cache=True,    # Use cached results when available
    stealth=True,  # Use stealth mode
    device="mobile",  # Emulate a mobile device
    timeout=30000  # 30 second timeout per page
)
```

### Asynchronous Execution

```python
from apps.agents.tools.web_crawler_tool.web_crawler_tool import web_crawler_task

# Start a Celery task for crawling
task = web_crawler_task.delay(
    start_url="https://example.com",
    user_id=1,
    max_pages=50,
    max_depth=4
)

# Get the task ID for tracking
task_id = task.id
print(f"Started crawling task with ID: {task_id}")
```

## Implementation Details

The WebCrawlerTool follows a composition pattern, using ScrapperTool internally for content extraction. This design provides several advantages:

1. **Separation of Concerns**: The crawler handles link discovery and traversal, while ScrapperTool handles content extraction.
2. **Code Reusability**: Leverages existing ScrapperTool code for reliable content extraction.
3. **Flexibility**: Can be easily updated to use different scraping mechanisms in the future.

The crawler maintains state during execution, including:
- Queue of URLs to visit
- Set of visited URLs
- Depth tracking for each URL
- Results for each processed URL

This allows it to efficiently manage the crawling process and avoid revisiting the same URLs. 