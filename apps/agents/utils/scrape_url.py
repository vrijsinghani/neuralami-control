import logging
import json
import re
from urllib.parse import urlparse
from typing import Dict, List, Any, Optional, Union
# Import utilities for content type detection
from apps.common.utils import is_pdf_url, is_youtube
# Import loaders for PDF and YouTube content
from langchain_community.document_loaders import YoutubeLoader, PyMuPDFLoader
# Import CompressionTool for processing large content
from apps.agents.tools.compression_tool.compression_tool import CompressionTool
# Import the scraper service
from .scraper_service import ScraperService

# NOTE: This file has been updated to use the Playwright adapter by default
# The Playwright adapter connects to a self-hosted Playwright service
# that extracts comprehensive metadata from web pages

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

def crawl_website(url, output_type="text", max_pages=100, max_depth=3, include_patterns=None,
                exclude_patterns=None, stay_within_domain=True, cache=True, stealth=False,
                timeout=30000, device=None, excluded_urls=None, adapter_name=None, **kwargs):
    # Use FireCrawl's dedicated crawl adapter for multi-page crawling
    # until Playwright service supports multi-page crawling
    if max_pages > 1 and adapter_name is None:
        adapter_name = "firecrawl_crawl"
    """
    Crawls a website and returns the content in the requested format.
    Uses the Playwright adapter for multi-page crawling.

    Args:
        url (str): The URL to crawl
        output_type (str): Format(s) to return (text, html, links, metadata, full) or comma-separated string
        max_pages (int): Maximum number of pages to crawl
        max_depth (int): Maximum depth to crawl
        include_patterns (list): URL patterns to include in crawl
        exclude_patterns (list): URL patterns to exclude from crawl
        stay_within_domain (bool): Whether to stay within the domain
        cache (bool): Whether to use cached results if available
        stealth (bool): Whether to use stealth mode for challenging websites
        timeout (int): Timeout in milliseconds
        device (str): Device to emulate (e.g., "mobile" or "desktop")
        excluded_urls (list): Additional list of URL patterns to exclude from scraping
        adapter_name (str): Name of the adapter to use (defaults to "playwright")
        **kwargs: Additional provider-specific parameters

    Returns:
        dict: The crawled content and metadata from the website or None if failed
    """
    # Check if URL should be excluded
    if is_excluded_url(url):
        logger.info(f"URL {url} is in the exclusion list, skipping crawl")
        return None

    # Check additional excluded URLs if provided
    if excluded_urls:
        for pattern in excluded_urls:
            if pattern in url:
                logger.info(f"URL {url} is in the additional exclusion list, skipping crawl")
                return None

    # Check if URL is a YouTube video
    if is_youtube(url):
        logger.info(f"Detected YouTube URL: {url}")
        return _load_from_youtube(url)

    # Check if URL is a PDF
    if is_pdf_url(url):
        logger.info(f"Detected PDF URL: {url}")
        return _load_from_pdf(url)

    # Use the scraper service for all other URLs
    try:
        # Initialize the scraper service
        scraper_service = ScraperService(adapter_name)

        # Determine if mobile device is requested
        mobile = device == "mobile" if device else False

        # Crawl the website
        crawl_result = scraper_service.scrape(
            url=url,
            output_types=output_type,
            timeout=timeout,
            mobile=mobile,
            stealth=stealth,
            cache=cache,
            max_pages=max_pages,
            max_depth=max_depth,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            stay_within_domain=stay_within_domain,
            **kwargs
        )

        # Check if crawl was successful
        if "error" in crawl_result:
            logger.error(f"Crawl failed for URL {url}: {crawl_result['error']}")
            return None

        # Process the crawl results
        # For crawl, we get a dictionary of URLs to their content
        # We'll combine them into a single result
        combined_result = {
            'url': url,
            'domain': urlparse(url).netloc,
            'pages': [],
            'links': [],
            'meta': {
                'crawled_pages': len(crawl_result) if isinstance(crawl_result, dict) else 1,
                'crawl_depth': max_depth,
                'max_pages': max_pages
            }
        }

        # Process the crawl result based on its structure
        # Check if it's a dictionary with page URLs as keys
        if isinstance(crawl_result, dict) and all(isinstance(k, str) and isinstance(v, dict) for k, v in crawl_result.items() if k != 'error'):
            # It's a dictionary of pages - process each page
            for page_url, page_content in crawl_result.items():
                if page_url == 'error':
                    continue

                # Extract content based on available formats
                html_content = page_content.get("html", page_content.get("raw_html", ""))
                text_content = page_content.get("text", "")
                links = page_content.get("links", [])
                metadata = page_content.get("metadata", {})

                # Add page to the combined result
                combined_result['pages'].append({
                    'url': page_url,
                    'title': metadata.get("title", ""),
                    'content': html_content,
                    'textContent': text_content,
                    'links': links,
                    'metadata': metadata
                })

                # Add links to the combined result
                combined_result['links'].extend(links)
        else:
            # It's a single page result - treat it as a single page
            # This handles the case where the adapter returns a string or a simple object
            logger.info(f"Received single page result for {url}")

            # For string results (like text content)
            if isinstance(crawl_result, str):
                text_content = crawl_result
                html_content = ""
                links = []
                metadata = {}
            else:
                # For dictionary results
                html_content = crawl_result.get("html", crawl_result.get("raw_html", ""))
                text_content = crawl_result.get("text", "")
                links = crawl_result.get("links", [])
                metadata = crawl_result.get("metadata", {})

            # Add the single page to the result
            combined_result['pages'].append({
                'url': url,
                'title': metadata.get("title", "") if isinstance(metadata, dict) else "",
                'content': html_content,
                'textContent': text_content,
                'links': links,
                'metadata': metadata
            })

            # Add links to the combined result
            if links:
                combined_result['links'].extend(links)

        # Remove duplicate links
        combined_result['links'] = list(set(combined_result['links']))

        logger.info(f"Successfully crawled website: {url} - {len(combined_result['pages'])} pages")
        return combined_result

    except Exception as e:
        logger.error(f"Error crawling website {url}: {str(e)}")
        return None


def scrape_url(url, output_type="text", cache=True, stealth=False, screenshot=False,
               timeout=30000, wait_for=None, css_selector=None, device=None,
               excluded_urls=None, adapter_name="playwright", **kwargs):
    """
    Retrieves content of a URL using the configured scraper adapter.
    Support for PDF documents and YouTube videos has been added.

    Args:
        url (str): The URL to scrape
        output_type (str): Format(s) to return (text, html, links, metadata, full) or comma-separated string
        cache (bool): Whether to use cached results if available
        stealth (bool): Whether to use stealth mode for challenging websites
        screenshot (bool): Whether to capture screenshot
        timeout (int): Timeout in milliseconds
        wait_for (int): Time to wait after page load in milliseconds
        css_selector (str): CSS selector to extract content from
        device (str): Device to emulate (e.g., "mobile" or "desktop")
        excluded_urls (list): Additional list of URL patterns to exclude from scraping
        adapter_name (str): Name of the adapter to use (defaults to "playwright")
        **kwargs: Additional provider-specific parameters

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

    # Use the scraper service for all other URLs
    try:
        # Initialize the scraper service
        scraper_service = ScraperService(adapter_name)

        # Determine if mobile device is requested
        mobile = device == "mobile" if device else False

        # Scrape the URL
        scrape_result = scraper_service.scrape(
            url=url,
            output_types=output_type,
            timeout=timeout,
            wait_for=wait_for,
            css_selector=css_selector,
            mobile=mobile,
            stealth=stealth,
            cache=cache,
            **kwargs
        )

        # Check if scrape was successful
        if "error" in scrape_result:
            logger.error(f"Scrape failed for URL {url}: {scrape_result['error']}")
            return None

        # Create result in the expected format
        parsed_url = urlparse(url)
        domain = parsed_url.netloc

        # Extract content based on available formats
        html_content = scrape_result.get("html", scrape_result.get("raw_html", ""))
        text_content = scrape_result.get("text", "")
        metadata = scrape_result.get("metadata", {})

        # Add links to metadata if available
        if "links" in scrape_result:
            metadata["links"] = scrape_result["links"]

        # Log the metadata keys for debugging
        if metadata:
            logger.info(f"Metadata keys received: {list(metadata.keys())}")
        else:
            logger.warning(f"No metadata received for URL: {url}")

        # Extract title and description from metadata
        title = metadata.get("title", "")
        description = metadata.get("meta_description", metadata.get("description", ""))

        # Check for content compression
        if len(text_content) > 500000:
            logger.info(f"Text content from {url} exceeds 500,000 characters. Compressing...")
            compressed_content = _compress_large_content(text_content)
            if compressed_content:
                logger.info(f"Successfully compressed text content from {url}")
                text_content = compressed_content

        # Create a structured result
        result = {
            'url': url,
            'domain': domain,
            'title': title,
            'byline': metadata.get("author", ""),
            'content': html_content,  # HTML content
            'textContent': text_content,  # Text content
            'excerpt': description if description else (text_content[:200] + "..." if len(text_content) > 200 else text_content),
            'length': len(text_content),
            'meta': metadata  # Simply use the metadata directly
        }

        # Add screenshot if available
        if screenshot and "screenshot" in scrape_result:
            result['meta']['screenshot'] = scrape_result["screenshot"]

        logger.info(f"Successfully scraped URL: {url}")
        return result

    except Exception as e:
        logger.error(f"Error scraping URL {url}: {str(e)}")
        return None