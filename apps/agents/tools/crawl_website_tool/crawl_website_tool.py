import logging
import aiohttp
import asyncio
from typing import Optional, Dict, Any, Type, List, Literal, Union
from enum import Enum
from pydantic import BaseModel, Field, HttpUrl
from crewai.tools import BaseTool
from django.contrib.auth.models import User
from django.conf import settings
from apps.crawl_website.models import CrawlResult
from .utils import sanitize_url
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import time
import json
import re
from celery import shared_task
from celery.contrib.abortable import AbortableTask

logger = logging.getLogger(__name__)

# Define all possible CrawlResult attributes
CrawlResultAttribute = Literal[
    "url",
    "html",
    "success",
    "cleaned_html",
    "media",
    "links",
    "downloaded_files",
    "screenshot",
    "markdown",
    "markdown_v2",
    "fit_markdown",
    "fit_html",
    "extracted_content",
    "metadata",
    "error_message",
    "session_id",
    "response_headers",
    "status_code"
]

# Ensure OutputType is defined at module level
class OutputType(str, Enum):
    TEXT = "text"  # Plain text content with basic formatting
    RAW_TEXT = "raw_text"  # Pure text content, optimized for LLMs
    HTML = "html"  # Raw HTML
    MARKDOWN = "markdown"  # Markdown formatted content
    CLEAN_HTML = "clean_html"  # Sanitized HTML
    STRUCTURED = "structured"  # Extracted structured content
    MEDIA = "media"  # Media-focused extraction (images, videos)
    FULL = "full"  # Complete extraction with all available data

class ExtractionConfig(BaseModel):
    """Configuration for content extraction."""
    type: str = Field(default="basic", description="Type of extraction: basic, llm, cosine, or json_css")
    params: Dict[str, Any] = Field(default_factory=dict, description="Parameters for extraction")

def get_output_format(output_type: OutputType) -> str:
    """Get the appropriate output format based on output type."""
    if output_type in [OutputType.TEXT, OutputType.CLEAN_HTML, OutputType.RAW_TEXT]:
        return "html"
    elif output_type == OutputType.HTML:
        return "html"
    elif output_type == OutputType.STRUCTURED:
        return "json"
    else:
        return "markdown_v2"

def get_excluded_tags(output_type: OutputType) -> List[str]:
    """Get excluded tags based on output type."""
    base_tags = ['nav', 'aside', 'footer']
    if output_type in [OutputType.TEXT, OutputType.CLEAN_HTML]:
        return base_tags + ['header', 'script', 'style']
    elif output_type == OutputType.RAW_TEXT:
        # Exclude all non-content tags for raw text
        return base_tags + ['header', 'script', 'style', 'meta', 'link', 'noscript', 
                          'iframe', 'form', 'button', 'input', 'select', 'textarea']
    return base_tags

def get_html2text_config(output_type: OutputType) -> Dict[str, Any]:
    """Get HTML2Text configuration based on output type."""
    config = {
        "ignore_links": output_type in [OutputType.TEXT, OutputType.STRUCTURED, OutputType.RAW_TEXT],
        "ignore_images": output_type in [OutputType.TEXT, OutputType.STRUCTURED, OutputType.RAW_TEXT],
        "body_width": 0,
        "unicode_snob": True,
        "protect_links": output_type not in [OutputType.TEXT, OutputType.STRUCTURED, OutputType.RAW_TEXT],
        "bypass_tables": output_type in [OutputType.TEXT, OutputType.STRUCTURED, OutputType.RAW_TEXT],
        "single_line_break": True
    }
    
    if output_type == OutputType.RAW_TEXT:
        config.update({
            "ignore_emphasis": True,  # Remove bold/italic
            "ignore_tables": True,    # Remove tables completely
            "skip_internal_links": True,
            "inline_links": False,
            "ignore_anchors": True,
            "ignore_images": True,
            "pad_tables": False,
            "default_image_alt": "",
            "escape_snob": True
        })
    
    return config

class CrawlWebsiteToolSchema(BaseModel):
    """Input for CrawlWebsiteTool."""
    website_url: str = Field(..., description="Website URL to crawl")
    user_id: int = Field(..., description="ID of the user initiating the crawl")
    max_pages: int = Field(default=100, description="Maximum number of pages to crawl")
    max_depth: int = Field(default=3, description="Maximum depth for crawling")
    output_type: OutputType = Field(default=OutputType.MARKDOWN, description="Type of output content (text, html, or markdown)")
    extraction_config: Optional[ExtractionConfig] = Field(
        default=None,
        description="Configuration for content extraction"
    )
    wait_for: Optional[str] = Field(
        default=None,
        description="CSS selector to wait for before extraction"
    )
    css_selector: Optional[str] = Field(
        default=None,
        description="CSS selector for targeted content extraction"
    )
    include_patterns: Optional[List[str]] = Field(
        default=None,
        description="URL patterns to include in crawl"
    )
    exclude_patterns: Optional[List[str]] = Field(
        default=None,
        description="URL patterns to exclude from crawl"
    )

class CrawlerState:
    """Manages crawler state in memory."""
    def __init__(self, task_id: str, max_pages: int):
        self.task_id = task_id
        self.max_pages = max_pages
        self.pages_crawled = 0
        self.url_queue = []  # Changed to list to maintain order and track depth
        self.visited_urls = set()
        self.url_depths = {}  # Track depth of each URL
        self.results = {}
        
    def add_url(self, url: str, depth: int) -> None:
        """Add URL to queue if not visited and within depth limit."""
        if url not in self.visited_urls and url not in self.url_depths:
            self.url_queue.append(url)
            self.url_depths[url] = depth
    
    def mark_visited(self, url: str) -> None:
        """Mark URL as visited and update counter."""
        if url not in self.visited_urls:
            self.visited_urls.add(url)
            self.pages_crawled += 1
    
    def get_next_batch(self, batch_size: int) -> List[str]:
        """Get next batch of URLs to process."""
        batch = self.url_queue[:batch_size]
        self.url_queue = self.url_queue[batch_size:]
        return batch

def create_requests_session(
    retries: int = 3,
    backoff_factor: float = 0.3,
    status_forcelist: List[int] = (500, 502, 503, 504),
    timeout: int = 300
) -> requests.Session:
    """Create a requests Session with retry logic."""
    session = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist
    )
    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=10,  # Increase connection pool
        pool_maxsize=100,     # Increase max pool size
        pool_block=True       # Block when pool is full
    )
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    session.timeout = timeout
    return session

class CrawlWebsiteTool(BaseTool):
    name: str = "Crawl and Read Website Content"
    description: str = """A tool that can crawl websites and extract content.
    
    Features:
    - Single page scraping with `single_page=True`
    - Full website crawling with depth control
    - Content extraction with different strategies
    - Screenshot capture
    - Pattern-based URL filtering
    - Progress tracking
    
    Example for single page:
    {
        "website_url": "https://example.com",
        "user_id": 1,
        "single_page": true,
        "extraction_config": {"type": "basic"}
    }
    
    Example for website crawling:
    {
        "website_url": "https://example.com",
        "user_id": 1,
        "max_pages": 50,
        "max_depth": 2,
        "include_patterns": ["blog", "articles"],
        "exclude_patterns": ["login", "signup"]
    }
    """
    args_schema: Type[BaseModel] = CrawlWebsiteToolSchema
    
    def _prepare_request_data(self, params: CrawlWebsiteToolSchema) -> Dict[str, Any]:
        """Prepare request data based on parameters."""
        crawler_params = {
            **settings.CRAWL4AI_CRAWLER_PARAMS,
            "wait_for": params.wait_for or "main, #main, .main, #content, .content, article, .post-content",  # Wait for main content
            "remove_overlay_elements": True,
            "delay_before_return_html": 5.0,  # Increased delay for JS content
            "wait_until": "networkidle0",  # Wait until network is idle
            "javascript": True,  # Enable JavaScript
            "scroll": True,  # Scroll the page
            "wait_for_selector_timeout": 10000,  # Increase timeout
            "verbose": True
        }

        # Configure extraction based on output type
        extraction_config = {
            "type": "basic",
            "params": {
                "output_format": get_output_format(params.output_type),
                "word_count_threshold": 0,  # Don't filter by word count
                "only_text": False,
                "bypass_cache": settings.CRAWL4AI_EXTRA_PARAMS.get("bypass_cache", False),
                "process_iframes": True,
                "excluded_tags": ["script", "style", "noscript"],  # Minimal tag exclusion
                "html2text": {
                    **get_html2text_config(params.output_type),
                    "bypass_tables": False,  # Keep tables
                    "ignore_images": False,  # Keep images
                    "ignore_emphasis": False  # Keep formatting
                },
                "markdown": {
                    "enabled": params.output_type == OutputType.MARKDOWN,
                    "gfm": True,
                    "tables": True,
                    "breaks": True,
                    "smartLists": True,
                    "smartypants": True,
                    "xhtml": True
                }
            }
        }

        return {
            "urls": params.website_url,
            "priority": 10,
            "extraction_config": extraction_config,
            "crawler_params": crawler_params
        }

    def _process_results(self, response_data: Dict[str, Any], single_page: bool) -> Dict[str, Any]:
        """Process and format crawl results."""
        if single_page:
            result = response_data.get("result", {})
            return {
                "status": "success",
                "url": result.get("url"),
                "content": result.get("markdown", ""),
                "metadata": result.get("metadata", {}),
                "links": result.get("links", {}),
            }
        else:
            results = response_data.get("results", {})
            return {
                "status": "success",
                "crawled_count": response_data.get("crawled_count", 0),
                "failed_count": response_data.get("failed_count", 0),
                "max_depth_reached": response_data.get("max_depth_reached", 0),
                "results": results,
                "failed_urls": response_data.get("failed_urls", {})
            }

    def _run(self, website_url: str, user_id: int, max_pages: int = 100, max_depth: int = 3,
             extraction_config: Optional[Dict[str, Any]] = None,
             wait_for: Optional[str] = None, css_selector: Optional[str] = None,
             include_patterns: Optional[List[str]] = None, exclude_patterns: Optional[List[str]] = None,
             output_type: str = "markdown_v2",
             **kwargs: Any) -> str:
        """Run the website crawling tool."""
        try:
            # Get current task if available
            current_task = kwargs.get('task', None)
            
            # Always ensure output_type is valid
            output_type = output_type if output_type else "markdown_v2"
            try:
                output_type_enum = OutputType(output_type.lower())
            except ValueError:
                output_type_enum = OutputType.MARKDOWN
            
            # Prepare extraction config with markdown_v2 format
            if not extraction_config:
                extraction_config = {
                    "type": "basic",
                    "params": {
                        "output_format": "markdown_v2",  # Always use markdown_v2
                        "word_count_threshold": 0,
                        "only_text": False,
                        "bypass_cache": True,
                        "process_iframes": True,
                        "excluded_tags": ["script", "style", "noscript"],
                        "html2text": {
                            "ignore_links": False,
                            "ignore_images": False,
                            "body_width": 0,
                            "unicode_snob": True,
                            "protect_links": True,
                            "bypass_tables": False,
                            "single_line_break": True
                        },
                        "markdown": {
                            "enabled": True,
                            "gfm": True,
                            "tables": True,
                            "breaks": True,
                            "smartLists": True,
                            "smartypants": True,
                            "xhtml": True
                        }
                    }
                }
            
            # Call the crawling function with enhanced parameters
            result = crawl_website(
                website_url=website_url,
                user_id=user_id,
                max_pages=max_pages,
                max_depth=max_depth,
                output_type=output_type_enum,
                wait_for=wait_for or "main, #main, .main, #content, .content, article, .post-content",
                css_selector=css_selector,
                include_patterns=include_patterns,
                exclude_patterns=exclude_patterns,
                task=current_task
            )
            return result
            
        except Exception as e:
            logger.error(f"Error in CrawlWebsiteTool: {str(e)}", exc_info=True)
            return json.dumps({
                "status": "error",
                "message": str(e)
            })

def crawl_website(
    website_url: str,
    user_id: int,
    max_pages: int = 100,
    max_depth: int = 3,
    output_type: OutputType = OutputType.MARKDOWN,
    batch_size: int = 10,
    wait_for: Optional[str] = None,
    css_selector: Optional[str] = None,
    include_patterns: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None,
    task: Optional[Any] = None
) -> str:
    """Core website crawling logic."""
    try:
        logger.info(f"Starting crawl for URL: {website_url}")
        
        # Initialize state for progress tracking
        state = CrawlerState(None, max_pages)
        state.add_url(website_url, 0)  # Start URL at depth 0
        
        # Update initial state
        if task:
            task.update_state(state='PROGRESS', meta={
                    'current': 0,
                    'total': max_pages,
                'status': 'Starting crawl',
                'url': website_url
            })
        
        # Create session with retry logic
        session = create_requests_session()
        headers = {
            "Authorization": f"Bearer {settings.CRAWL4AI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        while state.url_queue and state.pages_crawled < max_pages:
            # Get next batch of URLs to process
            batch_urls = state.get_next_batch(batch_size)
            current_depth = max(state.url_depths[url] for url in batch_urls)
            
            if current_depth > max_depth:
                logger.info(f"Reached maximum depth {max_depth}")
                break
            
            # Prepare request for batch with enhanced parameters
            request_data = {
                "urls": batch_urls[0] if len(batch_urls) == 1 else batch_urls,
                "priority": 10,
                "extraction_config": {
                    "type": "basic",
                    "params": {
                        "output_format": "markdown_v2",  # Always use markdown_v2
                        "word_count_threshold": 0,
                        "only_text": False,
                        "bypass_cache": True,
                        "process_iframes": True,
                        "excluded_tags": ["script", "style", "noscript"],
                        "html2text": {
                            "ignore_links": False,
                            "ignore_images": False,
                            "body_width": 0,
                            "unicode_snob": True,
                            "protect_links": True,
                            "bypass_tables": False,
                            "single_line_break": True
                        },
                        "markdown": {
                            "enabled": True,
                            "gfm": True,
                            "tables": True,
                            "breaks": True,
                            "smartLists": True,
                            "smartypants": True,
                            "xhtml": True
                        }
                    }
                },
                "crawler_params": {
                    **settings.CRAWL4AI_CRAWLER_PARAMS,
                    "wait_for": wait_for or "main, #main, .main, #content, .content, article, .post-content",
                    "remove_overlay_elements": True,
                    "delay_before_return_html": 5.0,
                    "wait_until": "networkidle0",
                    "javascript": True,
                    "scroll": True,
                    "wait_for_selector_timeout": 10000,
                    "verbose": True
                }
            }
            
            #logger.info(f"Sending request with data: {request_data}")
            
            try:
                # Submit crawl task
                response = session.post(
                    f"{settings.CRAWL4AI_URL}/crawl",
                    headers=headers,
                    json=request_data
                )
                response.raise_for_status()
                task_data = response.json()
                #logger.info(f"Task submission response: {task_data}")
                crawl_task_id = task_data["task_id"]
                #logger.info(f"Submitted batch of {len(batch_urls)} URLs, task ID: {crawl_task_id}")
                
                # Poll for results
                timeout = 600
                start_time = time.time()
                while True:
                    if time.time() - start_time > timeout:
                        raise TimeoutError(f"Task {crawl_task_id} timed out")
                    
                    result_response = session.get(
                        f"{settings.CRAWL4AI_URL}/task/{crawl_task_id}",
                        headers=headers,
                        stream=True  # Enable streaming for large responses
                    )
                    result_response.raise_for_status()
                    
                    # Read the response in chunks
                    content = b""
                    for chunk in result_response.iter_content(chunk_size=8192):
                        if chunk:
                            content += chunk
                    
                    try:
                        status = json.loads(content.decode('utf-8'))
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to decode JSON response: {str(e)}")
                        logger.error(f"Response content (first 1000 bytes): {content[:1000]}")
                        raise
                    
                    # Fix logging of dictionary objects
                    #logger.info(f"Task status response: {str(status)[:250]}")
                    
                    if status["status"] == "completed":
                        # Process results - handle both single result and batch results
                        results_to_process = []
                        if "result" in status:
                            # Single URL response
                            results_to_process.append(status["result"])
                        elif "results" in status:
                            # Batch response
                            results_to_process.extend(status["results"])
                        
                        #logger.info(f"Processing {len(results_to_process)} results")
                        
                        for result in results_to_process:
                            if not result:
                                continue
                                
                            #logger.info(f"Processing result for URL: {result.get('url', 'unknown')}")
                            #logger.info(f"Content keys available: {list(result.keys()) if result else 'No result'}")
                            
                            # Extract markdown content based on CrawlResult structure
                            markdown_content = None
                            # Log raw content for debugging
                            #logger.info(f"Raw markdown_v2: {str(result.get('markdown_v2', ''))[:250]}")
                            #logger.info(f"Raw markdown: {str(result.get('markdown', ''))[:250]}")
                            
                            # Try markdown_v2 first
                            md_v2 = result.get("markdown_v2")
                            if md_v2:
                                if isinstance(md_v2, dict) and "raw_markdown" in md_v2:
                                    markdown_content = md_v2["raw_markdown"]
                                    #logger.info(f"Found markdown_v2 content, length: {len(markdown_content)}")
                                else:
                                    markdown_content = str(md_v2)
                                    #logger.info(f"Found markdown_v2 string content, length: {len(markdown_content)}")
                            
                            # Fall back to markdown if needed
                            if not markdown_content:
                                md = result.get("markdown")
                                if md:
                                    if isinstance(md, dict) and "raw_markdown" in md:
                                        markdown_content = md["raw_markdown"]
                                        #logger.info("Using markdown raw_markdown content")
                                    else:
                                        markdown_content = str(md)
                                        #logger.info("Using markdown string content")
                            
                            # Fall back to text content if no markdown
                            if not markdown_content:
                                markdown_content = result.get("text", "")
                                if not markdown_content:
                                    markdown_content = result.get("cleaned_html", "")
                                if markdown_content:
                                    logger.info(f"Using fallback content, length: {len(markdown_content)}")
                            
                            # Store the result
                            url = result.get("url", "")
                            if url and url not in state.visited_urls and markdown_content:
                                state.mark_visited(url)
                                processed_result = {
                                    "url": url,
                                    "content": markdown_content,
                                    "metadata": result.get("metadata", {}),
                                    "links": result.get("links", {}),
                                    "media": result.get("media", {}),
                                    "success": True
                                }
                                state.results[url] = processed_result
                                #logger.info(f"Stored content for URL {url}, content length: {len(processed_result['content'])}")
                            
                                # Extract and queue new links if within depth limit
                                if current_depth < max_depth:
                                    # Get links from the links dictionary according to CrawlResult structure
                                    all_links = []
                                    links_dict = result.get("links", {})
                                    internal_links = links_dict.get("internal", [])
                                    for link_data in internal_links:
                                        if isinstance(link_data, dict):
                                            link = link_data.get("href")
                                            if link:
                                                all_links.append(link)
                                        elif isinstance(link_data, str):
                                            all_links.append(link_data)
                                    
                                    #logger.info(f"Found links for {url}: {all_links}")
                                    for link in all_links:
                                        # Apply include/exclude patterns if specified
                                        if include_patterns and not any(pattern in link for pattern in include_patterns):
                                            continue
                                        if exclude_patterns and any(pattern in link for pattern in exclude_patterns):
                                            continue
                                        state.add_url(link, current_depth + 1)
                            else:
                                logger.warning(f"Skipping result - URL: {url}, Has content: {bool(markdown_content)}, Already visited: {url in state.visited_urls}")
                        
                        # Update progress
                        logger.info(
                            f'Processed {state.pages_crawled} pages, {len(state.url_queue)} URLs in queue, depth {current_depth}'
                        )
                        if task:
                            task.update_state(state='PROGRESS', meta={
                                'current': state.pages_crawled,
                                'total': max_pages,
                                'status': f'Processing pages at depth {current_depth}',
                                'url': website_url,
                                'depth': current_depth,
                                'queue_size': len(state.url_queue)
                            })
                        break
                        
                    elif status["status"] == "failed":
                        raise Exception(f"Task failed: {status.get('error', 'Unknown error')}")
                    
                    time.sleep(2)
            except Exception as e:
                logger.error(f"Error processing batch: {str(e)}", exc_info=True)
                continue
        
        # Process final results
        all_content = []
        #logger.info(f"Processing final results. Number of results: {len(state.results)}")
        #logger.info(f"URLs with content: {list(state.results.keys())}")
        
        for url, result in state.results.items():
            #logger.info(f"Processing final content for URL {url}")
            # Get content based on output type
            content = None
            if output_type == OutputType.RAW_TEXT:
                # Use the stored markdown content and clean it up
                raw_text = result.get("content", "")
                if raw_text:
                    # Remove markdown formatting
                    content = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', raw_text)  # Remove links but keep text
                    content = re.sub(r'[*_~`]', '', content)  # Remove formatting characters
                    content = re.sub(r'#+\s+', '', content)  # Remove headers
                    content = re.sub(r'\n\s*[-*+]\s+', '\n', content)  # Remove list markers
                    content = re.sub(r'\s+', ' ', content).strip()  # Normalize whitespace
                    content = re.sub(r'\n\s*\n', '\n', content)  # Normalize line endings
                #logger.info(f"RAW_TEXT content length: {len(content) if content else 0}")
            elif output_type == OutputType.TEXT:
                content = result.get("content", "")  # Use stored content
                #logger.info(f"TEXT content length: {len(content) if content else 0}")
            elif output_type == OutputType.HTML:
                content = result.get("html", "")
                #logger.info(f"HTML content length: {len(content) if content else 0}")
            elif output_type == OutputType.CLEAN_HTML:
                content = result.get("cleaned_html", "")
                #logger.info(f"CLEAN_HTML content length: {len(content) if content else 0}")
            elif output_type == OutputType.STRUCTURED:
                content = result.get("extracted_content", "")
                #logger.info(f"STRUCTURED content length: {len(content) if content else 0}")
            elif output_type == OutputType.MEDIA:
                # Format media content as markdown with embedded media
                media_content = []
                if result.get("media", {}).get("images"):
                    media_content.extend([f"![{img.get('alt', '')}]({img['src']})" 
                                       for img in result["media"]["images"] if img.get("src")])
                if result.get("media", {}).get("videos"):
                    media_content.extend([f"Video: {vid['src']}" 
                                       for vid in result["media"]["videos"] if vid.get("src")])
                content = "\n".join(media_content)
                #logger.info(f"MEDIA content length: {len(content) if content else 0}")
            elif output_type == OutputType.FULL:
                # Combine all available content
                full_content = {
                    "url": result.get("url", ""),
                    "title": result.get("metadata", {}).get("title", ""),
                    "description": result.get("metadata", {}).get("description", ""),
                    "content": result.get("content", ""),
                    "cleaned_html": result.get("cleaned_html", ""),
                    "media": result.get("media", {}),
                    "links": result.get("links", {}),
                    "metadata": result.get("metadata", {})
                }
                content = json.dumps(full_content, indent=2)
                #logger.info(f"FULL content length: {len(content) if content else 0}")
            else:  # MARKDOWN
                # Log the raw result for debugging
                #logger.info(f"Raw result keys for MARKDOWN: {list(result.keys())}")
                #logger.info(f"Content field value length: {len(result.get('content', ''))}")
                content = result.get("content", "")  # Get the content we stored earlier
                #logger.info(f"MARKDOWN content length: {len(content) if content else 0}")
            
            #logger.info(f"Final content type: {output_type}, content length: {len(str(content)) if content else 0}")
            
            if content:
                formatted_content = f"URL: {url}\n\n"
                if result.get("metadata", {}).get("title"):
                    formatted_content += f"Title: {result['metadata']['title']}\n\n"
                formatted_content += str(content)
                formatted_content += "\n\n---\n\n"
                all_content.append(formatted_content)
                logger.info(f"Added formatted content for {url}, length: {len(formatted_content)}")
            else:
                logger.warning(f"No content to format for {url}")
        
        # Create final crawl result in database
        if all_content:
            final_content = '\n'.join(all_content)
            logger.info(f"Final combined content length: {len(final_content)}")
            crawl_result = CrawlResult.create_with_content(
                user=User.objects.get(id=user_id),
                website_url=website_url,
                content=final_content,
                links_visited={"internal": list(state.visited_urls)},
                total_links=len(state.visited_urls)
            )
            # log all_content first 250 characters
            logger.info(f"All content: {final_content[:250]}")
            result = {
                "status": "success",
                "website_url": website_url,
                "total_pages": len(state.results),
                "max_depth_reached": max(state.url_depths.values()),
                "crawl_result_id": crawl_result.id,
                "content": final_content,
                "content_type": output_type,
                # "metadata": {
                #     "total_links": len(state.visited_urls),
                #     "visited_urls": list(state.visited_urls),
                #     "pages_crawled": state.pages_crawled
                # },
                # "results": state.results
            }
            if task:
                task.update_state(state='PROGRESS', meta={
                    'current': state.pages_crawled,
                    'total': state.pages_crawled,
                    'status': 'Completed successfully',
                    'result': result
                })
        else:
            result = {
                "status": "success",
                "warning": "No valid content found",
                "website_url": website_url,
                "total_pages": 0,
                "max_depth_reached": 0,
                "content": "",
                "content_type": output_type,
                # "metadata": {
                #     "total_links": 0,
                #     "visited_urls": [],
                #     "pages_crawled": 0
                # },
                # "results": {}
            }
        
        logger.info(f"Completed crawl with {len(state.results)} pages")
        return json.dumps(result)

    except Exception as e:
        logger.error(f"Error in crawl_website: {str(e)}", exc_info=True)
        return json.dumps({
            "status": "error",
            "message": str(e)
        })

@shared_task(bind=True, base=AbortableTask)
def crawl_website_task(self, website_url: str, user_id: int, max_pages: int = 100, max_depth: int = 3,
                      wait_for: Optional[str] = None, css_selector: Optional[str] = None,
                      include_patterns: Optional[List[str]] = None, exclude_patterns: Optional[List[str]] = None) -> str:
    """Celery task wrapper for crawl_website function."""
    return crawl_website(
        website_url=website_url,
        user_id=user_id,
        max_pages=max_pages,
        max_depth=max_depth,
        wait_for=wait_for,
        css_selector=css_selector,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        task=self
    )
