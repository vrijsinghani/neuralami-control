"""
Simple test script to verify the web crawler tool is correctly requesting all formats.
Run with: python manage.py shell < test_simple_crawler.py
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

# Test URL
url = "https://neuralami.com"

# Test with multiple formats
output_formats = ["text", "metadata", "screenshot"]

print(f"\n\n=== Testing crawler with formats: {output_formats} ===\n")

# Run the crawler
result = crawl_website(
    start_url=url,
    max_pages=1,  # Just crawl one page for testing
    max_depth=0,  # Don't follow links
    output_format=output_formats,
    delay_seconds=0.1,  # Minimal delay for testing
)

# Check the results
print(f"\n=== Crawler completed with {len(result.get('results', []))} pages ===")

# Print the keys for each result to see what formats were retrieved
for i, page in enumerate(result.get('results', [])):
    print(f"\nPage {i+1}: {page.get('url')}")
    print(f"Retrieved formats: {list(page.keys())}")
    
    # Check if we got the requested formats
    for fmt in output_formats:
        if fmt in page:
            print(f"✅ {fmt} format was retrieved")
            
            # Print a sample of the content
            if fmt == 'text':
                text_sample = page[fmt][:100] + '...' if isinstance(page[fmt], str) and len(page[fmt]) > 100 else page[fmt]
                print(f"Text sample: {text_sample}")
            elif fmt == 'metadata':
                if isinstance(page[fmt], dict):
                    print(f"Metadata keys: {list(page[fmt].keys())}")
                    for key, value in list(page[fmt].items())[:5]:  # Show first 5 metadata items
                        print(f"  {key}: {value}")
                    if len(page[fmt]) > 5:
                        print(f"  ... and {len(page[fmt]) - 5} more metadata items")
                else:
                    print(f"Metadata (not a dict): {page[fmt]}")
            elif fmt == 'screenshot':
                if isinstance(page[fmt], str):
                    print(f"Screenshot length: {len(page[fmt])} characters")
                else:
                    print(f"Screenshot (not a string): {type(page[fmt])}")
        else:
            print(f"❌ {fmt} format was NOT retrieved")

print("\n=== Test completed ===")
