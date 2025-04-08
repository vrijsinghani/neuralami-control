"""
Test script to verify that the crawler utilities are working correctly.
Run with: python manage.py shell < test_crawler_utils.py
"""
import sys
import logging
from apps.agents.utils.crawler_utils import init_crawler_rate_limiting, respect_rate_limit
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

# Test URL
url = "https://www.paradisefloorsandmore.com/"

print(f"\n\n=== Testing init_crawler_rate_limiting with URL: {url} ===\n")

# Test init_crawler_rate_limiting
domain, robots_crawl_delay = init_crawler_rate_limiting(url, 1.0)
print(f"Domain: {domain}")
print(f"Robots crawl delay: {robots_crawl_delay}")

print(f"\n\n=== Testing respect_rate_limit with domain: {domain} ===\n")

# Test respect_rate_limit
respect_rate_limit(domain)
print("Rate limit respected")

print(f"\n\n=== Testing web_crawler_tool with URL: {url} ===\n")

# Test web_crawler_tool
result = crawl_website(
    start_url=url,
    max_pages=1,
    max_depth=0,
    output_format=["text", "html", "links", "metadata"],
    delay_seconds=1.0
)

print(f"Web crawler result: {result.keys() if result else None}")

print(f"\n\n=== Testing sitemap_crawler with URL: {url} ===\n")

# Test sitemap_crawler
sitemap_crawler = SitemapCrawlerTool()
sitemap_result = sitemap_crawler._run(
    url=url,
    user_id=1,
    max_sitemap_urls_to_process=1,
    max_sitemap_retriever_pages=10,
    requests_per_second=1.0,
    output_format="text,html,links,metadata"
)

print(f"Sitemap crawler result: {sitemap_result[:100] if sitemap_result else None}...")

print("\n=== Test completed ===")
