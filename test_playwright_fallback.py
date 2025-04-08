"""
Test script to verify that the Playwright adapter with fallback mechanism works correctly.
Run with: python manage.py shell < test_playwright_fallback.py
"""
import sys
import logging
from apps.agents.utils.scraper_adapters.playwright_adapter import PlaywrightAdapter

# Set up logging to see debug messages
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Test URL
url = "https://www.paradisefloorsandmore.com/"

print(f"\n\n=== Testing Playwright adapter with fallback for URL: {url} ===\n")

# Create a Playwright adapter instance
adapter = PlaywrightAdapter()

# Test the adapter
result = adapter.scrape(
    url=url,
    formats=["text", "html", "links", "metadata"],
    timeout=60000,
    stealth=True,
    max_retries=3
)

# Check the result
if "error" in result:
    print(f"Error: {result['error']}")
else:
    print(f"Success! Result keys: {list(result.keys())}")
    
    # Check if we got HTML content
    if "html" in result and result["html"]:
        print(f"HTML content length: {len(result['html'])} characters")
        print(f"HTML content sample: {result['html'][:100]}...")
    else:
        print("No HTML content found")
        
    # Check if we got text content
    if "text" in result and result["text"]:
        print(f"Text content length: {len(result['text'])} characters")
        print(f"Text content sample: {result['text'][:100]}...")
    else:
        print("No text content found")
        
    # Check if we got metadata
    if "metadata" in result and result["metadata"]:
        print(f"Metadata: {result['metadata']}")
    else:
        print("No metadata found")
        
    # Check if we got links
    if "links" in result and result["links"]:
        print(f"Links count: {len(result['links'])}")
        print(f"First 5 links: {result['links'][:5]}")
    else:
        print("No links found")

print("\n=== Test completed ===")
