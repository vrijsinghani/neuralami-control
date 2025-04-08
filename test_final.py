"""
Final test script to verify the web crawler tool is correctly handling URLs.
Run with: python manage.py shell < test_final.py
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

# Test URLs with and without www
urls_to_test = [
    "https://neuralami.com",
    "https://www.neuralami.com"
]

for url in urls_to_test:
    print(f"\n\n=== Testing WebCrawlerTool with URL: {url} ===\n")
    
    # Create the tool
    tool = WebCrawlerTool()
    
    # Call the tool directly
    result = tool._run(
        start_url=url,
        max_pages=1,
        max_depth=0,
        output_format=["text", "metadata", "screenshot"],
        device="desktop",
        delay_seconds=0.1
    )
    
    # Check the results
    if isinstance(result, dict) and 'results' in result:
        print(f"\n=== Tool returned result with {len(result['results'])} pages ===")
        
        # Print the URLs in the results
        for i, page in enumerate(result['results']):
            print(f"Page {i+1}: {page.get('url')}")
            print(f"Retrieved formats: {list(page.keys())}")
    else:
        print(f"\n=== Tool returned result of type {type(result)} ===")
        print(f"Result: {result}")

print("\n=== Test completed ===")
