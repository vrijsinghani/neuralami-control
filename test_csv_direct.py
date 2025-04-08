"""
Test script to directly generate a CSV file with links.
Run with: python manage.py shell < test_csv_direct.py
"""
import sys
import csv
import io
import logging
import os

# Set up logging to see debug messages
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Create sample data
sample_links = [
    {"href": "https://www.example.com/page1", "text": "Example Page 1"},
    {"href": "https://www.example.com/page2", "text": "Example Page 2"},
    {"href": "https://www.example.com/page3", "text": "Example Page 3"},
    {"href": "https://www.example.com/page4", "text": "Example Page 4"},
    {"href": "https://www.example.com/page5", "text": "Example Page 5"}
]

# Create a CSV file
with open('test_links.csv', 'w', newline='') as csvfile:
    csv_writer = csv.writer(csvfile, dialect='excel', lineterminator='\n', quoting=csv.QUOTE_ALL)
    
    # Write header
    csv_writer.writerow(['URL', 'Title', 'Text', 'Links'])
    
    # Write data
    url = "https://www.example.com"
    title = "Example Website"
    text = "This is some example text content."
    
    # Format links
    links_count = len(sample_links)
    links_text = f"{links_count} links found:\n"
    
    for i, link in enumerate(sample_links):
        link_href = link.get('href', '')
        link_text = link.get('text', '').strip()
        
        if link_text:
            links_text += f"{i+1}. {link_href} ({link_text})\n"
        else:
            links_text += f"{i+1}. {link_href}\n"
    
    # Write row
    csv_writer.writerow([url, title, text, links_text])

# Check if the file was created
if os.path.exists('test_links.csv'):
    print(f"CSV file created: test_links.csv")
    print(f"File size: {os.path.getsize('test_links.csv')} bytes")
    
    # Read and print the file contents
    with open('test_links.csv', 'r') as f:
        content = f.read()
        print("\nCSV file contents:")
        print(content)
else:
    print("Failed to create CSV file")

print("\n=== Test completed ===")
