"""
Test script to verify that the sitemap crawler is correctly handling HTML content.
Run with: python manage.py shell < test_sitemap_html.py
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

# Create the sitemap crawler
sitemap_crawler = SitemapCrawlerTool()

print(f"\n\n=== Testing sitemap crawler with URL: {url}, output_format: html,text,links,metadata ===\n")

# Call the sitemap crawler
sitemap_result = sitemap_crawler._run(
    url=url,
    user_id=1,
    max_sitemap_urls_to_process=1,
    max_sitemap_retriever_pages=10,
    requests_per_second=1.0,
    output_format="html,text,links,metadata"
)

# Check the results
if isinstance(sitemap_result, str):
    try:
        # Parse the JSON result
        parsed_result = json.loads(sitemap_result)
        
        print(f"\n=== Sitemap crawler returned result with {len(parsed_result.get('results', []))} pages ===")
        
        # Check if the first result has HTML content
        if parsed_result.get('results', []):
            first_result = parsed_result['results'][0]
            
            print(f"\nFirst result URL: {first_result.get('url', '')}")
            print(f"First result keys: {list(first_result.keys())}")
            
            if 'html' in first_result:
                html_length = len(first_result['html'])
                print(f"HTML content length: {html_length} characters")
                print(f"HTML content sample: {first_result['html'][:100]}...")
            else:
                print("No HTML content found in the first result")
        else:
            print("No results found")
    except json.JSONDecodeError:
        print(f"\nFailed to parse sitemap crawler result as JSON: {sitemap_result[:100]}...")
else:
    print(f"\n=== Sitemap crawler returned result of type {type(sitemap_result)} ===")
    print(f"Result: {sitemap_result}")

print("\n=== Test completed ===")
