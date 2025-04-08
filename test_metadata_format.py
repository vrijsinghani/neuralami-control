"""
Test script to verify the metadata formatting in the CSV file.
Run with: python manage.py shell < test_metadata_format.py
"""
import sys
import csv
import io
import logging
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
output_format = ["metadata"]

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
    
    # Create a CSV file in memory
    csv_buffer = io.StringIO()
    csv_writer = csv.writer(csv_buffer, dialect='excel', lineterminator='\n', quoting=csv.QUOTE_ALL)
    
    # Determine which columns to include based on the content in the results
    columns = ['URL', 'Title']
    has_metadata = any('metadata' in item for item in result['results'])
    
    if has_metadata:
        columns.append('Metadata')
    
    # Write the header row
    csv_writer.writerow(columns)
    
    # Write each result row
    for item in result['results']:
        url_item = item.get('url', '')
        title_item = item.get('title', '')
        
        # Prepare the row data
        row_data = [url_item, title_item]
        
        # Add metadata if available and requested
        if has_metadata:
            if 'metadata' in item and item['metadata']:
                if isinstance(item['metadata'], dict):
                    # Format metadata with each tag on its own line
                    metadata_count = len(item['metadata'])
                    metadata_text = f"{metadata_count} metadata tags found:\n"
                    
                    # Add each metadata tag on its own line
                    for i, (key, value) in enumerate(sorted(item['metadata'].items())):
                        if value:  # Only include non-empty values
                            # Clean the value to avoid CSV formatting issues
                            clean_value = str(value).replace('"', '').replace(',', ' ')
                            # Truncate very long values
                            if len(clean_value) > 100:
                                clean_value = clean_value[:100] + '...'
                            metadata_text += f"{i+1}. {key}: {clean_value}\n"
                    
                    row_data.append(metadata_text)
                else:
                    row_data.append(str(item['metadata']))
            else:
                row_data.append('')
        
        # Write the row to the CSV
        csv_writer.writerow(row_data)
    
    # Get the CSV content
    csv_content = csv_buffer.getvalue()
    
    # Print the CSV content
    print("\n=== CSV Content ===")
    print(csv_content)
    
    # Print the metadata from the first result
    if result['results'] and 'metadata' in result['results'][0]:
        metadata = result['results'][0]['metadata']
        if isinstance(metadata, dict):
            print(f"\n=== Metadata from first result ({len(metadata)} tags) ===")
            for i, (key, value) in enumerate(sorted(metadata.items())[:10]):  # Show first 10 metadata tags
                print(f"{i+1}. {key}: {value}")
            if len(metadata) > 10:
                print(f"... and {len(metadata) - 10} more metadata tags")
else:
    print(f"\n=== Function returned result of type {type(result)} ===")
    print(f"Result: {result}")

print("\n=== Test completed ===")
