"""
Test script to verify the unified web crawler with different modes.
Run with: python manage.py shell < test_crawler_modes.py
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

def test_mode(url, mode):
    """Test the crawler with a specific mode."""
    print(f"\n\n=== Testing {mode.upper()} mode with URL: {url} ===\n")
    
    result = crawl_website(
        start_url=url,
        max_pages=1,
        max_depth=0,
        output_format=["text", "html", "links", "metadata"],
        delay_seconds=1.0,
        mode=mode
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
            
        # Check if we got text content
        if 'text' in first_result and first_result['text']:
            print(f"Text content length: {len(first_result['text'])} characters")
            print(f"Text content sample: {first_result['text'][:100]}...")
        else:
            print("No text content found")
            
        # Check if we got metadata
        if 'metadata' in first_result and first_result['metadata']:
            print(f"Metadata keys: {list(first_result['metadata'].keys())}")
        else:
            print("No metadata found")
            
        # Check if we got links
        if 'links' in first_result and first_result['links']:
            print(f"Links count: {len(first_result['links'])}")
            print(f"First 5 links: {first_result['links'][:5]}")
        else:
            print("No links found")
    else:
        print("No results found")
        print(f"Result: {result}")

# Test URL that might have a sitemap
url = "https://www.example.com/"

# Test all three modes
print("\n=== Starting crawler mode tests ===\n")
test_mode(url, "auto")
test_mode(url, "sitemap")
test_mode(url, "discovery")
print("\n=== All tests completed ===\n")
