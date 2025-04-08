#!/usr/bin/env python
"""
Test script for the progress callback in the unified web crawler.
Run with: python manage.py shell < test_progress_callback.py
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

def test_progress_callback():
    """Test the progress callback in the unified web crawler."""
    print("\n\n=== Testing progress callback with URL: https://example.com/ ===\n")
    
    result = crawl_website(
        start_url="https://example.com/",
        max_pages=1,
        max_depth=0,
        output_format=["text", "html", "links", "metadata"],
        delay_seconds=1.0,
        mode="auto",
        progress_callback=progress_callback
    )
    
    print(f"Crawl mode used: {result.get('crawl_mode', 'unknown')}")
    print(f"Elapsed time: {result.get('elapsed_time', 0):.2f} seconds")
    print(f"Stats: {result.get('stats', {})}")
    
    if "results" in result and result["results"]:
        print(f"Number of results: {len(result['results'])}")
    else:
        print("No results found")

# Run the test
print("\n=== Starting progress callback test ===\n")
test_progress_callback()
print("\n=== Test completed ===\n")
