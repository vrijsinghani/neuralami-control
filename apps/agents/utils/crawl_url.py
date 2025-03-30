import requests
import logging
import json
import asyncio
from django.conf import settings
from urllib.parse import urlparse
import re
import time
from apps.common.utils import is_pdf_url, is_youtube
from apps.agents.utils.scrape_url import (
    _load_from_youtube, 
    _load_from_pdf, 
    is_excluded_url, 
    _compress_large_content
)

logger = logging.getLogger(__name__)

def _get_firecrawl_headers():
    """Helper function to create headers with optional Authorization."""
    headers = {
        "Content-Type": "application/json"
    }
    # Check if FIRECRAWL_API_KEY is defined and not empty in settings
    api_key = getattr(settings, 'FIRECRAWL_API_KEY', None)
    if api_key:
        logger.debug("Adding FireCrawl API Key to headers.")
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        logger.debug("No FireCrawl API Key found in settings.")
    return headers

def crawl_url(url, limit=100, exclude_paths=None, include_paths=None, 
              max_depth=10, max_discovery_depth=None, ignore_sitemap=False,
              ignore_query_parameters=False, allow_backward_links=False,
              allow_external_links=False, webhook=None, scrape_options=None,
              include_html=True, include_markdown=True, poll_interval=30,
              wait_for_completion=True, timeout=3600, excluded_urls=None):
    """
    Crawls a website and all accessible subpages using the FireCrawl crawl endpoint.
    
    Args:
        url (str): The base URL to start crawling from
        limit (int): Maximum number of pages to crawl (default: 100)
        exclude_paths (list): URL pathname regex patterns to exclude
        include_paths (list): URL pathname regex patterns to include
        max_depth (int): Maximum depth to crawl relative to base URL (default: 10)
        max_discovery_depth (int): Maximum depth based on discovery order
        ignore_sitemap (bool): Ignore the website sitemap when crawling
        ignore_query_parameters (bool): Do not re-scrape same path with different query parameters
        allow_backward_links (bool): Enable crawler to navigate to previously linked pages
        allow_external_links (bool): Allow crawler to follow links to external websites
        webhook (dict): A webhook specification object
        scrape_options (dict): Scrape options for each page
        include_html (bool): Include HTML content in results
        include_markdown (bool): Include Markdown content in results
        poll_interval (int): Seconds between status checks when waiting for completion
        wait_for_completion (bool): Wait for crawl to complete before returning
        timeout (int): Maximum seconds to wait for crawl completion
        excluded_urls (list): Additional list of URL patterns to exclude from crawling
    
    Returns:
        dict: The crawl results with all pages content and metadata, or crawl job info if not waiting for completion
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
    
    # Check if URL is a YouTube video or PDF - handle with specific loaders
    if is_youtube(url):
        logger.info(f"Detected YouTube URL: {url}. Using specific YouTube loader instead of crawl.")
        return _load_from_youtube(url)
    
    if is_pdf_url(url):
        logger.info(f"Detected PDF URL: {url}. Using specific PDF loader instead of crawl.")
        return _load_from_pdf(url)
    
    # Prepare scrape options if not provided
    if scrape_options is None:
        scrape_options = {}
    
    # Set formats based on include_html and include_markdown
    formats = []
    if include_markdown:
        formats.append("markdown")
    if include_html:
        formats.append("html")
    
    if formats and "formats" not in scrape_options:
        scrape_options["formats"] = formats
    
    # Use FireCrawl crawl endpoint
    try:
        # Use direct URL that we know works
        firecrawl_url = "https://firecrawl.neuralami.ai/v1/crawl"
        
        # Setup request data for FireCrawl crawl endpoint
        request_data = {
            "url": url,
            "limit": limit
        }
        
        # Add optional parameters if provided
        if exclude_paths:
            request_data["excludePaths"] = exclude_paths
        
        if include_paths:
            request_data["includePaths"] = include_paths
            
        if max_depth != 10:  # Only include if different from default
            request_data["maxDepth"] = max_depth
            
        if max_discovery_depth is not None:
            request_data["maxDiscoveryDepth"] = max_discovery_depth
            
        if ignore_sitemap:
            request_data["ignoreSitemap"] = ignore_sitemap
            
        if ignore_query_parameters:
            request_data["ignoreQueryParameters"] = ignore_query_parameters
            
        if allow_backward_links:
            request_data["allowBackwardLinks"] = allow_backward_links
            
        if allow_external_links:
            request_data["allowExternalLinks"] = allow_external_links
            
        if webhook:
            request_data["webhook"] = webhook
            
        # Explicitly log scrape_options before adding to request_data
        if scrape_options:
            logger.debug(f"Received scrape_options in crawl_url: {json.dumps(scrape_options)}")
            request_data["scrapeOptions"] = scrape_options
        else:
            logger.warning("No scrape_options provided to crawl_url")
            # Even if scrape_options is None, make sure formats are set based on include flags
            if "scrapeOptions" not in request_data:
                request_data["scrapeOptions"] = {"formats": []}
            if include_markdown and "markdown" not in request_data["scrapeOptions"]["formats"]:
                request_data["scrapeOptions"]["formats"].append("markdown")
            if include_html and "html" not in request_data["scrapeOptions"]["formats"]:
                request_data["scrapeOptions"]["formats"].append("html")
            logger.debug(f"Manually set scrapeOptions formats: {request_data['scrapeOptions']}")
        
        # Get headers with optional Authorization
        headers = _get_firecrawl_headers()
        
        # Log the complete request data payload being sent to FireCrawl
        logger.info(f"FireCrawl crawl request payload: {json.dumps(request_data)}")
        
        # Make the request to FireCrawl crawl endpoint
        response = requests.post(
            firecrawl_url,
            headers=headers,
            json=request_data,
            timeout=(30, 120)  # (connect timeout, read timeout)
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
        
        # Parse response to get crawl job info
        crawl_job = response.json()
        
        # Check if crawl job was created successfully
        if not crawl_job.get("success", False):
            logger.error(f"FireCrawl crawl job creation failed for URL {url}: {crawl_job.get('error', 'Unknown error')}")
            return None
        
        # Get crawl job ID
        crawl_id = crawl_job.get("id")
        if not crawl_id:
            logger.error(f"FireCrawl crawl job ID missing in response for URL {url}")
            return None
            
        logger.info(f"FireCrawl crawl job created with ID: {crawl_id} for URL: {url}")
        
        # If not waiting for completion, return the crawl job info
        if not wait_for_completion:
            return {
                "success": True,
                "id": crawl_id,
                "status": "started",
                "message": "Crawl job started successfully. Use check_crawl_status to monitor progress."
            }
        
        # Wait for crawl to complete
        return _poll_crawl_status(crawl_id, poll_interval, timeout)
        
    except Exception as e:
        logger.error(f"Error starting crawl for URL {url} with FireCrawl: {str(e)}")
        return None

def check_crawl_status(crawl_id):
    """
    Check the status of a crawl job.
    
    Args:
        crawl_id (str): The ID of the crawl job
        
    Returns:
        dict: The current status and data of the crawl job
    """
    try:
        # Use FireCrawl check crawl status endpoint
        status_url = f"https://firecrawl.neuralami.ai/v1/crawl/{crawl_id}"
        
        # Get headers with optional Authorization
        headers = _get_firecrawl_headers()
        
        # Make the request
        response = requests.get(
            status_url,
            headers=headers,
            timeout=(30, 120)  # (connect timeout, read timeout)
        )
        
        # Check response status
        if response.status_code != 200:
            logger.error(f"FireCrawl service returned status code {response.status_code} for crawl ID {crawl_id}")
            try:
                error_details = response.json()
                logger.error(f"Error details: {error_details}")
            except:
                logger.error(f"Raw error response: {response.text}")
            return None
        
        # Parse response
        status_result = response.json()
        logger.info(f"FireCrawl crawl status for ID {crawl_id}: {status_result.get('status', 'unknown')}, "
                    f"completed: {status_result.get('completed', 0)}/{status_result.get('total', 0)}")
        
        return status_result
        
    except Exception as e:
        logger.error(f"Error checking crawl status for ID {crawl_id}: {str(e)}")
        return None

def _poll_crawl_status(crawl_id, poll_interval=30, timeout=3600):
    """
    Poll the crawl status until completion or timeout.
    
    Args:
        crawl_id (str): The ID of the crawl job
        poll_interval (int): Seconds between status checks
        timeout (int): Maximum seconds to wait
        
    Returns:
        dict: The complete crawl data or status on timeout
    """
    start_time = time.time()
    complete_data = []
    
    while time.time() - start_time < timeout:
        # Check crawl status
        status_result = check_crawl_status(crawl_id)
        
        if not status_result:
            logger.error(f"Failed to get status for crawl ID {crawl_id}")
            return None
        
        # If data is available, add it to our complete data
        if "data" in status_result and status_result["data"]:
            complete_data.extend(status_result["data"])
        
        # Check if there's more data to retrieve (pagination)
        next_url = status_result.get("next")
        
        # Follow pagination until we get all available data
        while next_url:
            try:
                logger.info(f"Fetching next page of crawl data from: {next_url}")
                # Get headers with optional Authorization for pagination request
                headers = _get_firecrawl_headers()
                
                response = requests.get(
                    next_url,
                    headers=headers, # Use updated headers
                    timeout=(30, 120)
                )
                
                if response.status_code != 200:
                    logger.error(f"Error fetching next page of crawl data: {response.status_code}")
                    break
                    
                next_data = response.json()
                
                if "data" in next_data and next_data["data"]:
                    complete_data.extend(next_data["data"])
                
                # Update for next iteration
                next_url = next_data.get("next")
                
            except Exception as e:
                logger.error(f"Error fetching next page of crawl data: {str(e)}")
                break
        
        # Check if crawl is complete
        status = status_result.get("status")
        if status == "completed":
            logger.info(f"Crawl job {crawl_id} completed successfully with {len(complete_data)} pages")
            
            # Process and organize the results
            return _process_crawl_results(complete_data, status_result)
            
        elif status == "failed":
            logger.error(f"Crawl job {crawl_id} failed: {status_result.get('error', 'Unknown error')}")
            return {
                "success": False,
                "id": crawl_id,
                "status": "failed",
                "error": status_result.get("error", "Unknown error"),
                "data": complete_data if complete_data else []
            }
        
        # Wait before checking again
        time.sleep(poll_interval)
    
    # If we're here, we've timed out
    logger.warning(f"Timed out waiting for crawl job {crawl_id} to complete")
    return {
        "success": False,
        "id": crawl_id,
        "status": "timeout",
        "message": f"Timed out after {timeout} seconds",
        "data": complete_data if complete_data else []
    }

def _process_crawl_results(crawl_data, status_info):
    """
    Process and organize the crawl results into a structured format.
    
    Args:
        crawl_data (list): List of page data from the crawl
        status_info (dict): Status information about the crawl
        
    Returns:
        dict: Structured crawl results
    """
    # Extract domain from the first result's sourceURL if available
    domain = ""
    if crawl_data and "metadata" in crawl_data[0] and "sourceURL" in crawl_data[0]["metadata"]:
        parsed_url = urlparse(crawl_data[0]["metadata"]["sourceURL"])
        domain = parsed_url.netloc
    
    # Debug log the structure of the first item
    if crawl_data:
        logger.debug(f"First crawl data item keys: {list(crawl_data[0].keys())}")
        logger.debug(f"Metadata keys: {list(crawl_data[0].get('metadata', {}).keys())}")
        
        # If there's no html/markdown in the first item, log a warning
        if "html" not in crawl_data[0] and "markdown" not in crawl_data[0]:
            logger.warning("First result doesn't contain html or markdown fields. This may be why content is empty.")
    
    # Process each page in the crawl data
    processed_pages = []
    for page in crawl_data:
        # Log the raw page data for debugging
        logger.debug(f"Processing page with keys: {list(page.keys())}")
        
        # Extract metadata
        metadata = page.get("metadata", {})
        source_url = metadata.get("sourceURL", "")
        title = metadata.get("title", "")
        description = metadata.get("description", "")
        
        # Get content - FireCrawl returns markdown and html directly at the top level
        markdown_content = page.get("markdown", "")
        
        # Check for both "html" and "rawHtml" fields as FireCrawl might use either
        html_content = page.get("html", "")
        if not html_content:
            html_content = page.get("rawHtml", "")
            if html_content:
                logger.debug(f"Used rawHtml field instead of html for {source_url}")
        
        # Log content lengths for debugging
        logger.debug(f"URL: {source_url}, Markdown length: {len(markdown_content)}, HTML length: {len(html_content)}")
        
        # Check if content is too large and needs compression
        if len(markdown_content) > 500000:
            logger.info(f"Markdown content from {source_url} exceeds 500,000 characters. Compressing...")
            compressed_content = _compress_large_content(markdown_content)
            if compressed_content:
                logger.info(f"Successfully compressed markdown content from {source_url}")
                markdown_content = compressed_content
        
        # Create page result
        page_result = {
            'url': source_url,
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
                'contentType': 'html',
                'links': page.get("links", [])
            }
        }
        
        # Add screenshot if available
        if "screenshot" in page:
            page_result['meta']['screenshot'] = page["screenshot"]
            
        processed_pages.append(page_result)
    
    # Create final result
    result = {
        'success': True,
        'id': status_info.get("id", ""),
        'status': "completed",
        'pages': processed_pages,
        'total_pages': len(processed_pages),
        'credits_used': status_info.get("creditsUsed", 0)
    }
    
    return result

async def crawl_url_and_watch(url, options=None, on_document=None, on_error=None, on_done=None):
    """
    Start a crawl and watch for real-time updates via WebSocket.
    This is a placeholder implementation as the actual WebSocket functionality
    would require additional implementation.
    
    Args:
        url (str): The URL to crawl
        options (dict): Crawl options
        on_document (callable): Callback for document events
        on_error (callable): Callback for error events
        on_done (callable): Callback for done events
        
    Returns:
        dict: Result of the crawl
    """
    logger.warning("WebSocket functionality for crawl_url_and_watch is not fully implemented")
    logger.info(f"Starting crawl for {url} with options: {options}")
    
    # For now, fall back to the regular crawl method
    result = crawl_url(
        url=url,
        limit=options.get("limit", 100) if options else 100,
        exclude_paths=options.get("excludePaths") if options else None,
        include_paths=options.get("includePaths") if options else None,
        max_depth=options.get("maxDepth", 10) if options else 10,
        wait_for_completion=True
    )
    
    # Call callbacks if provided
    if result and result.get("success") and on_document and "pages" in result:
        for page in result["pages"]:
            on_document(page)
    
    if result and not result.get("success") and on_error:
        on_error({"error": result.get("error", "Unknown error")})
    
    if on_done:
        on_done({"status": result.get("status", "unknown")})
    
    return result 