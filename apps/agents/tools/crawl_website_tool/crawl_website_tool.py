import logging
import time
import json
import re
from typing import Optional, Dict, Any, Type, List, Literal, Union
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from enum import Enum
from pydantic import BaseModel, Field, HttpUrl
from apps.agents.tools.base_tool import BaseTool
from django.conf import settings
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

class OutputType(str, Enum):
    HTML = "html"  # Raw HTML
    CLEANED_HTML = "cleaned_html"  # Cleaned HTML
    METADATA = "metadata"  # Metadata only
    MARKDOWN = "markdown"  # Markdown formatted content
    TEXT = "text"  # Plain text (converted from markdown)
    FULL = "full"  # All formats combined for SEO analysis

class CacheMode(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    READ_ONLY = "read_only"
    WRITE_ONLY = "write_only"
    BYPASS = "bypass"

class CrawlWebsiteToolSchema(BaseModel):
    """Input for CrawlWebsiteTool."""
    website_url: Union[str, List[str]] = Field(..., description="Single website URL or list of URLs to crawl") 
    user_id: int = Field(..., description="ID of the user initiating the crawl")
    max_pages: int = Field(default=100, description="Maximum number of pages to crawl")
    max_depth: int = Field(default=3, description="Maximum depth for crawling")
    output_type: OutputType = Field(default=OutputType.MARKDOWN, description="Type of output content")
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

def create_requests_session(
    retries: int = 3,
    backoff_factor: float = 0.3,
    status_forcelist: List[int] = (500, 502, 503, 504),
    timeout: int = 60
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
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    session.timeout = timeout
    return session

def _parse_urls(website_url: Union[str, List[str]]) -> List[str]:
    """Parse website_url input into list of URLs."""
    if isinstance(website_url, str):
        # Split by common delimiters if string contains multiple URLs
        if any(d in website_url for d in [',', ';', '\n']):
            urls = [u.strip() for u in re.split(r'[,;\n]', website_url)]
            # Filter out empty strings
            urls = [u for u in urls if u]
        else:
            # Single URL
            urls = [website_url.strip()]
    elif isinstance(website_url, list):
        # Already a list of URLs
        urls = [u.strip() if isinstance(u, str) else u for u in website_url]
    else:
        # Invalid input
        urls = []
    
    # Ensure all URLs are properly formatted
    sanitized_urls = []
    for url in urls:
        # Check if URL is valid and add scheme if missing
        if url and isinstance(url, str):
            # Add http:// if no scheme provided
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            sanitized_urls.append(url)
    
    return sanitized_urls

class CrawlWebsiteTool(BaseTool):
    """
    A tool that can crawl websites and extract content in various formats (HTML, cleaned HTML, metadata, or markdown).
    """
    name: str = "Crawl and Read Website Content"
    description: str = """A tool that can crawl websites and extract content in various formats (HTML, cleaned HTML, metadata, or markdown)."""
    args_schema: Type[BaseModel] = CrawlWebsiteToolSchema
    
    def _run(self, website_url: str, user_id: int, max_pages: int = 100, max_depth: int = 3,
             wait_for: Optional[str] = None, css_selector: Optional[str] = None,
             include_patterns: Optional[List[str]] = None, exclude_patterns: Optional[List[str]] = None,
             output_type: str = "markdown",
             **kwargs: Any) -> str:
        """Run the website crawling tool."""
        try:
            # Get current task if available
            current_task = kwargs.get('task', None)
            
            # Ensure output_type is valid
            try:
                output_type_enum = OutputType(output_type.lower())
            except ValueError:
                output_type_enum = OutputType.MARKDOWN
            
            # Parse URLs
            urls = _parse_urls(website_url)
            if not urls:
                return json.dumps({
                    "status": "error",
                    "message": "No valid URLs provided"
                })

            # Update progress if task exists
            if current_task:
                current_task.update_progress(0, 100, "Starting crawl")
            
            # Prepare request data
            # Firecrawl /crawl endpoint takes a single URL as the starting point for crawling
            request_data = {
                "url": urls[0],
                "limit": max_pages,
                "scrapeOptions": {
                    "formats": ["markdown"],  # Only get markdown by default
                }
            }
            
            # Adjust formats based on output type
            if output_type_enum == OutputType.TEXT:
                # For TEXT output, we only need HTML (we'll extract text with BeautifulSoup)
                request_data["scrapeOptions"]["formats"] = ["html"]
            elif output_type_enum == OutputType.HTML or output_type_enum == OutputType.CLEANED_HTML:
                # For HTML outputs, we only need HTML
                request_data["scrapeOptions"]["formats"] = ["html"]
            elif output_type_enum == OutputType.METADATA:
                # For metadata, we need links
                request_data["scrapeOptions"]["formats"] = ["markdown", "links"]
            elif output_type_enum == OutputType.FULL:
                # For full output, we need everything
                request_data["scrapeOptions"]["formats"] = ["html", "markdown", "links"]
                
            # If wait_for parameter is provided, use it in the scrapeOptions
            if wait_for:
                request_data["scrapeOptions"]["waitFor"] = int(wait_for) if wait_for.isdigit() else wait_for
                
            # If css_selector is provided, include it as a tag to focus on
            if css_selector:
                request_data["scrapeOptions"]["includeTags"] = [css_selector]
            
            # Add parameters based on Firecrawl documentation
            if max_depth > 0:
                request_data["maxDepth"] = max_depth
                
            # Enable backward links to improve coverage (gets pages that aren't direct children)
            request_data["allowBackwardLinks"] = True
            
            # Only stay on the same domain by default
            request_data["allowExternalLinks"] = False
            
            # Add include/exclude paths if provided, else '/.*' 
            if include_patterns:
                request_data["includePaths"] = include_patterns
            else:
                request_data["includePaths"] = ["/.*"]
            
            if exclude_patterns:
                request_data["excludePaths"] = exclude_patterns
            
            # Log the request for debugging
            logger.info(f"Firecrawl request parameters: {request_data}")
            
            # Setup session and headers
            session = create_requests_session()
            # Use FIRECRAWL_API_KEY if available, otherwise fall back to CRAWL4AI_API_KEY
            api_key = getattr(settings, 'FIRECRAWL_API_KEY', '')
            headers = {
                "Content-Type": "application/json"
            }
            
            # Submit crawl task
            logger.info(f"Submitting crawl request for URLs: {urls}")

            try:
                response = session.post(
                    f"{settings.FIRECRAWL_URL}/v1/crawl",
                    headers=headers,
                    json=request_data
                )
            # log endpoint, headers and request data
                logger.debug(f"Crawl request: Headers {headers}, Request Data {request_data}")
                response.raise_for_status()
                
                task_data = response.json()
                if not task_data.get("success"):
                    error_message = f"Failed to submit crawl task: {task_data.get('error', 'Unknown error')}"
                    logger.error(error_message)
                    return json.dumps({
                        "status": "error",
                        "message": error_message
                    })
            except requests.exceptions.HTTPError as e:
                logger.error(f"HTTP error during crawl request: {str(e)}")
                # Log response content for debugging
                try:
                    error_details = response.json() if response.content else "No response details"
                    logger.error(f"Error response details: {error_details}")
                except Exception:
                    logger.error(f"Could not parse error response. Raw content: {response.content}")
                
                return json.dumps({
                    "status": "error",
                    "message": f"HTTP error: {str(e)}"
                })
            except Exception as e:
                logger.error(f"Unexpected error during crawl request: {str(e)}")
                return json.dumps({
                    "status": "error",
                    "message": f"Failed to submit crawl: {str(e)}"
                })
                
            crawl_task_id = task_data.get("id")
            crawl_task_url = task_data.get("url")
            
            if current_task:
                current_task.update_progress(10, 100, f"Submitted crawl task {crawl_task_id}")
            
            # Poll for results
            timeout = 600
            start_time = time.time()
            polling_interval = 5  # seconds between status checks
            
            # Poll for results of crawl using the provided SDK pattern
            while True:
                if time.time() - start_time > timeout:
                    return json.dumps({
                        "status": "error", 
                        "message": f"Task {crawl_task_id} timed out after {timeout} seconds"
                    })
                
                result_response = session.get(
                    crawl_task_url,
                    headers=headers
                )
                result_response.raise_for_status()
                status = result_response.json()
                
                # Log status information for debugging
                logger.info(f"Crawl status: {status.get('status', 'unknown')}, Total: {status.get('total', 0)}, Completed: {status.get('completed', 0)}")
                
                # Update progress if available
                if current_task:
                    # Calculate progress based on completed vs total pages
                    total_pages = status.get("total", 0)
                    completed_pages = status.get("completed", 0)
                    
                    # Extract any available URLs from the current status
                    crawled_urls = []
                    if "data" in status and isinstance(status["data"], list):
                        for item in status["data"]:
                            url = item.get("metadata", {}).get("sourceURL", "")
                            if url:
                                crawled_urls.append(url)
                    
                    if total_pages > 0:
                        progress = min(0.9, completed_pages / total_pages)
                    else:
                        # Fall back to status-based estimation
                        status_type = status.get("status")
                        if status_type == "completed":
                            progress = 1.0
                        elif status_type == "scraping":
                            # Estimate progress based on time elapsed
                            elapsed = (time.time() - start_time) / timeout
                            progress = min(0.8, elapsed)
                        else:
                            progress = 0.1
                    current_task.update_progress(
                        int(10 + progress * 80),
                        100,
                        f"Crawling in progress: {int(progress * 100)}%",
                        crawled_urls=crawled_urls
                    )
                
                if status.get("status") == "completed":
                    break
                elif status.get("status") == "failed":
                    return json.dumps({
                        "status": "error",
                        "message": f"Crawl task failed: {status.get('error', 'Unknown error')}"
                    })
                
                # Wait before polling again
                time.sleep(polling_interval)
            
            # Process results
            all_content = []
            collected_data = []
            
            # Collect all the data from the response (including pagination)
            def collect_response_data(response_data):
                if "data" in response_data:
                    data_items = response_data["data"]
                    logger.info(f"Collected {len(data_items)} items from response")
                    collected_data.extend(data_items)
                    
                    # Continue fetching if there's a next page
                    next_url = response_data.get("next")
                    if next_url:
                        logger.info(f"Fetching next page of results: {next_url}")
                        next_response = session.get(
                            next_url,
                            headers=headers
                        )
                        next_response.raise_for_status()
                        collect_response_data(next_response.json())
                else:
                    logger.warning(f"No 'data' field found in response. Response keys: {list(response_data.keys())}")
            
            # Start collection with initial response
            collect_response_data(status)
            
            # Log summary of collected data
            logger.info(f"Total data items collected: {len(collected_data)}")
            domain_count = {}
            for item in collected_data:
                url = item.get("metadata", {}).get("sourceURL", "")
                if url:
                    parsed = urlparse(url)
                    domain = parsed.netloc
                    domain_count[domain] = domain_count.get(domain, 0) + 1
            
            logger.info(f"Domain distribution of crawled pages: {domain_count}")
            
            # Process all collected data
            for item in collected_data:
                url = item.get("metadata", {}).get("sourceURL", "")
                if not url:
                    continue
                
                content = None
                if output_type_enum == OutputType.HTML:
                    content = item.get("html", "")
                elif output_type_enum == OutputType.CLEANED_HTML:
                    content = item.get("html", "")  # Firecrawl doesn't have a specific cleaned_html
                elif output_type_enum == OutputType.METADATA:
                    content = item.get("metadata", {})
                elif output_type_enum == OutputType.FULL:
                    content = {
                        "html": item.get("html", ""),
                        "markdown": item.get("markdown", ""),
                        "metadata": item.get("metadata", {}),
                        "status_code": item.get("metadata", {}).get("statusCode", 200)
                    }
                elif output_type_enum == OutputType.TEXT:
                    # Use BeautifulSoup to extract plain text from HTML
                    html_content = item.get("html", "")
                    soup = BeautifulSoup(html_content, "html.parser")
                    
                    # If a CSS selector was provided, focus only on that content
                    if css_selector:
                        selected_elements = soup.select(css_selector)
                        if selected_elements:
                            # Join text from all matching elements with line breaks
                            content = "\n\n".join([elem.get_text(separator="\n", strip=True) for elem in selected_elements])
                        else:
                            # Fallback to whole document if selector doesn't match
                            content = soup.get_text(separator="\n", strip=True)
                    else:
                        # Process full document if no selector specified
                        # Remove script and style elements that contain non-visible content
                        for script_or_style in soup(["script", "style", "meta", "noscript"]):
                            script_or_style.decompose()
                            
                        # Get text with better spacing
                        # 1. Get text with newlines preserved
                        lines = soup.get_text(separator="\n", strip=True).splitlines()
                        # 2. Remove empty lines and excessive whitespace
                        lines = [line.strip() for line in lines if line.strip()]
                        # 3. Join with newlines
                        content = "\n".join(lines)
                else:  # MARKDOWN (default)
                    # Make sure we properly handle markdown content
                    markdown_content = item.get("markdown", "")
                    if not markdown_content and item.get("html"):
                        # If for some reason we didn't get markdown but have HTML, log a warning
                        logger.warning(f"No markdown content available for URL: {url}, falling back to HTML")
                        # We could convert HTML to markdown here if needed, but for now just use HTML
                    content = markdown_content
                
                if content:
                    all_content.append({
                        "url": url,
                        "content": content
                    })
            
            # Create final result
            final_result = {
                "status": "success",
                "website_url": website_url,
                "total_pages": len(all_content),
                "results": all_content
            }
            
            # Update final progress
            if current_task:
                # Extract all URLs from the final result for reporting
                crawled_urls = [item.get("url", "") for item in all_content if item.get("url")]
                current_task.update_progress(100, 100, "Completed successfully", result=final_result, crawled_urls=crawled_urls)
            
            logger.info(f"Completed crawl with {len(all_content)} pages")
            return json.dumps(final_result)
            
        except Exception as e:
            logger.error(f"Error in CrawlWebsiteTool: {str(e)}", exc_info=True)
            return json.dumps({
                "status": "error",
                "message": str(e)
            })
