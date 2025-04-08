"""
Test script to verify the sitemap crawler can handle comma-separated output formats.
Run with: python manage.py shell < test_sitemap_crawler.py
"""
import sys
import logging
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

print(f"\n\n=== Testing SitemapCrawlerTool with output_format: {output_format} ===\n")

# Call the _extract_content method directly with some sample HTML
sample_html = """
<!DOCTYPE html>
<html>
<head>
    <title>Test Page</title>
    <meta name="description" content="This is a test page">
    <meta property="og:title" content="Test Page for OG">
</head>
<body>
    <h1>Test Page</h1>
    <p>This is a test paragraph.</p>
    <a href="https://example.com">Example Link</a>
    <a href="https://test.com">Test Link</a>
</body>
</html>
"""

# Test the _extract_content method
result = tool._extract_content(
    html_content=sample_html,
    content_type="text/html",
    output_format=output_format
)

# Check the result
print(f"\n=== _extract_content returned result with keys: {list(result.keys() if isinstance(result, dict) else [])} ===")

# Print the content of each format
if isinstance(result, dict):
    if 'text' in result:
        print(f"\nText content: {result['text']}")
    
    if 'metadata' in result:
        print(f"\nMetadata: {result['metadata']}")
    
    if 'links' in result:
        print(f"\nLinks: {result['links']}")
else:
    print(f"\nResult is not a dictionary: {result}")

print("\n=== Test completed ===")
