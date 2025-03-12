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
            max_tokens=32767,  # This is a reasonable size that balances detail and compression
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
               user_scripts_timeout=0, incognito=False, timeout=30000, 
               wait_until="domcontentloaded", sleep=0, device="iPhone 12", 
               scroll_down=0, ignore_https_errors=True, max_elems_to_parse=0, 
               nb_top_candidates=5, char_threshold=100, 
               resource="document",
               use_direct_request_first=False,
               excluded_urls=None):
    """
    Retrieves content of a URL using the FireCrawl scrape endpoint.
    Support for PDF documents and YouTube videos has been added.
    
    Args:
        url (str): The URL to scrape
        cache (bool): Whether to use cached results if available
        full_content (bool): Whether to return full content
        stealth (bool): Whether to use stealth mode for challenging websites
        screenshot (bool): Whether to capture screenshot
        user_scripts_timeout (int): Timeout for user scripts in milliseconds
        incognito (bool): Whether to use incognito mode
        timeout (int): Timeout in milliseconds
        wait_until (str): When to consider navigation successful
        sleep (int): Time to sleep after page load in milliseconds (waitFor in FireCrawl)
        device (str): Device to emulate (mobile option in FireCrawl)
        scroll_down (int): Number of times to scroll down
        ignore_https_errors (bool): Whether to ignore HTTPS errors (skipTlsVerification in FireCrawl)
        max_elems_to_parse (int): Maximum elements to parse (not used in FireCrawl)
        nb_top_candidates (int): Number of top candidates for content extraction (not used in FireCrawl)
        char_threshold (int): Character threshold for content extraction (not used in FireCrawl)
        resource (str): Resource types (not used in FireCrawl)
        use_direct_request_first (bool): Not used with FireCrawl
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
    
    # Use FireCrawl scrape endpoint for all other URLs
    try:
        # Use direct URL that we know works
        firecrawl_url = "https://firecrawl.neuralami.ai/v1/scrape"
        
        # Setup request data for FireCrawl scrape endpoint - keep it minimal
        request_data = {
            "url": url,
            "formats": ["markdown", "html"]
        }
        
        # Only add essential parameters
        if sleep > 0:
            request_data["waitFor"] = sleep
            
        # Setup headers - keep it minimal
        headers = {
            "Content-Type": "application/json"
        }
        
        # Log the request for debugging
        logger.info(f"FireCrawl scrape request for URL: {url}")
        
        # Make the request to FireCrawl scrape endpoint
        response = requests.post(
            firecrawl_url,
            headers=headers,
            json=request_data,
            timeout=(30, 300)  # (connect timeout, read timeout)
        )
        
        # Check response status
        if response.status_code != 200:
            logger.error(f"FireCrawl service returned status code {response.status_code} for URL {url}")
            try:
                error_details = response.json()
                logger.error(f"Error details: {error_details}")
            except:
                logger.error(f"Raw error response: {response.text}")
            return None
        
        # Parse response
        scrape_result = response.json()
        
        # Check if scrape was successful
        if not scrape_result.get("success", False):
            logger.error(f"FireCrawl scrape failed for URL {url}: {scrape_result.get('error', 'Unknown error')}")
            return None
        
        # Extract data from response
        data = scrape_result.get("data", {})
        
        # Extract metadata
        metadata = data.get("metadata", {})
        
        # Process HTML content if available
        html_content = data.get("html", "")
        
        # Process markdown content if available
        markdown_content = data.get("markdown", "")
        
        # Process links if available
        links = data.get("links", [])
        
        # Create result in the expected format
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        
        # Extract title and description from metadata
        title = metadata.get("title", "")
        description = metadata.get("description", "")
        
        # Create a structured result similar to the original format
        result = {
            'url': url,
            'domain': domain,
            'title': title,
            'byline': metadata.get("author", ""),
            'content': html_content,  # HTML content
            'textContent': markdown_content,  # Markdown as text content
            'excerpt': description if description else (markdown_content[:200] + "..." if len(markdown_content) > 200 else markdown_content),
            'length': len(markdown_content),
            'meta': {
                'general': {
                    'author': metadata.get("author", ""),
                    'description': description,
                    'language': metadata.get("language", ""),
                    'statusCode': metadata.get("statusCode", 200),
                },
                'og': {},  # FireCrawl doesn't provide Open Graph data separately
                'twitter': {},  # FireCrawl doesn't provide Twitter card data separately
                'contentType': 'html',
                'links': links
            }
        }
        
        # Add screenshot if available
        if screenshot and "screenshot" in data:
            result['meta']['screenshot'] = data["screenshot"]
        
        logger.info(f"Successfully scraped URL with FireCrawl: {url}")
        return result
        
    except Exception as e:
        logger.error(f"Error scraping URL {url} with FireCrawl: {str(e)}")
        return None