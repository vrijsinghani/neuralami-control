#!/usr/bin/env python
"""
Test script for the fixed web crawler tool.
Run with: python manage.py shell < test_fixed_crawler.py
"""
import sys
import logging
from apps.agents.tools.web_crawler_tool.web_crawler_tool import WebCrawlerTool

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

def test_web_crawler_tool():
    """Test the WebCrawlerTool initialization."""
    print("\n\n=== Testing WebCrawlerTool initialization ===\n")
    
    # Initialize the WebCrawlerTool
    tool = WebCrawlerTool()
    print(f"Successfully initialized WebCrawlerTool: {tool}")
    
    # Test running the tool with a progress callback
    print("\n=== Testing WebCrawlerTool._run with progress_callback ===\n")
    
    result = tool._run(
        start_url="https://example.com/",
        max_pages=1,
        max_depth=0,
        output_format="text",
        progress_callback=progress_callback
    )
    
    print(f"Successfully ran WebCrawlerTool._run with progress_callback")
    print(f"Result stats: {result.get('stats', {})}")

# Run the test
print("\n=== Starting WebCrawlerTool test ===\n")
test_web_crawler_tool()
print("\n=== Test completed ===\n")
