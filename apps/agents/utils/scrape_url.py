import requests
import logging
import json
from django.conf import settings
from urllib.parse import quote

logger = logging.getLogger(__name__)

def scrape_url(url, cache=True, full_content=False, stealth=True, screenshot=False, 
               user_scripts_timeout=0, incognito=True, timeout=60000, 
               wait_until="domcontentloaded", sleep=0, device="iPhone 12", 
               scroll_down=0, ignore_https_errors=True, max_elems_to_parse=0, 
               nb_top_candidates=5, char_threshold=500):
    """
    Retrieves content of a URL using the configured scrapper service.
    
    Args:
        url (str): The URL to scrape
        cache (bool): Whether to use cached results if available
        full_content (bool): Whether to return full content
        stealth (bool): Whether to use stealth mode
        screenshot (bool): Whether to capture screenshot
        user_scripts_timeout (int): Timeout for user scripts in milliseconds
        incognito (bool): Whether to use incognito mode
        timeout (int): Timeout in milliseconds
        wait_until (str): When to consider navigation successful
        sleep (int): Time to sleep after page load in milliseconds
        device (str): Device to emulate
        scroll_down (int): Number of times to scroll down
        ignore_https_errors (bool): Whether to ignore HTTPS errors
        max_elems_to_parse (int): Maximum elements to parse
        nb_top_candidates (int): Number of top candidates for content extraction
        char_threshold (int): Character threshold for content extraction
    
    Returns:
        dict: The scraped content and metadata from the URL or None if failed
    
    Response structure includes:
        - byline: Author information
        - content: Cleaned HTML content
        - excerpt: Brief description
        - url: Original URL
        - domain: Website domain
        - textContent: Plain text content
        - title: Page title
        - meta: Metadata (og, twitter tags, etc.)
        - and more...
    """
    try:
        # Get scrapper service configuration from settings
        scrapper_host = getattr(settings, 'SCRAPPER_HOST', None)
        scrapper_proxy_host = getattr(settings, 'SCRAPPER_PROXY_HOST', None)
        
        if not scrapper_host:
            logger.error("SCRAPPER_HOST is not configured in settings")
            return None
        
        # Build request URL with all parameters
        encoded_url = quote(url)
        request_url = f"http://{scrapper_host}/api/article"
        
        params = {
            'url': url,
            'cache': str(cache).lower(),
            'full-content': str(full_content).lower(),
            'stealth': str(stealth).lower(),
            'screenshot': str(screenshot).lower(),
            'user-scripts-timeout': user_scripts_timeout,
            'incognito': str(incognito).lower(),
            'timeout': timeout,
            'wait-until': wait_until,
            'sleep': sleep,
            'device': device,
            'scroll-down': scroll_down,
            'ignore-https-errors': str(ignore_https_errors).lower(),
            'max-elems-to-parse': max_elems_to_parse,
            'nb-top-candidates': nb_top_candidates,
            'char-threshold': char_threshold
        }
        
        # Add proxy server parameter if configured
        if scrapper_proxy_host:
            params['proxy-server'] = scrapper_proxy_host
        
        logger.info(f"Scraping URL: {url} using scrapper at {scrapper_host}")
        
        # Make the request
        response = requests.get(
            request_url,
            params=params,
            timeout=300  # Set a reasonable timeout for the HTTP request itself
        )
        
        # Check response status
        if response.status_code != 200:
            logger.error(f"Scrapper service returned status code {response.status_code} for URL {url}")
            return None
        
        # Parse JSON response
        result = response.json()
        logger.info(f"Successfully scraped URL: {url}, content length: {result.get('length', 0)}")
        
        return result
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Request exception when scraping URL {url}: {str(e)}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response for URL {url}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error when scraping URL {url}: {str(e)}")
        return None

def get_url_links(url, cache=True, full_content=False, stealth=False, screenshot=False, 
                 user_scripts_timeout=0, incognito=True, timeout=60000, 
                 wait_until="domcontentloaded", sleep=0, device="iPhone 12", 
                 scroll_down=0, ignore_https_errors=True, text_len_threshold=40,
                 words_threshold=3):
    """
    Retrieves all links from a URL using the configured scrapper service.
    
    Args:
        url (str): The URL to scrape for links
        cache (bool): Whether to use cached results if available
        full_content (bool): Whether to return full content
        stealth (bool): Whether to use stealth mode
        screenshot (bool): Whether to capture screenshot
        user_scripts_timeout (int): Timeout for user scripts in milliseconds
        incognito (bool): Whether to use incognito mode
        timeout (int): Timeout in milliseconds
        wait_until (str): When to consider navigation successful
        sleep (int): Time to sleep after page load in milliseconds
        device (str): Device to emulate
        scroll_down (int): Number of times to scroll down
        ignore_https_errors (bool): Whether to ignore HTTPS errors
        text_len_threshold (int): Minimum character length for link text
        words_threshold (int): Minimum number of words in link text
    
    Returns:
        dict: The scraped links and metadata from the URL or None if failed
    
    Response structure includes:
        - url: Original URL
        - domain: Website domain
        - title: Page title
        - links: Array of link objects with url and text properties
        - meta: Metadata (og, twitter tags, etc.)
    """
    try:
        # Get scrapper service configuration from settings
        scrapper_host = getattr(settings, 'SCRAPPER_HOST', None)
        scrapper_proxy_host = getattr(settings, 'SCRAPPER_PROXY_HOST', None)
        
        if not scrapper_host:
            logger.error("SCRAPPER_HOST is not configured in settings")
            return None
        
        # Build request URL with all parameters
        encoded_url = quote(url)
        request_url = f"http://{scrapper_host}/api/links"
        
        params = {
            'url': url,
            'cache': str(cache).lower(),
            'full-content': str(full_content).lower(), 
            'stealth': str(stealth).lower(),
            'screenshot': str(screenshot).lower(),
            'user-scripts-timeout': user_scripts_timeout,
            'incognito': str(incognito).lower(),
            'timeout': timeout,
            'wait-until': wait_until,
            'sleep': sleep,
            'device': device,
            'scroll-down': scroll_down,
            'ignore-https-errors': str(ignore_https_errors).lower(),
            'text-len-threshold': text_len_threshold,
            'words-threshold': words_threshold
        }
        
        # Add proxy server parameter if configured
        if scrapper_proxy_host:
            params['proxy-server'] = scrapper_proxy_host
        
        logger.info(f"Fetching links from URL: {url} using scrapper at {scrapper_host}")
        
        # Make the request
        response = requests.get(
            request_url,
            params=params,
            timeout=300  # Set a reasonable timeout for the HTTP request itself
        )
        
        # Check response status
        if response.status_code != 200:
            logger.error(f"Scrapper service returned status code {response.status_code} for URL {url}")
            return None
        
        # Parse JSON response
        result = response.json()
        link_count = len(result.get('links', []))
        logger.info(f"Successfully retrieved {link_count} links from URL: {url}")
        
        return result
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Request exception when fetching links from URL {url}: {str(e)}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response for URL {url}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error when fetching links from URL {url}: {str(e)}")
        return None 