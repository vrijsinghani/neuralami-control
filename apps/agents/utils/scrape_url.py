import requests
import logging
import json
from django.conf import settings
from urllib.parse import quote, urlparse
from bs4 import BeautifulSoup
import re
# Import utilities for content type detection
from apps.common.utils import is_pdf_url, is_youtube
# Import loaders for PDF and YouTube content
from langchain_community.document_loaders import YoutubeLoader, PyMuPDFLoader
# Import CompressionTool for processing large content
from apps.agents.tools.compression_tool.compression_tool import CompressionTool

logger = logging.getLogger(__name__)

# List of URL patterns to exclude from scraping
# These can be exact domains or regex patterns
EXCLUDED_URL_PATTERNS = [
    # Example patterns (uncomment or add your own):
    # 'facebook.com',
    # 'twitter.com',
    # 'instagram.com',
    # 'linkedin.com',
    # r'.*\.pdf$',  # PDF files
    'yelp.com',
]

def is_excluded_url(url):
    """
    Check if a URL should be excluded from scraping based on predefined patterns.
    
    Args:
        url (str): The URL to check
        
    Returns:
        bool: True if the URL should be excluded, False otherwise
    """
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    
    for pattern in EXCLUDED_URL_PATTERNS:
        # Check if it's a regex pattern (starts with r')
        if pattern.startswith('r\'') and pattern.endswith('\''):
            # Extract the actual regex pattern
            regex = pattern[2:-1]
            if re.search(regex, url, re.IGNORECASE):
                logger.info(f"URL {url} excluded by regex pattern: {regex}")
                return True
        # Check if domain contains the pattern
        elif pattern in domain:
            logger.info(f"URL {url} excluded by domain pattern: {pattern}")
            return True
    
    return False

def _load_from_youtube(url: str) -> dict:
    """
    Load and process YouTube video content using YoutubeLoader.
    
    Args:
        url (str): YouTube video URL
        
    Returns:
        dict: Processed YouTube content with transcript and metadata
    """
    try:
        logger.info(f"Loading YouTube content from: {url}")
        loader = YoutubeLoader.from_youtube_url(url)
        docs = loader.load()
        
        if not docs:
            logger.error(f"No content extracted from YouTube video: {url}")
            return None
            
        page_content = "".join(doc.page_content for doc in docs)
        metadata = docs[0].metadata
        
        # Create output string with metadata and page_content
        transcript = f"Title: {metadata.get('title')}\n\n"
        transcript += f"Description: {metadata.get('description')}\n\n"
        transcript += f"View Count: {metadata.get('view_count')}\n\n"
        transcript += f"Author: {metadata.get('author')}\n\n"
        transcript += f"Category: {metadata.get('category')}\n\n"
        transcript += f"Source: {metadata.get('source')}\n\n"
        transcript += f"Page Content:\n{page_content}"
        
        # Check if content is too large and needs compression
        if len(transcript) > 500000:
            logger.info(f"YouTube content from {url} exceeds 500,000 characters. Compressing...")
            compressed_content = _compress_large_content(transcript)
            # Use compressed content if compression succeeded
            if compressed_content:
                logger.info(f"Successfully compressed YouTube content from {url}")
                transcript = compressed_content
                page_content = compressed_content  # Update page_content as well
        
        # Create result in the scrape_url format
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        
        result = {
            'url': url,
            'domain': domain,
            'title': metadata.get('title', ''),
            'byline': metadata.get('author', ''),
            'content': transcript,  # Full formatted content
            'textContent': page_content,
            'excerpt': page_content[:200] + "..." if len(page_content) > 200 else page_content,
            'length': len(page_content),
            'meta': {
                'general': {
                    'author': metadata.get('author', ''),
                    'description': metadata.get('description', ''),
                },
                'youtube': metadata,
                'contentType': 'youtube',
                'compressed': len(transcript) > 500000
            }
        }
        
        logger.info(f"Successfully loaded YouTube content from: {url}")
        return result
        
    except Exception as e:
        logger.error(f"Error loading YouTube content from {url}: {str(e)}")
        return None

def _load_from_pdf(url: str) -> dict:
    """
    Load and process PDF content using PyMuPDFLoader.
    
    Args:
        url (str): PDF document URL
        
    Returns:
        dict: Processed PDF content with text and metadata
    """
    try:
        logger.info(f"Loading PDF content from: {url}")
        loader = PyMuPDFLoader(url)
        docs = loader.load()
        
        if not docs:
            logger.error(f"No content extracted from PDF: {url}")
            return None
            
        pdf_text = "".join(doc.page_content for doc in docs)
        
        # Check if content is too large and needs compression
        was_compressed = False
        if len(pdf_text) > 500000:
            logger.info(f"PDF content from {url} exceeds 500,000 characters. Compressing...")
            compressed_content = _compress_large_content(pdf_text)
            # Use compressed content if compression succeeded
            if compressed_content:
                logger.info(f"Successfully compressed PDF content from {url}")
                pdf_text = compressed_content
                was_compressed = True
        
        # Extract filename from URL
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        filename = parsed_url.path.split('/')[-1]
        
        # Create result in the scrape_url format
        result = {
            'url': url,
            'domain': domain,
            'title': filename,
            'byline': '',
            'content': pdf_text,  # Full PDF text
            'textContent': pdf_text,
            'excerpt': pdf_text[:200] + "..." if len(pdf_text) > 200 else pdf_text,
            'length': len(pdf_text),
            'meta': {
                'general': {
                    'filename': filename,
                },
                'contentType': 'pdf',
                'pageCount': len(docs),
                'compressed': was_compressed
            }
        }
        
        logger.info(f"Successfully loaded PDF content from: {url}")
        return result
        
    except Exception as e:
        logger.error(f"Error loading PDF content from {url}: {str(e)}")
        return None

def _compress_large_content(content: str) -> str:
    """
    Compress large content using CompressionTool.
    
    Args:
        content (str): Content to compress
        
    Returns:
        str: Compressed content or original content if compression fails
    """
    try:
        logger.info(f"Compressing content of length {len(content)}")
        
        # Initialize the compression tool
        compression_tool = CompressionTool()
        
        # Call the tool with appropriate parameters
        # Setting a smaller max_tokens to ensure significant compression
        result_json = compression_tool._run(
            content=content,
            max_tokens=16384,  # This is a reasonable size that balances detail and compression
            detail_level="detailed"  # Use "detailed" to preserve important information
        )
        
        result = json.loads(result_json)
        
        # Check if compression was successful
        if "processed_content" in result:
            compressed_content = result["processed_content"]
            original_tokens = result.get("original_tokens", 0)
            final_tokens = result.get("final_tokens", 0)
            reduction_ratio = result.get("reduction_ratio", 0)
            
            logger.info(f"Content compressed: original tokens: {original_tokens}, "
                        f"final tokens: {final_tokens}, reduction ratio: {reduction_ratio}")
            
            return compressed_content
        else:
            logger.error(f"Compression failed: {result.get('error', 'Unknown error')}")
            return content  # Return original content if compression fails
            
    except Exception as e:
        logger.error(f"Error compressing content: {str(e)}")
        return content  # Return original content if compression fails

def scrape_url(url, cache=True, full_content=False, stealth=False, screenshot=False, 
               user_scripts_timeout=0, incognito=False, timeout=60000, 
               wait_until="domcontentloaded", sleep=0, device="iPhone 12", 
               scroll_down=0, ignore_https_errors=True, max_elems_to_parse=0, 
               nb_top_candidates=5, char_threshold=100, 
               resource="document",
               use_direct_request_first=True,
               excluded_urls=None):
    """
    Retrieves content of a URL using a standard request first, then falling back to the configured scrapper service if needed.
    Support for PDF documents and YouTube videos has been added.
    
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
        resource (str): Comma-separated list of resource types to allow (document,stylesheet,image,media,font,script,texttrack,xhr,fetch,eventsource,websocket,manifest,other)
        use_direct_request_first (bool): Whether to try a direct request before using the scrapper service
        excluded_urls (list): Additional list of URL patterns to exclude from scraping
    
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
    # Check if URL should be excluded
    if is_excluded_url(url):
        logger.info(f"URL {url} is in the exclusion list, skipping scrape")
        return None
    
    # Check additional excluded URLs if provided
    if excluded_urls:
        for pattern in excluded_urls:
            if pattern in url:
                logger.info(f"URL {url} is in the additional exclusion list, skipping scrape")
                return None
    
    # Check if URL is a YouTube video
    if is_youtube(url):
        logger.info(f"Detected YouTube URL: {url}")
        return _load_from_youtube(url)
    
    # Check if URL is a PDF
    if is_pdf_url(url):
        logger.info(f"Detected PDF URL: {url}")
        return _load_from_pdf(url)
    
    # Try direct request first if enabled
    if use_direct_request_first:
        try:
            logger.info(f"Attempting direct request to URL: {url}")
            
            # Set up headers to mimic a browser
            # 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            headers = {
                'User-Agent': 'ChatGPT-User',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Cache-Control': 'max-age=0',
            }
            
            # Make direct request
            direct_response = requests.get(
                url,
                headers=headers,
                timeout=30,  # 30 seconds timeout for direct request
                verify=not ignore_https_errors
            )
            
            # Check if response is HTML and has sufficient content
            content_type = direct_response.headers.get('Content-Type', '')
            is_html = 'text/html' in content_type.lower()
            logger.info(f"Direct request response: {direct_response.status_code}, {content_type}, {is_html}, {len(direct_response.text)}")
            if direct_response.status_code == 200 and len(direct_response.text) > 100:
                # Check if the page contains anti-bot measures or requires JavaScript
                if not _requires_javascript(direct_response.text):
                    # Process the HTML response
                    result = _process_html_response(direct_response, url)
                    if result:
                        logger.info(f"Successfully scraped URL with direct request: {url}, content length: {len(direct_response.text)}")
                        return result
                    else:
                        logger.info(f"Direct request succeeded but processing failed, falling back to scrapper for URL: {url}")
                else:
                    logger.info(f"Direct request detected JavaScript requirement, falling back to scrapper for URL: {url}")
            else:
                logger.info(f"Direct request insufficient (status: {direct_response.status_code}, is_html: {is_html}, length: {len(direct_response.text)}), falling back to scrapper for URL: {url}")
        except Exception as e:
            logger.info(f"Direct request failed, falling back to scrapper for URL {url}: {str(e)}")
    
    # Fall back to scrapper service
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
            'char-threshold': char_threshold,
            'resource': resource
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
        
        # Add content type marker to metadata
        if 'meta' not in result:
            result['meta'] = {}
        result['meta']['contentType'] = 'webpage'
        
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

def _requires_javascript(html_content):
    """
    Check if the page likely requires JavaScript to display content properly.
    
    Args:
        html_content (str): The HTML content to check
        
    Returns:
        bool: True if the page likely requires JavaScript, False otherwise
    """
    # Check for common JavaScript-only content indicators
    js_indicators = [
        # Cloudflare protection
        'cf-browser-verification',
        'cf_chl_prog',
        'challenge-form',
        # JavaScript-only content loaders
        'window.location.reload',
        'document.getElementById("challenge")',
        # Common anti-bot measures
        'captcha',
        'recaptcha',
        # Empty body with scripts
        '<body></body>',
        r'<body>\s*<script',
        # JavaScript frameworks that require client-side rendering
        'ng-app',
        'react-root',
        'vue-app',
        'data-reactroot',
        # # Lazy loading indicators
        # 'lazyload',
        # 'lazy-load',
    ]
    
    # Check if the page has a very small content size but lots of scripts
    soup = BeautifulSoup(html_content, 'html.parser')
    body = soup.find('body')
    
    if not body:
        return True
    
    # If body text is very small but has scripts, likely needs JS
    body_text = body.get_text(strip=True)
    scripts = soup.find_all('script')
    
    if len(body_text) < 500 and len(scripts) > 5:
        return True
    
    # Check for JS indicators
    for indicator in js_indicators:
        if re.search(indicator, html_content, re.IGNORECASE):
            logger.info(f"Detected JavaScript requirement: {indicator}")
            return True
    
    return False

def _process_html_response(response, url):
    """
    Process an HTML response into the same structure as the scrapper service.
    
    Args:
        response (requests.Response): The response object from requests
        url (str): The original URL
        
    Returns:
        dict: Processed content in the same structure as the scrapper service or None if processing fails
    """
    try:
        html_content = response.text
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract domain from URL
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        
        # Extract title
        title = soup.title.string if soup.title else ""
        
        # Extract meta tags
        meta_tags = {}
        for meta in soup.find_all('meta'):
            name = meta.get('name') or meta.get('property')
            content = meta.get('content')
            if name and content:
                meta_tags[name] = content
        
        # Extract OpenGraph and Twitter meta tags
        og_tags = {}
        twitter_tags = {}
        
        for meta in soup.find_all('meta'):
            property_name = meta.get('property') or meta.get('name')
            content = meta.get('content')
            
            if property_name and content:
                if property_name.startswith('og:'):
                    og_tags[property_name[3:]] = content
                elif property_name.startswith('twitter:'):
                    twitter_tags[property_name[8:]] = content
        
        # Extract main content
        # This is a simplified version - the scrapper service likely has more sophisticated content extraction
        main_content = ""
        main_tags = ['article', 'main', 'div[role="main"]', '.content', '#content', '.post', '.article']
        
        for tag_selector in main_tags:
            if '[' in tag_selector:
                # Handle attribute selectors
                tag, attr = tag_selector.split('[', 1)
                attr = attr.rstrip(']')
                attr_name, attr_value = attr.split('=', 1)
                attr_value = attr_value.strip('"\'')
                
                elements = soup.find_all(tag, {attr_name.strip(): attr_value})
            elif tag_selector.startswith('.'):
                # Handle class selectors
                elements = soup.find_all(class_=tag_selector[1:])
            elif tag_selector.startswith('#'):
                # Handle id selectors
                elements = [soup.find(id=tag_selector[1:])]
            else:
                # Handle tag selectors
                elements = soup.find_all(tag_selector)
            
            if elements:
                main_content = max([elem.get_text(strip=True) for elem in elements], key=len)
                break
        
        # If no main content found, use body text
        if not main_content and soup.body:
            main_content = soup.body.get_text(strip=True)
        
        # Extract text content
        text_content = soup.get_text(strip=True)
        
        # Create excerpt (first 200 characters of main content)
        excerpt = main_content[:200] + "..." if len(main_content) > 200 else main_content
        
        # Try to find author/byline
        byline = ""
        byline_selectors = [
            'meta[name="author"]', 
            '.author', 
            '.byline', 
            '.post-author', 
            '[rel="author"]'
        ]
        
        for selector in byline_selectors:
            if '[' in selector:
                tag, attr = selector.split('[', 1)
                attr = attr.rstrip(']')
                attr_name, attr_value = attr.split('=', 1)
                attr_value = attr_value.strip('"\'')
                
                elements = soup.find_all(tag, {attr_name.strip(): attr_value})
                if elements and elements[0].get('content'):
                    byline = elements[0].get('content')
                    break
            elif selector.startswith('.'):
                elements = soup.find_all(class_=selector[1:])
                if elements:
                    byline = elements[0].get_text(strip=True)
                    break
            elif selector.startswith('['):
                attr = selector.strip('[]')
                elements = soup.find_all(attrs={attr: True})
                if elements:
                    byline = elements[0].get_text(strip=True)
                    break
        
        # Construct result in the same format as the scrapper service
        result = {
            'url': url,
            'domain': domain,
            'title': title,
            'byline': byline,
            'content': str(soup),  # Full HTML content
            'textContent': text_content,
            'excerpt': excerpt,
            'length': len(text_content),
            'meta': {
                'general': meta_tags,
                'og': og_tags,
                'twitter': twitter_tags
            }
        }
        
        return result
    
    except Exception as e:
        logger.error(f"Error processing HTML response: {str(e)}")
        return None

def get_url_links(url, cache=True, full_content=False, stealth=False, screenshot=False, 
                 user_scripts_timeout=0, incognito=True, timeout=60000, 
                 wait_until="domcontentloaded", sleep=0, device="iPhone 12", 
                 scroll_down=0, ignore_https_errors=True, text_len_threshold=40,
                 words_threshold=3, resource="document",
                 use_direct_request_first=True,
                 excluded_urls=None):
    """
    Retrieves all links from a URL using a standard request first, then falling back to the configured scrapper service if needed.
    Support for PDF documents and YouTube videos has been added.
    
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
        resource (str): Comma-separated list of resource types to allow (document,stylesheet,image,media,font,script,texttrack,xhr,fetch,eventsource,websocket,manifest,other)
        use_direct_request_first (bool): Whether to try a direct request before using the scrapper service
        excluded_urls (list): Additional list of URL patterns to exclude from scraping
    
    Returns:
        dict: The scraped links and metadata from the URL or None if failed
    
    Response structure includes:
        - url: Original URL
        - domain: Website domain
        - title: Page title
        - links: Array of link objects with url and text properties
        - meta: Metadata (og, twitter tags, etc.)
    """
    # Check if URL should be excluded
    if is_excluded_url(url):
        logger.info(f"URL {url} is in the exclusion list, skipping link extraction")
        return None
    
    # Check additional excluded URLs if provided
    if excluded_urls:
        for pattern in excluded_urls:
            if pattern in url:
                logger.info(f"URL {url} is in the additional exclusion list, skipping link extraction")
                return None
    
    # Check if URL is a YouTube video
    if is_youtube(url):
        logger.info(f"Detected YouTube URL for link extraction: {url}")
        # For YouTube, we can only create a basic link structure without real links
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        
        # Return a minimal links structure for YouTube
        return {
            'url': url,
            'domain': domain,
            'title': "YouTube Video",
            'links': [],  # YouTube videos typically don't have extractable links
            'meta': {
                'contentType': 'youtube'
            }
        }
    
    # Check if URL is a PDF
    if is_pdf_url(url):
        logger.info(f"Detected PDF URL for link extraction: {url}")
        # PDFs don't have links in the same way as web pages
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        filename = parsed_url.path.split('/')[-1]
        
        # Return a minimal links structure for PDF
        return {
            'url': url,
            'domain': domain,
            'title': filename,
            'links': [],  # PDFs typically don't have extractable links in this context
            'meta': {
                'contentType': 'pdf'
            }
        }
    
    # Try direct request first if enabled
    if use_direct_request_first:
        try:
            logger.info(f"Attempting direct request to URL for links: {url}")
            # 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',

            # Set up headers to mimic a browser
            headers = {
                'User-Agent': 'ChatGPT-User',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Cache-Control': 'max-age=0',
            }
            
            # Make direct request
            direct_response = requests.get(
                url,
                headers=headers,
                timeout=30,  # 30 seconds timeout for direct request
                verify=not ignore_https_errors
            )
            
            # Check if response is HTML and has sufficient content
            content_type = direct_response.headers.get('Content-Type', '')
            is_html = 'text/html' in content_type.lower()
            logger.info(f"Direct request response: {direct_response.status_code}, {content_type}, {is_html}, {len(direct_response.text)}")
            if direct_response.status_code == 200 and len(direct_response.text) > 100:
                # Check if the page contains anti-bot measures or requires JavaScript
                if not _requires_javascript(direct_response.text):
                    # Process the HTML response to extract links
                    result = _process_html_links(direct_response, url, text_len_threshold, words_threshold)
                    if result:
                        logger.info(f"Successfully extracted links with direct request: {url}, found {len(result.get('links', []))} links")
                        return result
                    else:
                        logger.info(f"Direct request succeeded but link extraction failed, falling back to scrapper for URL: {url}")
                else:
                    logger.info(f"Direct request detected JavaScript requirement, falling back to scrapper for URL: {url}")
            else:
                logger.info(f"Direct request insufficient (status: {direct_response.status_code}, is_html: {is_html}, length: {len(direct_response.text)}), falling back to scrapper for URL: {url}")
        
        except Exception as e:
            logger.info(f"Direct request failed, falling back to scrapper for URL {url}: {str(e)}")
    
    # Fall back to scrapper service
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
            'words-threshold': words_threshold,
            'resource': resource
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
        
        # Add content type marker to metadata
        if 'meta' not in result:
            result['meta'] = {}
        result['meta']['contentType'] = 'webpage'
        
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

def _process_html_links(response, url, text_len_threshold=40, words_threshold=3):
    """
    Process an HTML response to extract links in the same structure as the scrapper service.
    
    Args:
        response (requests.Response): The response object from requests
        url (str): The original URL
        text_len_threshold (int): Minimum character length for link text
        words_threshold (int): Minimum number of words in link text
        
    Returns:
        dict: Processed links in the same structure as the scrapper service or None if processing fails
    """
    try:
        html_content = response.text
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract domain from URL
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        # Extract title
        title = soup.title.string if soup.title else ""
        
        # Extract meta tags
        meta_tags = {}
        for meta in soup.find_all('meta'):
            name = meta.get('name') or meta.get('property')
            content = meta.get('content')
            if name and content:
                meta_tags[name] = content
        
        # Extract OpenGraph and Twitter meta tags
        og_tags = {}
        twitter_tags = {}
        
        for meta in soup.find_all('meta'):
            property_name = meta.get('property') or meta.get('name')
            content = meta.get('content')
            
            if property_name and content:
                if property_name.startswith('og:'):
                    og_tags[property_name[3:]] = content
                elif property_name.startswith('twitter:'):
                    twitter_tags[property_name[8:]] = content
        
        # Extract links
        links = []
        for a_tag in soup.find_all('a', href=True):
            link_text = a_tag.get_text(strip=True)
            link_url = a_tag['href']
            
            # Skip empty links or javascript links
            if not link_url or link_url.startswith('javascript:'):
                continue
            
            # Convert relative URLs to absolute
            if link_url.startswith('/'):
                link_url = f"{base_url}{link_url}"
            elif not (link_url.startswith('http://') or link_url.startswith('https://')):
                link_url = f"{base_url}/{link_url}"
            
            # Apply filtering criteria
            if len(link_text) >= text_len_threshold and len(link_text.split()) >= words_threshold:
                links.append({
                    'url': link_url,
                    'text': link_text
                })
        
        # Construct result in the same format as the scrapper service
        result = {
            'url': url,
            'domain': domain,
            'title': title,
            'links': links,
            'meta': {
                'general': meta_tags,
                'og': og_tags,
                'twitter': twitter_tags,
                'contentType': 'webpage'
            }
        }
        
        return result
    
    except Exception as e:
        logger.error(f"Error processing HTML response for links: {str(e)}")
        return None 