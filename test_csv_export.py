"""
Test script to verify that HTML content is properly included in CSV exports.
Run with: python manage.py shell < test_csv_export.py
"""
import sys
import logging
from apps.crawl_website.export_utils import save_crawl_results
from core.storage import SecureFileStorage

# Set up logging to see debug messages
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Test data with HTML content
test_results = [
    {
        'url': 'https://example.com',
        'title': 'Example Domain',
        'text': 'This domain is for use in illustrative examples in documents.',
        'html': '<html><head><title>Example Domain</title></head><body><h1>Example Domain</h1><p>This domain is for use in illustrative examples in documents.</p></body></html>',
        'metadata': {
            'title': 'Example Domain',
            'description': 'Example domain for testing',
        },
        'links': [
            {'href': 'https://example.com/page1', 'text': 'Page 1'},
            {'href': 'https://example.com/page2', 'text': 'Page 2'},
        ],
        'screenshot': 'base64encodedscreenshot'
    },
    {
        'url': 'https://example.org',
        'title': 'Example.org',
        'text': 'This is another example domain.',
        'html': '<html><head><title>Example.org</title></head><body><h1>Example.org</h1><p>This is another example domain.</p></body></html>',
        'metadata': {
            'title': 'Example.org',
            'description': 'Another example domain',
        },
        'links': [
            {'href': 'https://example.org/page1', 'text': 'Page 1'},
            {'href': 'https://example.org/page2', 'text': 'Page 2'},
        ],
        'screenshot': 'base64encodedscreenshot'
    }
]

print("\n\n=== Testing CSV export with HTML content ===\n")

# Test saving as text with CSV
_, csv_file_url = save_crawl_results(
    results=test_results,
    url='https://example.com',
    user_id=1,
    output_format='text',
    storage=SecureFileStorage(),
    save_as_csv=True
)

print(f"CSV file URL: {csv_file_url}")

print("\n=== Test completed ===")
