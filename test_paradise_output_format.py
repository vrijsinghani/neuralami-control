#!/usr/bin/env python
"""
Test script for the output format handling in the unified web crawler with Paradise Floors website.
Run with: python manage.py shell < test_paradise_output_format.py
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

def test_output_format():
    """Test the output format handling of the unified crawler."""
    print("\n\n=== Testing output format handling with URL: https://www.paradisefloorsandmore.com/ ===\n")
    
    result = crawl_website(
        start_url="https://www.paradisefloorsandmore.com/",
        max_pages=1,
        max_depth=1,
        output_format=["text", "html", "links", "metadata"],
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
        print(f"First result content keys: {list(first_result.keys())}")
        
        # Check if text is present
        if "text" in first_result:
            print(f"Text content length: {len(first_result['text'])}")
            print(f"Text content preview: {first_result['text'][:100]}...")
        else:
            print("No text content found")
            
        # Check if HTML is present
        if "html" in first_result:
            print(f"HTML content length: {len(first_result['html'])}")
            print(f"HTML content preview: {first_result['html'][:100]}...")
        else:
            print("No HTML content found")
            
        # Check if links are present
        if "links" in first_result:
            print(f"Number of links: {len(first_result['links'])}")
            if first_result['links']:
                print(f"First link: {first_result['links'][0]}")
        else:
            print("No links found")
            
        # Check if metadata is present
        if "metadata" in first_result:
            print(f"Metadata keys: {list(first_result['metadata'].keys())}")
        else:
            print("No metadata found")
    else:
        print("No results found")
        
    return result

def main():
    """Run the tests."""
    print("\n=== Starting Paradise Floors output format tests ===\n")
    
    # Test output format handling
    test_output_format()
    
    print("\n=== All tests completed ===\n")

if __name__ == "__main__":
    main()
