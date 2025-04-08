"""
Test script to verify the CSV format of the web crawler tool.
Run with: python manage.py shell < test_csv_format.py
"""
import sys
import csv
import io
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
if isinstance(result, dict) and 'results' in result:
    print(f"\n=== Tool returned result with {len(result['results'])} pages ===")
    
    # Create a CSV file in memory
    csv_buffer = io.StringIO()
    csv_writer = csv.writer(csv_buffer, dialect='excel', lineterminator='\n', quoting=csv.QUOTE_ALL)
    
    # Determine which columns to include based on the content in the results
    columns = ['URL', 'Title']
    has_text = any('text' in item for item in result['results'])
    has_html = any('html' in item for item in result['results'])
    has_metadata = any('metadata' in item for item in result['results'])
    has_links = any('links' in item for item in result['results'])
    has_screenshot = any('screenshot' in item for item in result['results'])
    
    if has_text:
        columns.append('Text')
    if has_html:
        columns.append('HTML')
    if has_metadata:
        columns.append('Metadata')
    if has_links:
        columns.append('Links')
    if has_screenshot:
        columns.append('Screenshot')
    
    # Write the header row
    csv_writer.writerow(columns)
    
    # Write each result row
    for item in result['results']:
        url_item = item.get('url', '')
        title_item = item.get('title', '')
        
        # Prepare the row data
        row_data = [url_item, title_item]
        
        # Add text content if available and requested
        if has_text:
            if 'text' in item and item['text']:
                # Truncate text to first 500 characters for CSV
                text = item['text'][:500] + '...' if len(item['text']) > 500 else item['text']
                # Replace newlines with spaces for CSV
                text = text.replace('\n', ' ').replace('\r', '')
                row_data.append(text)
            else:
                row_data.append('')
        
        # Add HTML content if available and requested
        if has_html:
            if 'html' in item and item['html']:
                # Just indicate HTML is available (too large for CSV)
                row_data.append('HTML content available')
            else:
                row_data.append('')
        
        # Add metadata if available and requested
        if has_metadata:
            if 'metadata' in item and item['metadata']:
                if isinstance(item['metadata'], dict):
                    # Format key metadata fields
                    meta_parts = []
                    for key, value in item['metadata'].items():
                        if value:  # Only include non-empty values
                            meta_parts.append(f"{key}: {value}")
                    metadata_text = '; '.join(meta_parts)
                    row_data.append(metadata_text)
                else:
                    row_data.append(str(item['metadata']))
            else:
                row_data.append('')
        
        # Add links if available and requested
        if has_links:
            if 'links' in item and item['links']:
                if isinstance(item['links'], list):
                    # Format the first few links
                    links_text = f"{len(item['links'])} links found"
                    row_data.append(links_text)
                else:
                    row_data.append(str(item['links']))
            else:
                row_data.append('')
        
        # Add screenshot indicator if available and requested
        if has_screenshot:
            if 'screenshot' in item and item['screenshot']:
                row_data.append('Screenshot available')
            else:
                row_data.append('')
        
        # Write the row to the CSV
        csv_writer.writerow(row_data)
    
    # Get the CSV content
    csv_content = csv_buffer.getvalue()
    
    # Print the CSV content
    print("\n=== CSV Content ===")
    print(csv_content)
else:
    print(f"\n=== Tool returned result of type {type(result)} ===")
    print(f"Result: {result}")

print("\n=== Test completed ===")
