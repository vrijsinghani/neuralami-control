"""
Test script to verify the CSV format of the web crawler tool with a real crawl.
Run with: python manage.py shell < test_real_crawl_csv.py
"""
import sys
import logging
import json
import os
from apps.agents.tools.web_crawler_tool.web_crawler_tool import crawl_website

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
max_pages = 2
max_depth = 1
output_format = ["text", "metadata", "links"]

print(f"\n\n=== Testing crawl_website with URL: {website_url} ===\n")

# Call the crawl_website function directly
result = crawl_website(
    start_url=website_url,
    max_pages=max_pages,
    max_depth=max_depth,
    output_format=output_format,
    delay_seconds=0.1
)

# Check the results
if isinstance(result, dict) and 'results' in result:
    print(f"\n=== Function returned result with {len(result['results'])} pages ===")
    
    # Save the result to a file for inspection
    with open('crawler_result_with_links.json', 'w') as f:
        # Convert the result to a serializable format
        serializable_result = {
            'success': result.get('success', False),
            'message': result.get('message', ''),
            'results': []
        }
        
        # Process each page result
        for page in result.get('results', []):
            page_copy = {
                'url': page.get('url', ''),
                'title': page.get('title', ''),
                'success': page.get('success', False)
            }
            
            # Add text content if available
            if 'text' in page and isinstance(page['text'], str):
                page_copy['text_length'] = len(page['text'])
                
            # Add metadata if available
            if 'metadata' in page:
                if isinstance(page['metadata'], dict):
                    page_copy['metadata'] = page['metadata']
                else:
                    page_copy['metadata'] = str(page['metadata'])
                
            # Add links count if available
            if 'links' in page:
                if isinstance(page['links'], list):
                    page_copy['links_count'] = len(page['links'])
                    # Add the first 5 links as a sample
                    page_copy['links_sample'] = []
                    for i, link in enumerate(page['links'][:5]):
                        if isinstance(link, dict):
                            page_copy['links_sample'].append({
                                'href': link.get('href', ''),
                                'text': link.get('text', '')
                            })
                        else:
                            page_copy['links_sample'].append(str(link))
                else:
                    page_copy['links'] = str(page['links'])
                
            # Add screenshot indicator if available
            if 'screenshot' in page:
                page_copy['has_screenshot'] = True
                
            serializable_result['results'].append(page_copy)
        
        json.dump(serializable_result, f, indent=2)
        
    print(f"\nSaved result to crawler_result_with_links.json for inspection")
    
    # Print the file size
    file_size = os.path.getsize('crawler_result_with_links.json')
    print(f"File size: {file_size} bytes")
    
    # Print a summary of the results
    for i, page in enumerate(result['results']):
        print(f"\nPage {i+1}: {page.get('url')}")
        print(f"Title: {page.get('title', '')}")
        
        if 'text' in page:
            text_length = len(page['text']) if isinstance(page['text'], str) else 0
            print(f"Text length: {text_length} characters")
            
        if 'metadata' in page:
            metadata_count = len(page['metadata']) if isinstance(page['metadata'], dict) else 0
            print(f"Metadata fields: {metadata_count}")
            
        if 'links' in page:
            links_count = len(page['links']) if isinstance(page['links'], list) else 0
            print(f"Links count: {links_count}")
            
        if 'screenshot' in page:
            screenshot_length = len(page['screenshot']) if isinstance(page['screenshot'], str) else 0
            print(f"Screenshot length: {screenshot_length} characters")
else:
    print(f"\n=== Function returned result of type {type(result)} ===")
    print(f"Result: {result}")

print("\n=== Test completed ===")
