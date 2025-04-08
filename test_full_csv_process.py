"""
Test script to simulate the entire CSV generation process.
Run with: python manage.py shell < test_full_csv_process.py
"""
import sys
import csv
import io
import logging
from django.core.files.base import ContentFile
from core.storage import SecureFileStorage
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
max_pages = 1
max_depth = 0
output_format = ["text", "metadata", "links"]
user_id = 1

print(f"\n\n=== Testing full CSV process with URL: {website_url} ===\n")

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
                # Truncate text to first 100 characters for display
                text = item['text'][:100] + '...' if len(item['text']) > 100 else item['text']
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
                    metadata_text = '; '.join(meta_parts[:3])  # Show first 3 metadata items
                    if len(meta_parts) > 3:
                        metadata_text += f"; ... and {len(meta_parts) - 3} more"
                    row_data.append(metadata_text)
                else:
                    row_data.append(str(item['metadata']))
            else:
                row_data.append('')
        
        # Add links if available and requested
        if has_links:
            if 'links' in item and item['links']:
                if isinstance(item['links'], list):
                    # Format all links for CSV output
                    links_count = len(item['links'])
                    
                    # Create a properly formatted list of all links
                    # Use line breaks (\n) to separate links within the cell
                    links_text = f"{links_count} links found:\n"
                    
                    for i, link in enumerate(item['links']):
                        if isinstance(link, dict) and 'href' in link:
                            # Format each link with its URL and text (if available)
                            link_href = link.get('href', '')
                            link_text = link.get('text', '').strip()
                            
                            # Clean the link text to avoid CSV formatting issues
                            if link_text:
                                # Replace commas and quotes to avoid CSV parsing issues
                                clean_text = link_text.replace('"', '').replace(',', ' ')
                                # Truncate very long text
                                clean_text = clean_text[:50] + '...' if len(clean_text) > 50 else clean_text
                                links_text += f"{i+1}. {link_href} ({clean_text})\n"
                            else:
                                links_text += f"{i+1}. {link_href}\n"
                        elif isinstance(link, str):
                            links_text += f"{i+1}. {link}\n"
                    
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
    
    # Save the CSV file
    crawl_storage = SecureFileStorage()
    csv_filename = f"{user_id}/crawled_websites/test_csv_output.csv"
    csv_path = crawl_storage.save(csv_filename, ContentFile(csv_content.encode('utf-8')))
    csv_url = crawl_storage.url(csv_path)
    
    print(f"\nCSV file saved to: {csv_path}")
    print(f"CSV URL: {csv_url}")
    
    # Print the CSV content
    print("\n=== CSV Content ===")
    print(csv_content)
    
    # Save a local copy for inspection
    with open('test_full_csv.csv', 'w', newline='') as f:
        f.write(csv_content)
    
    print("\nLocal CSV file saved to: test_full_csv.csv")
else:
    print(f"\n=== Function returned result of type {type(result)} ===")
    print(f"Result: {result}")

print("\n=== Test completed ===")
