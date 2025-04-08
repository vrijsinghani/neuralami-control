"""
Test script to verify URL normalization in the web crawler tool.
Run with: python manage.py shell < test_both_urls.py
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

print(f"\n\n=== Testing crawler with both URLs ===\n")

# Run the crawler with both URLs
result = crawl_website(
    start_url="https://neuralami.com",
    max_pages=2,  # Allow up to 2 pages
    max_depth=1,  # Follow links one level deep
    output_format=["text"],
    delay_seconds=0.1,  # Minimal delay for testing
)

# Check the results
print(f"\n=== Crawler completed with {len(result.get('results', []))} pages ===")

# Print the URLs in the results
for i, page in enumerate(result.get('results', [])):
    print(f"Page {i+1}: {page.get('url')}")

print("\n=== Test completed ===")
