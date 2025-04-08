"""
Test script to verify the export utilities.
Run with: python manage.py shell < test_export_utils.py
"""
import sys
import logging
from apps.crawl_website.export_utils import generate_text_content, generate_csv_content, save_crawl_results
from core.storage import SecureFileStorage

# Set up logging to see debug messages
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Test data
test_results = [
    {
        'url': 'https://example.com',
        'title': 'Example Domain',
        'text': 'This domain is for use in illustrative examples in documents.',
        'metadata': {
            'title': 'Example Domain',
            'description': 'Example domain for testing',
            'og:title': 'Example Domain',
            'og:description': 'Example domain for testing'
        },
        'links': [
            {'href': 'https://example.com/page1', 'text': 'Page 1'},
            {'href': 'https://example.com/page2', 'text': 'Page 2'},
            {'href': 'https://example.com/page3', 'text': 'Page 3'}
        ],
        'screenshot': 'base64encodedscreenshot'
    }
]

print("\n\n=== Testing generate_text_content ===\n")
text_content = generate_text_content(test_results)
print(text_content[:500] + "..." if len(text_content) > 500 else text_content)

print("\n\n=== Testing generate_csv_content ===\n")
csv_content = generate_csv_content(test_results)
print(csv_content)

print("\n\n=== Testing save_crawl_results ===\n")
storage = SecureFileStorage()
file_url, csv_url = save_crawl_results(
    results=test_results,
    url='https://example.com',
    user_id=1,
    output_format='text',
    storage=storage,
    save_as_csv=True
)

print(f"File URL: {file_url}")
print(f"CSV URL: {csv_url}")

print("\n=== Test completed ===")
