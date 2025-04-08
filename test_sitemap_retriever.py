import json
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Import the tool
from apps.agents.tools.sitemap_retriever_tool.sitemap_retriever_tool import SitemapRetrieverTool

# Create and run the tool
tool = SitemapRetrieverTool()
url = "https://www.accel-golf.com"
results = tool.run(url=url, user_id=1, max_pages=100, requests_per_second=5.0)

# Print results
print("\n--- Final Results ---")
print(json.dumps(results, indent=2))

if results["success"]:
    print(f"\nSuccessfully retrieved {results['total_urls_found']} URLs using method: {results['method_used']}")
    print("URLs found:")
    for i, url_data in enumerate(results["urls"]):
        print(f"  {i+1}. {url_data.get('loc')}")
else:
    print(f"\nTool failed: {results.get('error', 'Unknown error')}")

print(f"\nDuration: {results['duration_seconds']} seconds")
print(f"Crawl Delay Used: {results['robots_crawl_delay_found']}")
