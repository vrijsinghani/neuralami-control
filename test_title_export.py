"""
Test script to verify that titles are properly exported.
Run with: python manage.py shell < test_title_export.py
"""
import sys
import logging
import json
from apps.agents.tools.web_crawler_tool.sitemap_crawler import SitemapCrawlerTool, ContentOutputFormat
from apps.crawl_website.export_utils import generate_csv_content

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
        
        # Check if the first result has a title
        if parsed_result.get('results', []):
            first_result = parsed_result['results'][0]
            
            print(f"\nFirst result URL: {first_result.get('url', '')}")
            print(f"First result title: {first_result.get('title', 'No title found')}")
            
            if 'metadata' in first_result and isinstance(first_result['metadata'], dict):
                print(f"Title in metadata: {first_result['metadata'].get('title', 'No title in metadata')}")
            
            # Generate CSV content
            csv_content = generate_csv_content(parsed_result['results'])
            print(f"\nCSV content (first 500 characters):\n{csv_content[:500]}...")
        else:
            print("No results found")
    except json.JSONDecodeError:
        print(f"\nFailed to parse sitemap crawler result as JSON: {sitemap_result[:100]}...")
else:
    print(f"\n=== Sitemap crawler returned result of type {type(sitemap_result)} ===")
    print(f"Result: {sitemap_result}")

print("\n=== Test completed ===")
