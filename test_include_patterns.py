#!/usr/bin/env python
"""
Test script for the include patterns functionality.
Run with: python manage.py shell < test_include_patterns.py
"""
import sys
import logging
import json
from apps.agents.tools.web_crawler_tool.web_crawler_tool import crawl_website, CrawlMode

# Set up logging to see debug messages
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

def progress_callback(current, total, url):
    """Progress callback function."""
    print(f"Progress: {current}/{total} - {url}")

# Test with include patterns
include_patterns = [r".*about.*", r".*contact.*"]
print(f"Using include patterns: {include_patterns}")

result = crawl_website(
    start_url="https://www.paradisefloorsandmore.com/",
    max_pages=10,
    max_depth=1,
    output_format=["text"],
    delay_seconds=1.0,
    mode="sitemap",
    include_patterns=include_patterns,
    progress_callback=progress_callback
)

print(f"Crawl mode used: {result.get('crawl_mode', 'unknown')}")
print(f"Elapsed time: {result.get('elapsed_time', 0):.2f} seconds")
print(f"Stats: {result.get('stats', {})}")

if "results" in result and result["results"]:
    print(f"Number of results: {len(result['results'])}")
    print("URLs crawled:")
    for item in result["results"]:
        print(f"  - {item.get('url', 'No URL')}")
else:
    print("No results found")
