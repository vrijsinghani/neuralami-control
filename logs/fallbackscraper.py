import requests
from urllib.parse import quote
from bs4 import BeautifulSoup
import logging
import sys
import os
import importlib.util
import types

# Set up basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Define the scrapper host
SCRAPPER_HOST = "scrapper.rijsinghani.us"

# Define excluded URL patterns
EXCLUDED_URLS = [
    'facebook.com',
    'twitter.com',
    'instagram.com',
    'linkedin.com',
    'youtube.com',
    'tiktok.com',
    'pinterest.com',
    'reddit.com',
]

# Create a mock Django settings module
class MockSettings:
    SCRAPPER_HOST = SCRAPPER_HOST
    SCRAPPER_PROXY_HOST = None

# Create a mock django.conf module with settings
mock_conf = types.ModuleType('django.conf')
mock_conf.settings = MockSettings()

# Add it to sys.modules
sys.modules['django.conf'] = mock_conf

# Now we can import from scrape_url.py
try:
    # Get the path to the scrape_url.py file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, '..'))
    scrape_url_path = os.path.join(project_root, 'apps', 'agents', 'utils', 'scrape_url.py')
    
    # Load the module
    spec = importlib.util.spec_from_file_location("scrape_url_module", scrape_url_path)
    scrape_url_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scrape_url_module)
    
    # Get the functions we need
    scrape_url = scrape_url_module.scrape_url
    get_url_links = scrape_url_module.get_url_links
    
    # Update the EXCLUDED_URL_PATTERNS in the imported module
    scrape_url_module.EXCLUDED_URL_PATTERNS = EXCLUDED_URLS
    
    logger.info("Successfully imported functions from scrape_url.py")
except Exception as e:
    logger.error(f"Failed to import from scrape_url.py: {e}")
    
    # Fallback to our own implementation if import fails
    def scrape_url(url, **kwargs):
        logger.warning("Using fallback scrape_url implementation")
        
        # Check excluded URLs
        for pattern in EXCLUDED_URLS:
            if pattern in url:
                logger.info(f"URL {url} is excluded, skipping scrape")
                return None
                
        # Check additional excluded URLs if provided
        excluded_urls = kwargs.get('excluded_urls')
        if excluded_urls:
            for pattern in excluded_urls:
                if pattern in url:
                    logger.info(f"URL {url} is in the additional exclusion list, skipping scrape")
                    return None
        
        try:
            response = requests.get(
                f"https://{SCRAPPER_HOST}/api/article",
                params={'url': url},
                timeout=300
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"Error in fallback scrape_url: {e}")
            return None
    
    def get_url_links(url, **kwargs):
        logger.warning("Using fallback get_url_links implementation")
        
        # Check excluded URLs
        for pattern in EXCLUDED_URLS:
            if pattern in url:
                logger.info(f"URL {url} is excluded, skipping link extraction")
                return None
                
        # Check additional excluded URLs if provided
        excluded_urls = kwargs.get('excluded_urls')
        if excluded_urls:
            for pattern in excluded_urls:
                if pattern in url:
                    logger.info(f"URL {url} is in the additional exclusion list, skipping link extraction")
                    return None
        
        try:
            response = requests.get(
                f"https://{SCRAPPER_HOST}/api/links",
                params={'url': url},
                timeout=300
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"Error in fallback get_url_links: {e}")
            return None

# Example usage
if __name__ == "__main__":
    # Example URLs - one normal, one excluded
    target_url = "https://www.yelp.com/search?find_desc=jacksonville+flooring+stores&find_loc=Jacksonville%2C+FL&src=opensearch"
    excluded_url = "https://www.facebook.com/some_page"
    
    # Additional excluded patterns for this specific run
    additional_excluded = ["yelp.com/biz"]
    
    print("\n=== Testing URL exclusion functionality ===")
    
    # Test 1: Normal URL
    print(f"\nTest 1: Normal URL - {target_url}")
    content_result = scrape_url(target_url, use_direct_request_first=True)
    if content_result:
        print(f"Successfully retrieved content from {target_url}")
        print(f"Title: {content_result.get('title')}")
        print(f"Excerpt: {content_result.get('excerpt')}")
        print(f"Content length: {content_result.get('length')}")
    else:
        print(f"Failed to retrieve content from {target_url}")
    
    # Test 2: Excluded URL
    print(f"\nTest 2: Excluded URL - {excluded_url}")
    content_result = scrape_url(excluded_url, use_direct_request_first=True)
    if content_result:
        print(f"Successfully retrieved content from {excluded_url}")
        print(f"Title: {content_result.get('title')}")
    else:
        print(f"URL was excluded as expected: {excluded_url}")
    
    # Test 3: URL with additional exclusion pattern
    print(f"\nTest 3: URL with additional exclusion - {target_url} + {additional_excluded}")
    content_result = scrape_url(target_url, use_direct_request_first=True, excluded_urls=additional_excluded)
    if content_result:
        print(f"Successfully retrieved content from {target_url}")
        print(f"Title: {content_result.get('title')}")
    else:
        print(f"URL was excluded by additional pattern as expected: {target_url}")
    
    # Test 4: Get links from normal URL
    print(f"\nTest 4: Get links from normal URL - {target_url}")
    links_result = get_url_links(target_url, use_direct_request_first=True)
    if links_result:
        links = links_result.get('links', [])
        print(f"Successfully retrieved {len(links)} links from {target_url}")
        for i, link in enumerate(links[:3], 1):  # Print first 3 links
            print(f"{i}. {link.get('text')} - {link.get('url')}")
        if len(links) > 3:
            print(f"... and {len(links) - 3} more links")
    else:
        print(f"Failed to retrieve links from {target_url}")
    
    # Test 5: Get links from excluded URL
    print(f"\nTest 5: Get links from excluded URL - {excluded_url}")
    links_result = get_url_links(excluded_url, use_direct_request_first=True)
    if links_result:
        links = links_result.get('links', [])
        print(f"Successfully retrieved {len(links)} links from {excluded_url}")
    else:
        print(f"URL was excluded as expected: {excluded_url}")