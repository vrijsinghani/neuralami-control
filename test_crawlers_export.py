"""
Test script to verify that both the standard crawler and sitemap crawler are using the same export format.
Run with: python manage.py shell < test_crawlers_export.py
"""
import sys
import logging
import json
from apps.agents.tools.web_crawler_tool.web_crawler_tool import crawl_website
from apps.agents.tools.web_crawler_tool.sitemap_crawler import SitemapCrawlerTool

# Set up logging to see debug messages
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Test parameters
website_url = "https://neuralami.com"
max_pages = 1
max_depth = 0
output_format = ["text", "metadata", "links"]

print(f"\n\n=== Testing standard crawler with URL: {website_url} ===\n")

# Call the standard crawler
standard_result = crawl_website(
    start_url=website_url,
    max_pages=max_pages,
    max_depth=max_depth,
    output_format=output_format,
    delay_seconds=0.1
)

# Check the results
if isinstance(standard_result, dict) and 'results' in standard_result:
    print(f"\n=== Standard crawler returned result with {len(standard_result['results'])} pages ===")
    
    # Save the first result to a file for inspection
    with open('standard_crawler_result.json', 'w') as f:
        # Get the first result
        first_result = standard_result['results'][0] if standard_result['results'] else {}
        
        # Create a serializable version of the result
        serializable_result = {
            'url': first_result.get('url', ''),
            'title': first_result.get('title', ''),
            'text_length': len(first_result.get('text', '')) if 'text' in first_result else 0,
            'metadata_count': len(first_result.get('metadata', {})) if 'metadata' in first_result else 0,
            'links_count': len(first_result.get('links', [])) if 'links' in first_result else 0
        }
        
        # Add metadata sample
        if 'metadata' in first_result and first_result['metadata']:
            serializable_result['metadata_sample'] = dict(list(first_result['metadata'].items())[:5])
            
        # Add links sample
        if 'links' in first_result and first_result['links']:
            serializable_result['links_sample'] = first_result['links'][:5]
            
        json.dump(serializable_result, f, indent=2)
        
    print(f"\nSaved standard crawler result to standard_crawler_result.json")
else:
    print(f"\n=== Standard crawler returned result of type {type(standard_result)} ===")
    print(f"Result: {standard_result}")

print(f"\n\n=== Testing sitemap crawler with URL: {website_url} ===\n")

# Create the sitemap crawler
sitemap_crawler = SitemapCrawlerTool()

# Call the sitemap crawler
sitemap_result = sitemap_crawler._run(
    url=website_url,
    user_id=1,
    max_sitemap_urls_to_process=1,
    max_sitemap_retriever_pages=10,
    requests_per_second=1.0,
    output_format=",".join(output_format)
)

# Check the results
if isinstance(sitemap_result, str):
    try:
        # Parse the JSON result
        parsed_result = json.loads(sitemap_result)
        
        print(f"\n=== Sitemap crawler returned result with {len(parsed_result.get('results', []))} pages ===")
        
        # Save the first result to a file for inspection
        with open('sitemap_crawler_result.json', 'w') as f:
            # Get the first result
            first_result = parsed_result['results'][0] if parsed_result.get('results', []) else {}
            
            # Create a serializable version of the result
            serializable_result = {
                'url': first_result.get('url', ''),
                'title': first_result.get('title', ''),
                'text_length': len(first_result.get('text', '')) if 'text' in first_result else 0,
                'metadata_count': len(first_result.get('metadata', {})) if 'metadata' in first_result else 0,
                'links_count': len(first_result.get('links', [])) if 'links' in first_result else 0
            }
            
            # Add metadata sample
            if 'metadata' in first_result and first_result['metadata']:
                serializable_result['metadata_sample'] = dict(list(first_result['metadata'].items())[:5])
                
            # Add links sample
            if 'links' in first_result and first_result['links']:
                serializable_result['links_sample'] = first_result['links'][:5]
                
            json.dump(serializable_result, f, indent=2)
            
        print(f"\nSaved sitemap crawler result to sitemap_crawler_result.json")
    except json.JSONDecodeError:
        print(f"\nFailed to parse sitemap crawler result as JSON: {sitemap_result[:100]}...")
else:
    print(f"\n=== Sitemap crawler returned result of type {type(sitemap_result)} ===")
    print(f"Result: {sitemap_result}")

print("\n=== Test completed ===")
