"""
Test script to verify that duplicate links are removed from the export.
Run with: python manage.py shell < test_deduplicate_links.py
"""
import sys
import logging
from apps.crawl_website.export_utils import generate_text_content, generate_csv_content

# Set up logging to see debug messages
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Test data with duplicate links
test_results = [
    {
        'url': 'https://example.com',
        'title': 'Example Domain',
        'text': 'This domain is for use in illustrative examples in documents.',
        'metadata': {
            'title': 'Example Domain',
            'description': 'Example domain for testing',
        },
        'links': [
            {'href': 'https://example.com/page1', 'text': 'Page 1'},
            {'href': 'https://example.com/page2', 'text': 'Page 2'},
            {'href': 'https://example.com/page1', 'text': 'Page 1 Again'},  # Duplicate
            {'href': 'https://example.com/page3', 'text': 'Page 3'},
            {'href': 'https://example.com/page2', 'text': 'Page 2 Again'},  # Duplicate
            {'href': 'https://example.com/page4', 'text': 'Page 4'},
        ],
        'screenshot': 'base64encodedscreenshot'
    }
]

print("\n\n=== Testing generate_text_content with duplicate links ===\n")
text_content = generate_text_content(test_results)
print(text_content)

print("\n\n=== Testing generate_csv_content with duplicate links ===\n")
csv_content = generate_csv_content(test_results)
print(csv_content)

print("\n=== Test completed ===")
