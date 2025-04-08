#!/usr/bin/env python
"""
Test script for the updated web crawler tool.
Run with: python test_updated_crawler.py
"""
import os
import sys
import django
import logging
import json
import time

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Import the updated web crawler tool
from apps.agents.tools.web_crawler_tool.web_crawler_tool_updated import crawl_website

def test_updated_crawler():
    """Test the updated web crawler tool."""
    print("\n=== Testing updated web crawler with URL: https://www.paradisefloorsandmore.com/ ===\n")
    
    result = crawl_website(
        start_url="https://www.paradisefloorsandmore.com/",
        max_pages=2,
        max_depth=1,
        output_format=["text", "html", "links", "metadata"],
        delay_seconds=1.0,
        mode="auto"
    )
    
    print(f"Crawl mode used: {result.get('crawl_mode', 'unknown')}")
    print(f"Elapsed time: {result.get('elapsed_time', 0):.2f} seconds")
    print(f"Stats: {result.get('stats', {})}")
    
    if "results" in result and result["results"]:
        print(f"Number of results: {len(result['results'])}")
        first_result = result["results"][0]
        print(f"First result URL: {first_result.get('url', 'No URL')}")
        print(f"First result title: {first_result.get('title', 'No title')}")
        print(f"First result content keys: {list(first_result.keys())}")
        
        # Check if we got HTML content
        if 'html' in first_result and first_result['html']:
            print(f"HTML content length: {len(first_result['html'])} characters")
            print(f"HTML content sample: {first_result['html'][:100]}...")
        else:
            print("No HTML content found")
    else:
        print("No results found")
        
    return result

def main():
    """Run the test."""
    print("\n=== Starting updated web crawler test ===\n")
    
    # Test the updated web crawler
    result = test_updated_crawler()
    
    print("\n=== Test completed ===\n")

if __name__ == "__main__":
    main()
