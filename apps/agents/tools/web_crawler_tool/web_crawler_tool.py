import logging
import json
import asyncio
from typing import Optional, Dict, Any, Type, List, Literal, Union, Set
from enum import Enum
from pydantic import BaseModel, Field, validator
from crewai.tools import BaseTool
from django.contrib.auth.models import User
from django.conf import settings
from urllib.parse import urlparse, urljoin
import re
import time
from celery import shared_task
from apps.agents.tasks.base import ProgressTask
from celery.contrib.abortable import AbortableTask
from apps.crawl_website.models import CrawlResult

# Import the ScrapperTool components for internal use
from apps.agents.tools.scrapper_tool import ScrapperTool, ScrapperToolSchema, OutputType

logger = logging.getLogger(__name__)

class CrawlOutputFormat(str, Enum):
    TEXT = "text"  # Text content only
    HTML = "html"  # Raw HTML
    LINKS = "links"  # Links only
    METADATA = "metadata"  # Metadata only
    FULL = "full"  # All formats combined

class WebCrawlerToolSchema(BaseModel):
    """Input schema for WebCrawlerTool."""
    start_url: str = Field(..., description="Starting URL to begin crawling")
    user_id: int = Field(..., description="ID of the user initiating the crawl")
    max_pages: int = Field(default=10, description="Maximum number of pages to crawl")
    max_depth: int = Field(default=2, description="Maximum depth for crawling")
    output_format: str = Field(
        default=CrawlOutputFormat.TEXT, 
        description="Format of the output content (text, html, links, metadata, full). Can be a single value or a comma-separated list."
    )
    include_patterns: Optional[List[str]] = Field(
        default=None,
        description="URL patterns to include in crawl (regex patterns)"
    )
    exclude_patterns: Optional[List[str]] = Field(
        default=None,
        description="URL patterns to exclude from crawl (regex patterns)"
    )
    stay_within_domain: bool = Field(
        default=True,
        description="Whether to stay within the same domain"
    )
    cache: bool = Field(
        default=True,
        description="Whether to use cached results if available"
    )
    stealth: bool = Field(
        default=True,
        description="Whether to use stealth mode"
    )
    device: str = Field(
        default="desktop",
        description="Device type to emulate (desktop, mobile, tablet)"
    )
    timeout: int = Field(
        default=60000,
        description="Timeout in milliseconds for each page request"
    )
    
    @validator('start_url')
    def validate_url(cls, v):
        """Validate URL format."""
        if not v.startswith(('http://', 'https://')):
            raise ValueError("URL must start with http:// or https://")
        return v
        
    @validator('output_format')
    def normalize_output_formats(cls, v):
        """Handle any format of output format specification."""
        try:
            logger.debug(f"Normalizing output_format: {repr(v)}")
            
            # Convert any input to a string first for consistency
            input_str = str(v)
            
            # Remove all quotes (both single and double)
            cleaned = input_str.replace('"', '').replace("'", '')
            
            # Split by comma and clean up
            if ',' in cleaned:
                # Multiple formats specified
                formats = [f.strip().lower() for f in cleaned.split(',')]
                valid_formats = []
                for f in formats:
                    if f:  # Skip empty strings
                        try:
                            valid_formats.append(CrawlOutputFormat(f))
                        except ValueError:
                            logger.warning(f"Invalid output format: {f}")
                
                # If FULL is included, it overrides everything else
                if CrawlOutputFormat.FULL in valid_formats:
                    logger.debug("FULL format found, using only that")
                    return CrawlOutputFormat.FULL
                    
                if valid_formats:
                    # For multiple formats, use a comma-separated string
                    result = ",".join(f.value for f in valid_formats)
                    logger.debug(f"Parsed to formats: {result}")
                    return result
            else:
                # Single format
                try:
                    single_format = CrawlOutputFormat(cleaned.lower())
                    logger.debug(f"Parsed to single format: {single_format}")
                    return single_format
                except ValueError:
                    logger.warning(f"Invalid output format: {cleaned}")
            
            # Default to TEXT if parsing failed
            logger.warning(f"Using default TEXT output format")
            return CrawlOutputFormat.TEXT
            
        except Exception as e:
            logger.error(f"Error normalizing output_format {repr(v)}: {str(e)}")
            # Default to TEXT if there's an error
            logger.warning(f"Defaulting to TEXT output_format due to validation error")
            return CrawlOutputFormat.TEXT

class CrawlerState:
    """Manages crawler state in memory."""
    def __init__(self, task_id: str, max_pages: int):
        self.task_id = task_id
        self.max_pages = max_pages
        self.pages_crawled = 0
        self.url_queue = []
        self.visited_urls: Set[str] = set()
        self.url_depths: Dict[str, int] = {}
        self.results: Dict[str, Any] = {}
        
    def add_url(self, url: str, depth: int) -> bool:
        """Add URL to the crawling queue if not already visited or queued.
        
        Returns:
            bool: True if URL was added, False if it was already visited or queued
        """
        # Normalize URL to avoid duplicates with trailing slashes, etc.
        normalized_url = url.rstrip('/')
        
        # Skip URLs that are just fragments or empty
        parsed_url = urlparse(normalized_url)
        if not parsed_url.netloc and not parsed_url.path:
            logger.debug(f"Skipping empty or fragment-only URL: {url}")
            return False
            
        if normalized_url in self.visited_urls:
            # Already visited
            logger.debug(f"URL already visited: {url}")
            return False
        
        if normalized_url in self.url_depths:
            # Already in queue
            # If we find it at a lower depth, update the depth
            if depth < self.url_depths[normalized_url]:
                logger.debug(f"Updating depth for queued URL: {url} from {self.url_depths[normalized_url]} to {depth}")
                self.url_depths[normalized_url] = depth
                # This is just depth update, not a new URL
            return False
            
        # New URL, add to queue
        logger.debug(f"Adding new URL to queue: {url} at depth {depth}")
        self.url_queue.append(normalized_url)
        self.url_depths[normalized_url] = depth
        return True
    
    def mark_visited(self, url: str) -> None:
        """Mark URL as visited and increment pages crawled counter."""
        # Normalize URL
        normalized_url = url.rstrip('/')
        
        if normalized_url not in self.visited_urls:
            self.visited_urls.add(normalized_url)
            self.pages_crawled += 1
    
    def get_next_batch(self, batch_size: int) -> List[str]:
        """Get next batch of URLs to crawl, respecting maximum pages limit."""
        remaining_pages = self.max_pages - self.pages_crawled
        actual_batch_size = min(batch_size, remaining_pages, len(self.url_queue))
        batch = self.url_queue[:actual_batch_size]
        self.url_queue = self.url_queue[actual_batch_size:]
        return batch

class WebCrawlerTool(BaseTool):
    """
    A tool that crawls websites starting from a URL, following links up to a specified depth,
    and extracts content in various formats (text, HTML, metadata, links, or all).
    Can be configured to stay within a domain and to include/exclude URL patterns.
    """
    name: str = "Web Crawler Tool"
    description: str = """
    A tool that crawls websites starting from a URL, following links up to a specified depth,
    and extracts content in various formats (text, HTML, metadata, links, or all).
    Can be configured to stay within a domain and to include/exclude URL patterns.
    """
    args_schema: Type[BaseModel] = WebCrawlerToolSchema
    
    def _run(self, start_url: str, user_id: int, max_pages: int = 10, max_depth: int = 2,
             output_format: str = "text", include_patterns: Optional[List[str]] = None,
             exclude_patterns: Optional[List[str]] = None, stay_within_domain: bool = True,
             cache: bool = True, stealth: bool = True, device: str = "desktop", 
             timeout: int = 60000, **kwargs) -> str:
        """
        Run the web crawler tool.
        
        Args:
            start_url: Starting URL to crawl
            user_id: ID of the user initiating the crawl
            max_pages: Maximum number of pages to crawl
            max_depth: Maximum depth for crawling
            output_format: Format of output content, can be single value or comma-separated
            include_patterns: URL patterns to include
            exclude_patterns: URL patterns to exclude
            stay_within_domain: Whether to stay within the same domain
            cache: Whether to use cached results
            stealth: Whether to use stealth mode
            device: Device to emulate
            timeout: Timeout in milliseconds
            
        Returns:
            JSON string with crawling results
        """
        try:
            # Debug logging for parameters
            logger.debug(f"WebCrawlerTool called with: start_url={start_url}, max_pages={max_pages}, max_depth={max_depth}, output_format={output_format}, device={device}")
            
            # Get current task if available
            current_task = kwargs.get('task', None)
            
            # Process output format - convert comma-separated string to a list if needed
            output_format_value = None
            if isinstance(output_format, str) and ',' in output_format:
                # It's already a comma-separated string of valid formats
                output_format_value = output_format  
                logger.debug(f"Using composite formats: {output_format}")
            else:
                # Ensure output_format is valid for single value
                try:
                    # Convert to proper enum if it's a string
                    if isinstance(output_format, str):
                        output_format_enum = CrawlOutputFormat(output_format.lower())
                    else:
                        output_format_enum = output_format
                    
                    output_format_value = output_format_enum
                    logger.debug(f"Using single format: {output_format_enum}")
                except ValueError:
                    output_format_value = CrawlOutputFormat.TEXT
                    logger.warning(f"Invalid output_format '{output_format}', defaulting to TEXT")
            
            # Call the crawling function
            result = crawl_website(
                start_url=start_url,
                user_id=user_id,
                max_pages=max_pages,
                max_depth=max_depth,
                output_format=output_format_value,
                include_patterns=include_patterns,
                exclude_patterns=exclude_patterns,
                stay_within_domain=stay_within_domain,
                cache=cache,
                stealth=stealth,
                device=device,
                timeout=timeout,
                task=current_task
            )
            return result
            
        except Exception as e:
            logger.error(f"Error in WebCrawlerTool: {str(e)}", exc_info=True)
            return json.dumps({
                "status": "error",
                "message": str(e)
            })

def crawl_website(
    start_url: str,
    user_id: int,
    max_pages: int = 10,
    max_depth: int = 2,
    output_format: Union[CrawlOutputFormat, str] = CrawlOutputFormat.TEXT,
    include_patterns: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None,
    stay_within_domain: bool = True,
    cache: bool = True,
    stealth: bool = True,
    device: str = "desktop",
    timeout: int = 60000,
    batch_size: int = 5,
    task: Optional[Any] = None
) -> str:
    """Core website crawling logic."""
    try:
        logger.info(f"Starting crawl for URL: {start_url}, max_pages: {max_pages}, max_depth: {max_depth}")
        
        # Parse and validate start URL
        try:
            parsed_start_url = urlparse(start_url)
            if not parsed_start_url.netloc:
                raise ValueError(f"Invalid URL: {start_url}")
            
            # Extract domain for filtering if stay_within_domain is True
            start_domain = parsed_start_url.netloc
            logger.debug(f"Extracted start domain: {start_domain}")
            
            # Also store the normalized version for later comparison
            normalized_start_domain = start_domain.lower()
            if normalized_start_domain.startswith('www.'):
                normalized_start_domain = normalized_start_domain[4:]
            logger.debug(f"Normalized start domain: {normalized_start_domain}")
        except Exception as e:
            logger.error(f"URL parsing failed: {str(e)}")
            raise ValueError(f"Invalid URL: {start_url}")
        
        # Initialize crawler state
        state = CrawlerState(None, max_pages)
        state.add_url(start_url, 0)
        
        # Initialize progress if task is provided
        if task:
            task.update_progress(0, max_pages, "Starting crawl", url=start_url)
        
        # Create ScrapperTool instance for content retrieval
        scrapper_tool = ScrapperTool()
        
        # Determine which ScrapperTool output types to use based on crawler output format
        # Convert our output_format to appropriate scrapper_output_type_param
        if isinstance(output_format, str) and ',' in output_format:
            # Handle multiple formats - we'll use the individual types directly
            scrapper_output_type_param = output_format
            logger.debug(f"Using comma-separated output format: {scrapper_output_type_param}")
        else:
            # Handle single format - convert to appropriate scrapper type(s)
            output_format_str = output_format.value if hasattr(output_format, 'value') else str(output_format)
            
            # For crawling, we need to include links unless explicitly requested
            if output_format_str == CrawlOutputFormat.HTML:
                scrapper_output_type_param = "html,links"
            elif output_format_str == CrawlOutputFormat.METADATA:
                scrapper_output_type_param = "metadata,links"
            elif output_format_str == CrawlOutputFormat.LINKS:
                scrapper_output_type_param = "links"
            elif output_format_str == CrawlOutputFormat.FULL:
                scrapper_output_type_param = "full"
            else:  # Default to TEXT
                scrapper_output_type_param = "text,links"
            
        logger.debug(f"Using ScrapperTool with output types: {scrapper_output_type_param}")
        
        # Track consecutive errors to prevent infinite loops
        consecutive_errors = 0
        max_consecutive_errors = 3
        
        # Safety iteration counter
        iterations = 0
        max_iterations = max(50, max_pages * 2)
        
        while state.url_queue and state.pages_crawled < max_pages and iterations < max_iterations:
            iterations += 1
            logger.info(f"Crawl iteration {iterations}/{max_iterations}: processed {state.pages_crawled}/{max_pages} pages")
            logger.debug(f"Current queue size: {len(state.url_queue)}, visited URLs: {len(state.visited_urls)}")
            
            # Get next batch, respecting max_pages limit
            batch_urls = state.get_next_batch(batch_size)
            if not batch_urls:  # No more URLs to process within limits
                logger.info("No more URLs to process within limits")
                break
            
            logger.debug(f"Processing batch of {len(batch_urls)} URLs")
            current_depth = max(state.url_depths[url] for url in batch_urls)
            
            if current_depth > max_depth:
                logger.info(f"Reached maximum depth {max_depth}")
                break
            
            # Process each URL in the batch
            batch_processed = False
            for url in batch_urls:
                logger.info(f"Processing URL: {url} at depth {state.url_depths[url]}")
                
                try:
                    # Use ScrapperTool to fetch content
                    # Handle each output type separately to ensure proper parsing
                    scrapper_results = {}
                    requested_types = []
                    
                    # Parse output types from the parameter
                    if isinstance(scrapper_output_type_param, str) and ',' in scrapper_output_type_param:
                        requested_types = [t.strip() for t in scrapper_output_type_param.split(',')]
                        logger.debug(f"Split composite output types into: {requested_types}")
                    else:
                        requested_types = [scrapper_output_type_param]
                        logger.debug(f"Using single output type: {scrapper_output_type_param}")
                    
                    # Make sure links are requested if needed for crawling
                    if 'links' not in requested_types and current_depth < max_depth:
                        requested_types.append('links')
                        logger.debug("Added 'links' type for crawling purposes")
                    
                    # Process each type separately to avoid composite string issue
                    for output_type in requested_types:
                        logger.debug(f"Requesting output type: {output_type}")
                        
                        # Ensure output_type is a clean string
                        output_type = output_type.strip()
                        if not output_type:
                            continue
                            
                        try:
                            type_result_json = scrapper_tool._run(
                                url=url,
                                user_id=user_id,
                                output_type=output_type,  # Pass single type, not composite
                                cache=cache,
                                stealth=stealth,
                                device=device,
                                timeout=timeout
                            )
                            
                            try:
                                type_result = json.loads(type_result_json)
                                if type_result.get("success", False):
                                    # Store in our results dictionary
                                    if output_type == 'links' and 'links' in type_result:
                                        # Ensure links is properly extracted
                                        links_data = type_result.get('links', [])
                                        logger.debug(f"Raw links data type: {type(links_data)}")
                                        
                                        # Handle different formats of links data
                                        if isinstance(links_data, str):
                                            try:
                                                # Try to parse as JSON if it's a string
                                                parsed_links = json.loads(links_data)
                                                scrapper_results['links'] = parsed_links
                                            except json.JSONDecodeError:
                                                # If not JSON, use as is
                                                scrapper_results['links'] = [links_data]
                                        else:
                                            scrapper_results['links'] = links_data
                                            
                                        logger.debug(f"Found {len(scrapper_results['links'])} links, type: {type(scrapper_results['links'])}")
                                    elif output_type == 'text' and 'text' in type_result:
                                        scrapper_results['text'] = type_result.get('text', '')
                                    elif output_type == 'metadata':
                                        # Extract metadata fields
                                        for key in ['title', 'excerpt', 'meta', 'length']:
                                            if key in type_result:
                                                scrapper_results[key] = type_result[key]
                                    elif output_type == 'html':
                                        scrapper_results['html'] = type_result.get('html', '')
                                    elif output_type == 'full':
                                        # Copy all fields except success, url, domain
                                        scrapper_results.update({k: v for k, v in type_result.items() 
                                                               if k not in ['success', 'url', 'domain']})
                            except json.JSONDecodeError as e:
                                logger.error(f"JSON decode error for {output_type}: {str(e)}")
                                logger.debug(f"Failed content snippet: {type_result_json[:100]}...")
                        except Exception as e:
                            logger.error(f"Error requesting {output_type} for {url}: {str(e)}")
                    
                    # Create a combined result with all requested data
                    scrapper_result = {
                        "success": True,
                        "url": url,
                        "domain": urlparse(url).netloc
                    }
                    # Add all the collected results
                    scrapper_result.update(scrapper_results)
                    
                    # Log what we got
                    logger.debug(f"Combined result has keys: {list(scrapper_result.keys())}")
                    
                    # Skip if the scrape was unsuccessful
                    if not scrapper_result or not scrapper_result.get("success", False):
                        logger.warning(f"Failed to scrape {url}: {scrapper_result.get('error', 'Unknown error')}")
                        continue
                    
                    # Also skip if we have no useful content (only success, url, domain)
                    if len(scrapper_result.keys()) <= 3:
                        logger.warning(f"No content retrieved from {url}")
                        continue
                    
                    # Mark URL as visited and store result
                    state.mark_visited(url)
                    state.results[url] = scrapper_result
                    batch_processed = True
                    
                    # Extract links for further crawling if not at max depth
                    if current_depth < max_depth:
                        try:
                            links = scrapper_result.get("links", [])
                            
                            if not links:
                                logger.warning(f"No links found for {url}")
                                continue
                                
                            logger.debug(f"Processing {len(links)} discovered links")
                            
                            # Ensure links is a list
                            if isinstance(links, str):
                                try:
                                    # Try to parse as JSON if it's a string
                                    parsed_links = json.loads(links)
                                    if isinstance(parsed_links, list):
                                        links = parsed_links
                                    else:
                                        logger.warning(f"Links is not a list after parsing: {type(parsed_links)}")
                                        links = [links]  # Use the string as a single link
                                except json.JSONDecodeError:
                                    # If not JSON, treat as a single link
                                    links = [links]
                            elif not isinstance(links, list):
                                logger.warning(f"Links is not a list: {type(links)}")
                                links = [str(links)]
                                
                            logger.debug(f"Normalized links to list with {len(links)} items")
                            
                            # Process discovered links
                            links_added = 0
                            for link in links:
                                link_url = None
                                
                                # Handle different link formats
                                if isinstance(link, dict):
                                    link_url = link.get("url") or link.get("href")
                                elif isinstance(link, str):
                                    link_url = link
                                    
                                if not link_url:
                                    continue
                                
                                # Normalize the URL (make absolute if relative)
                                if not link_url.startswith(('http://', 'https://')):
                                    link_url = urljoin(url, link_url)
                                
                                # Skip fragment-only URLs (same page anchors)
                                parsed_url = urlparse(link_url)
                                if not parsed_url.netloc and not parsed_url.path and parsed_url.fragment:
                                    logger.debug(f"Skipping fragment-only URL: {link_url}")
                                    continue
                                
                                # Skip URLs that are just the base URL with a trailing slash difference
                                normalized_link = link_url.rstrip('/')
                                normalized_current = url.rstrip('/')
                                if normalized_link == normalized_current:
                                    logger.debug(f"Skipping self-reference URL: {link_url}")
                                    continue
                                
                                # Apply domain filtering if required
                                if stay_within_domain:
                                    link_domain = urlparse(link_url).netloc
                                    
                                    # Normalize domains by removing 'www.' prefix for comparison
                                    normalized_link_domain = link_domain.lower()
                                    
                                    if normalized_link_domain.startswith('www.'):
                                        normalized_link_domain = normalized_link_domain[4:]
                                    
                                    # Check if domains match after normalization
                                    domains_match = False
                                    
                                    # Exact match
                                    if normalized_link_domain == normalized_start_domain:
                                        domains_match = True
                                    # Subdomain match (link is a subdomain of start domain)
                                    elif normalized_link_domain.endswith('.' + normalized_start_domain):
                                        domains_match = True
                                    # Start URL is www but link isn't
                                    elif 'www.' + normalized_link_domain == normalized_start_domain:
                                        domains_match = True
                                    # Link is www but start URL isn't
                                    elif normalized_link_domain == 'www.' + normalized_start_domain:
                                        domains_match = True
                                        
                                    if not domains_match:
                                        logger.debug(f"Skipping out-of-domain URL: {link_url} (domain: {link_domain}, start domain: {start_domain})")
                                        continue
                                
                                # Apply include/exclude patterns
                                if include_patterns and not any(re.search(pattern, link_url) for pattern in include_patterns):
                                    logger.debug(f"Skipping URL not matching include patterns: {link_url}")
                                    continue
                                
                                if exclude_patterns and any(re.search(pattern, link_url) for pattern in exclude_patterns):
                                    logger.debug(f"Skipping URL matching exclude patterns: {link_url}")
                                    continue
                                
                                # Add the URL to the queue
                                was_added = state.add_url(link_url, current_depth + 1)
                                if was_added:
                                    links_added += 1
                                    logger.debug(f"Added URL to queue: {link_url}")
                                else:
                                    logger.debug(f"URL already in queue or visited: {link_url}")
                                
                            logger.debug(f"Found {len(links)} links, added {links_added} new URLs to the crawl queue")
                                
                        except Exception as e:
                            logger.error(f"Error processing links from {url}: {str(e)}", exc_info=True)
                            continue
                    
                except Exception as e:
                    logger.error(f"Error processing URL {url}: {str(e)}", exc_info=True)
                    continue
                    
                # Update progress if task is provided
                if task:
                    task.update_progress(
                        current=state.pages_crawled,
                        total=max_pages,
                        status=f'Processing pages at depth {current_depth}',
                        url=url
                    )
            
            # Handle consecutive errors
            if batch_processed:
                consecutive_errors = 0
            else:
                consecutive_errors += 1
                logger.warning(f"Batch processed no results. Consecutive errors: {consecutive_errors}/{max_consecutive_errors}")
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f"Too many consecutive errors ({consecutive_errors}), stopping crawl")
                    break
                    
            # Small pause between batches to be nice to the servers
            time.sleep(1)
        
        # Log if we stopped due to reaching max iterations
        if iterations >= max_iterations:
            logger.warning(f"Reached maximum iterations ({max_iterations}), stopping crawl")
        
        # Process results
        all_content = []
        for url, result in state.results.items():
            # Add URL to the result for context
            if isinstance(result, dict):
                result["url"] = url
                all_content.append(result)
        
        # Create final result
        if all_content:
            result = {
                "status": "success",
                "start_url": start_url,
                "total_pages": len(state.results),
                "results": all_content
            }
            
            # Store crawl result in database
            try:
                crawl_result = CrawlResult.create_with_content(
                    user=User.objects.get(id=user_id),
                    website_url=start_url[:200],
                    content=json.dumps(all_content),
                    links_visited={"internal": list(state.visited_urls)},
                    total_links=len(state.visited_urls)
                )
                result["crawl_result_id"] = crawl_result.id
            except Exception as e:
                logger.error(f"Error storing crawl result: {str(e)}")
            
            if task:
                task.update_progress(
                    current=state.pages_crawled,
                    total=state.pages_crawled,
                    status='Completed successfully',
                    result=result
                )
        else:
            logger.info(f"No valid content found for {start_url}")
            result = {
                "status": "success",
                "warning": "No valid content found",
                "start_url": start_url,
                "total_pages": 0,
                "results": []
            }
        
        logger.info(f"Completed crawl with {len(state.results)} pages")
        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"Error in crawl_website: {str(e)}", exc_info=True)
        return json.dumps({
            "status": "error",
            "message": str(e)
        })

class WebCrawlerAbortableTask(AbortableTask, ProgressTask):
    """Abortable task that supports progress reporting"""
    pass

@shared_task(bind=True, base=WebCrawlerAbortableTask, time_limit=600, soft_time_limit=540)
def web_crawler_task(self, start_url: str, user_id: int, max_pages: int = 10, max_depth: int = 2,
                    output_format: Union[str, CrawlOutputFormat] = "text", include_patterns: Optional[List[str]] = None,
                    exclude_patterns: Optional[List[str]] = None, stay_within_domain: bool = True,
                    cache: bool = True, stealth: bool = True, device: str = "desktop",
                    timeout: int = 60000) -> str:
    """Celery task wrapper for crawl_website function."""
    start_time = time.time()
    logger.info(f"Starting web_crawler_task for {start_url}, user_id={user_id}, max_pages={max_pages}, max_depth={max_depth}")
    
    try:
        result = crawl_website(
            start_url=start_url,
            user_id=user_id,
            max_pages=max_pages,
            max_depth=max_depth,
            output_format=output_format,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            stay_within_domain=stay_within_domain,
            cache=cache,
            stealth=stealth,
            device=device,
            timeout=timeout,
            task=self
        )
        elapsed_time = time.time() - start_time
        logger.info(f"Completed web_crawler_task for {start_url} in {elapsed_time:.2f} seconds, processed {max_pages} pages")
        return result
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(f"Error in web_crawler_task after {elapsed_time:.2f} seconds: {str(e)}", exc_info=True)
        return json.dumps({
            "status": "error",
            "message": str(e)
        }) 