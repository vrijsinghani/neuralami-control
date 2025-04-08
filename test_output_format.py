"""
Test script to verify the output format of the web crawler tool.
Run with: python manage.py shell < test_output_format.py
"""
import sys
import json
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
print(f"\n=== Tool returned result with keys: {list(result.keys() if isinstance(result, dict) else [])} ===")

# Print the keys for each result to see what formats were retrieved
if isinstance(result, dict) and 'results' in result:
    for i, page in enumerate(result['results']):
        print(f"\nPage {i+1}: {page.get('url')}")
        print(f"Retrieved formats: {list(page.keys())}")
        
        # Check if we got the requested formats
        for fmt in formats:
            if fmt in page:
                print(f"✅ {fmt} format was retrieved")
                
                # Print a sample of the content
                if fmt == 'text':
                    text_sample = page[fmt][:100] + '...' if isinstance(page[fmt], str) and len(page[fmt]) > 100 else page[fmt]
                    print(f"Text sample: {text_sample}")
                elif fmt == 'metadata':
                    if isinstance(page[fmt], dict):
                        print(f"Metadata keys: {list(page[fmt].keys())}")
                        for key, value in page[fmt].items():
                            print(f"  {key}: {value}")
                    else:
                        print(f"Metadata (not a dict): {page[fmt]}")
                elif fmt == 'screenshot':
                    if isinstance(page[fmt], str):
                        print(f"Screenshot length: {len(page[fmt])} characters")
                    else:
                        print(f"Screenshot (not a string): {type(page[fmt])}")
            else:
                print(f"❌ {fmt} format was NOT retrieved")
else:
    print("No results found in the response or response is not a dictionary")
    print(f"Response type: {type(result)}")
    print(f"Response: {result}")

# Save the result to a file for inspection
try:
    with open('crawler_result.json', 'w') as f:
        # Convert the result to a serializable format
        if isinstance(result, dict):
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
                    page_copy['text'] = page['text'][:500] + '...' if len(page['text']) > 500 else page['text']
                    
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
                    else:
                        page_copy['links'] = str(page['links'])
                    
                # Add screenshot indicator if available
                if 'screenshot' in page:
                    page_copy['has_screenshot'] = True
                    
                serializable_result['results'].append(page_copy)
            
            json.dump(serializable_result, f, indent=2)
        else:
            json.dump({'error': 'Result is not a dictionary', 'result_type': str(type(result))}, f, indent=2)
        
    print("\nSaved result to crawler_result.json for inspection")
except Exception as e:
    print(f"Error saving result to file: {e}")

print("\n=== Test completed ===")
