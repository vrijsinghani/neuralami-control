"""
Test script to directly test the Playwright adapter.
Run with: python manage.py shell < test_adapter_direct.py
"""
import sys
import logging
from apps.agents.utils.scraper_adapters.playwright_adapter import PlaywrightAdapter

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

# Create the adapter
adapter = PlaywrightAdapter()

# Test with multiple formats
formats = ["text", "metadata", "screenshot"]

print(f"\n\n=== Testing Playwright adapter with formats: {formats} ===\n")

# Call the adapter directly
result = adapter.scrape(
    url=url,
    formats=formats,
    timeout=60000,
    cache=True,
    stealth=True
)

# Check the results
print(f"\n=== Adapter returned content with keys: {list(result.keys())} ===")

# Print the keys for each result to see what formats were retrieved
for fmt in formats:
    if fmt in result:
        print(f"✅ {fmt} format was retrieved")
    else:
        print(f"❌ {fmt} format was NOT retrieved")

print("\n=== Test completed ===")
