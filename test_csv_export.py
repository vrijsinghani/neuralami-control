"""
Test script to verify that meta description is properly included in CSV exports.
Run with: python manage.py shell < test_csv_export.py
"""
import sys
import logging
import io
from apps.crawl_website.export_utils import generate_csv_content, save_crawl_results
from core.storage import SecureFileStorage

# Set up logging to see debug messages
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Test data with various meta description formats
test_results = [
    {
        'url': 'https://example.com',
        'title': 'Example Domain',
        'text': 'This domain is for use in illustrative examples in documents.',
        'html': '<html><head><title>Example Domain</title></head><body><h1>Example Domain</h1><p>This domain is for use in illustrative examples in documents.</p></body></html>',
        'metadata': {
            'title': 'Example Domain',
            'description': 'Standard meta description for testing',
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
            'og:description': 'Open Graph description for testing',
        },
        'links': [
            {'href': 'https://example.org/page1', 'text': 'Page 1'},
            {'href': 'https://example.org/page2', 'text': 'Page 2'},
        ],
        'screenshot': 'base64encodedscreenshot'
    },
    {
        'url': 'https://example.net',
        'title': 'Example.net',
        'text': 'This is a third example domain.',
        'html': '<html><head><title>Example.net</title></head><body><h1>Example.net</h1><p>This is a third example domain.</p></body></html>',
        'metadata': {
            'title': 'Example.net',
            'meta_description': 'Alternative meta description format',
        },
        'links': [
            {'href': 'https://example.net/page1', 'text': 'Page 1'},
            {'href': 'https://example.net/page2', 'text': 'Page 2'},
        ],
        'screenshot': 'base64encodedscreenshot'
    }
]

print("\n\n=== Testing CSV export with Meta Description column ===\n")

# First, test the generate_csv_content function directly
csv_content = generate_csv_content(test_results)
print("Generated CSV Content Preview:")
print("=" * 80)
# Print first few lines of CSV
lines = csv_content.split('\n')
for i, line in enumerate(lines[:10]):  # Print first 10 lines or less
    print(line)
    if i >= 9:
        print("...")
print("=" * 80)

# Check if the meta description column is included
if '"Meta Description"' in csv_content:
    print("\n✅ Meta Description column is included in the CSV export.")
else:
    print("\n❌ Meta Description column is missing from the CSV export.")

# Check if each sample has its description in the right place
descriptions = [
    "Standard meta description for testing",
    "Open Graph description for testing",
    "Alternative meta description format"
]

for desc in descriptions:
    if desc in csv_content:
        print(f"✅ Found description: {desc}")
    else:
        print(f"❌ Missing description: {desc}")

# Now test saving as text with CSV
print("\n=== Testing save_crawl_results function ===\n")
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
