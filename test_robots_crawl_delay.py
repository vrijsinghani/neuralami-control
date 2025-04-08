#!/usr/bin/env python
"""
Test script for the robots.txt crawl-delay handling in the unified web crawler.
Run with: python manage.py shell < test_robots_crawl_delay.py
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

def test_sitemap_mode():
    """Test the SITEMAP mode of the unified crawler."""
    print("\n\n=== Testing SITEMAP mode with URL: https://www.paradisefloorsandmore.com/ ===\n")
    
    result = crawl_website(
        start_url="https://www.paradisefloorsandmore.com/",
        max_pages=3,
        max_depth=1,
        output_format=["text"],
        delay_seconds=1.0,
        mode="sitemap",
        progress_callback=progress_callback
    )
    
    print(f"Crawl mode used: {result.get('crawl_mode', 'unknown')}")
    print(f"Elapsed time: {result.get('elapsed_time', 0):.2f} seconds")
    print(f"Stats: {result.get('stats', {})}")
    
    if "results" in result and result["results"]:
        print(f"Number of results: {len(result['results'])}")
        first_result = result["results"][0]
        print(f"First result URL: {first_result.get('url', 'No URL')}")
    else:
        print("No results found")
        
    return result

def test_auto_mode():
    """Test the AUTO mode of the unified crawler."""
    print("\n\n=== Testing AUTO mode with URL: https://www.paradisefloorsandmore.com/ ===\n")
    
    result = crawl_website(
        start_url="https://www.paradisefloorsandmore.com/",
        max_pages=3,
        max_depth=1,
        output_format=["text"],
        delay_seconds=1.0,
        mode="auto",
        progress_callback=progress_callback
    )
    
    print(f"Crawl mode used: {result.get('crawl_mode', 'unknown')}")
    print(f"Elapsed time: {result.get('elapsed_time', 0):.2f} seconds")
    print(f"Stats: {result.get('stats', {})}")
    
    if "results" in result and result["results"]:
        print(f"Number of results: {len(result['results'])}")
        first_result = result["results"][0]
        print(f"First result URL: {first_result.get('url', 'No URL')}")
    else:
        print("No results found")
        
    return result

def test_discovery_mode():
    """Test the DISCOVERY mode of the unified crawler."""
    print("\n\n=== Testing DISCOVERY mode with URL: https://www.paradisefloorsandmore.com/ ===\n")
    
    result = crawl_website(
        start_url="https://www.paradisefloorsandmore.com/",
        max_pages=3,
        max_depth=1,
        output_format=["text"],
        delay_seconds=1.0,
        mode="discovery",
        progress_callback=progress_callback
    )
    
    print(f"Crawl mode used: {result.get('crawl_mode', 'unknown')}")
    print(f"Elapsed time: {result.get('elapsed_time', 0):.2f} seconds")
    print(f"Stats: {result.get('stats', {})}")
    
    if "results" in result and result["results"]:
        print(f"Number of results: {len(result['results'])}")
        first_result = result["results"][0]
        print(f"First result URL: {first_result.get('url', 'No URL')}")
    else:
        print("No results found")
        
    return result

def main():
    """Run the tests."""
    print("\n=== Starting robots.txt crawl-delay tests ===\n")
    
    # Test SITEMAP mode
    sitemap_result = test_sitemap_mode()
    
    # Test AUTO mode
    auto_result = test_auto_mode()
    
    # Test DISCOVERY mode
    discovery_result = test_discovery_mode()
    
    print("\n=== All tests completed ===\n")

if __name__ == "__main__":
    main()
