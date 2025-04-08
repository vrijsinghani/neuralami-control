"""
Test script to directly test the web_crawler_tool.
Run with: python manage.py shell < test_crawler_tool.py
"""
import sys
import logging
from apps.agents.tools.web_crawler_tool.web_crawler_tool import WebCrawlerTool

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

# Create the tool
tool = WebCrawlerTool()

# Test with multiple formats
formats = ["text", "metadata", "screenshot"]

print(f"\n\n=== Testing WebCrawlerTool with formats: {formats} ===\n")

# Call the tool directly
result = tool._run(
    start_url=url,
    max_pages=1,
    max_depth=0,
    output_format=formats,
    device="desktop",
    delay_seconds=0.1
)

# Check the results
print(f"\n=== Tool returned result with keys: {list(result.keys())} ===")

# Print the keys for each result to see what formats were retrieved
if 'results' in result:
    for i, page in enumerate(result['results']):
        print(f"\nPage {i+1}: {page.get('url')}")
        print(f"Retrieved formats: {list(page.keys())}")
        
        # Check if we got the requested formats
        for fmt in formats:
            if fmt in page:
                print(f"✅ {fmt} format was retrieved")
            else:
                print(f"❌ {fmt} format was NOT retrieved")
else:
    print("No results found in the response")

print("\n=== Test completed ===")
