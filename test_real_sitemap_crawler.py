"""
Test script to verify the sitemap crawler can handle comma-separated output formats with a real URL.
Run with: python manage.py shell < test_real_sitemap_crawler.py
"""
import sys
import logging
import json
from apps.agents.tools.web_crawler_tool.sitemap_crawler import SitemapCrawlerTool, ContentOutputFormat

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
tool = SitemapCrawlerTool()

# Test with comma-separated output formats
output_format = "text,links,metadata"

print(f"\n\n=== Testing SitemapCrawlerTool with URL: {url}, output_format: {output_format} ===\n")

try:
    # Call the tool with a real URL
    result = tool._run(
        url=url,
        user_id=1,
        max_sitemap_urls_to_process=1,  # Just process one URL for testing
        max_sitemap_retriever_pages=10,
        requests_per_second=1.0,
        output_format=output_format
    )
    
    # Check if the result is a string (JSON)
    if isinstance(result, str):
        try:
            # Parse the JSON result
            parsed_result = json.loads(result)
            
            # Print the structure of the result
            print(f"\n=== Result structure: {list(parsed_result.keys())} ===")
            
            # Check if the parsed result has the expected structure
            if 'results' in parsed_result:
                print(f"\n=== Tool processed {len(parsed_result['results'])} URLs ===")
                
                # Print the first result
                if parsed_result['results']:
                    first_result = parsed_result['results'][0]
                    print(f"\nFirst result URL: {first_result.get('url')}")
                    
                    # Print all keys in the first result
                    print(f"First result keys: {list(first_result.keys())}")
                    
                    # Check if the result has the requested formats
                    if 'text' in first_result:
                        print(f"\nText content sample: {first_result['text'][:100]}...")
                    
                    if 'metadata' in first_result:
                        print(f"\nMetadata: {first_result['metadata']}")
                    
                    if 'links' in first_result:
                        print(f"\nLinks count: {len(first_result['links'])}")
                        print(f"First 3 links: {first_result['links'][:3]}")
            else:
                print(f"\nUnexpected result structure: {list(parsed_result.keys())}")
        except json.JSONDecodeError:
            print(f"\nFailed to parse result as JSON: {result[:100]}...")
    else:
        print(f"\nUnexpected result type: {type(result)}")
        print(f"Result: {result}")
except Exception as e:
    print(f"\nError running the tool: {e}")

print("\n=== Test completed ===")
