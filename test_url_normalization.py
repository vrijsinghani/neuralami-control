"""
Test script to verify URL normalization in the web crawler tool.
Run with: python manage.py shell < test_url_normalization.py
"""
import sys
import logging
from apps.agents.tools.web_crawler_tool.web_crawler_tool import crawl_website

# Set up logging to see debug messages
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Test URLs with and without www
urls_to_test = [
    "https://neuralami.com",
    "https://www.neuralami.com"
]

for url in urls_to_test:
    print(f"\n\n=== Testing crawler with URL: {url} ===\n")
    
    # Run the crawler
    result = crawl_website(
        start_url=url,
        max_pages=1,  # Just crawl one page for testing
        max_depth=0,  # Don't follow links
        output_format=["text"],
        delay_seconds=0.1,  # Minimal delay for testing
    )
    
    # Check the results
    print(f"\n=== Crawler completed with {len(result.get('results', []))} pages ===")
    
    # Print the URLs in the results
    for i, page in enumerate(result.get('results', [])):
        print(f"Page {i+1}: {page.get('url')}")

print("\n=== Test completed ===")
