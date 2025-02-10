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
from apps.agents.tasks.base import ProgressTask

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

# Update OutputType to only include native formats
class OutputType(str, Enum):
    HTML = "html"  # Raw HTML
    CLEANED_HTML = "cleaned_html"  # Cleaned HTML
    METADATA = "metadata"  # Metadata only
    MARKDOWN = "markdown"  # Markdown formatted content

class CrawlWebsiteToolSchema(BaseModel):
    """Input for CrawlWebsiteTool."""
    website_url: str = Field(..., description="Website URL to crawl")
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

class CrawlerState:
    """Manages crawler state in memory."""
    def __init__(self, task_id: str, max_pages: int):
        self.task_id = task_id
        self.max_pages = max_pages
        self.pages_crawled = 0
        self.url_queue = []
        self.visited_urls = set()
        self.url_depths = {}
        self.results = {}
        
    def add_url(self, url: str, depth: int) -> None:
        if url not in self.visited_urls and url not in self.url_depths:
            self.url_queue.append(url)
            self.url_depths[url] = depth
    
    def mark_visited(self, url: str) -> None:
        if url not in self.visited_urls:
            self.visited_urls.add(url)
            self.pages_crawled += 1
    
    def get_next_batch(self, batch_size: int) -> List[str]:
        # Calculate remaining pages we can crawl
        remaining_pages = self.max_pages - self.pages_crawled
        # Use the smaller of batch_size or remaining_pages
        actual_batch_size = min(batch_size, remaining_pages, len(self.url_queue))
        batch = self.url_queue[:actual_batch_size]
        self.url_queue = self.url_queue[actual_batch_size:]
        return batch

class CrawlWebsiteTool(BaseTool):
    name: str = "Crawl and Read Website Content"
    description: str = """A tool that can crawl websites and extract content in various formats (HTML, cleaned HTML, metadata, or markdown)."""
    args_schema: Type[BaseModel] = CrawlWebsiteToolSchema
    
    def _prepare_request_data(self, params: CrawlWebsiteToolSchema) -> Dict[str, Any]:
        """Prepare request data based on parameters."""
        return {
            "urls": params.website_url,
            "priority": 10,
            "crawler_params": {
                **settings.CRAWL4AI_CRAWLER_PARAMS,
                "wait_for": params.wait_for or "body",
                "javascript": True,
                "scroll": True,
                "wait_for_selector_timeout": 10000
            }
        }

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
            
            # Call the crawling function
            result = crawl_website(
                website_url=website_url,
                user_id=user_id,
                max_pages=max_pages,
                max_depth=max_depth,
                output_type=output_type_enum,
                wait_for=wait_for,
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
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    session.timeout = timeout
    return session

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
        
        # Initialize state
        state = CrawlerState(None, max_pages)
        state.add_url(website_url, 0)
        
        if task:
            task.update_progress(0, max_pages, "Starting crawl", url=website_url)
        
        # Setup session
        session = create_requests_session()
        headers = {
            "Authorization": f"Bearer {settings.CRAWL4AI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        while state.url_queue and state.pages_crawled < max_pages:
            # Get next batch, respecting max_pages limit
            batch_urls = state.get_next_batch(batch_size)
            if not batch_urls:  # No more URLs to process within limits
                break
                
            current_depth = max(state.url_depths[url] for url in batch_urls)
            
            if current_depth > max_depth:
                logger.info(f"Reached maximum depth {max_depth}")
                break
            
            request_data = {
                "urls": batch_urls[0] if len(batch_urls) == 1 else batch_urls,
                "priority": 10,
                "crawler_params": {
                    **settings.CRAWL4AI_CRAWLER_PARAMS,
                    "wait_for": wait_for or "body",
                    "javascript": True,
                    "scroll": True,
                    "wait_for_selector_timeout": 10000
                }
            }
            
            try:
                # Submit crawl task
                response = session.post(
                    f"{settings.CRAWL4AI_URL}/crawl",
                    headers=headers,
                    json=request_data
                )
                response.raise_for_status()
                
                task_data = response.json()
                crawl_task_id = task_data["task_id"]
                
                # Poll for results
                timeout = 600
                start_time = time.time()
                while True:
                    if time.time() - start_time > timeout:
                        raise TimeoutError(f"Task {crawl_task_id} timed out")
                    
                    result_response = session.get(
                        f"{settings.CRAWL4AI_URL}/task/{crawl_task_id}",
                        headers=headers,
                        stream=True
                    )
                    result_response.raise_for_status()
                    
                    content = b""
                    for chunk in result_response.iter_content(chunk_size=8192):
                        if chunk:
                            content += chunk
                    
                    status = json.loads(content.decode('utf-8'))
                    
                    if status["status"] == "completed":
                        results_to_process = []
                        if "result" in status:
                            results_to_process.append(status["result"])
                        elif "results" in status:
                            results_to_process.extend(status["results"])
                        
                        for result in results_to_process:
                            if not result:
                                continue
                            
                            url = result.get("url", "")
                            if url and url not in state.visited_urls:
                                state.mark_visited(url)
                                state.results[url] = result
                                
                                # Extract and queue new links if within depth limit
                                if current_depth < max_depth:
                                    links_dict = result.get("links", {})
                                    internal_links = links_dict.get("internal", [])
                                    for link_data in internal_links:
                                        if isinstance(link_data, dict):
                                            link = link_data.get("href")
                                            if link:
                                                if include_patterns and not any(pattern in link for pattern in include_patterns):
                                                    continue
                                                if exclude_patterns and any(pattern in link for pattern in exclude_patterns):
                                                    continue
                                                state.add_url(link, current_depth + 1)
                        
                        logger.info(f'Processed {state.pages_crawled} pages, {len(state.url_queue)} URLs in queue')
                        if task:
                            task.update_progress(
                                current=state.pages_crawled,
                                total=max_pages,
                                status=f'Processing pages at depth {current_depth}'
                            )
                        break
                    elif status["status"] == "failed":
                        raise Exception(f"Task failed: {status.get('error', 'Unknown error')}")
                    
                    time.sleep(2)
            except Exception as e:
                logger.error(f"Error processing batch: {str(e)}", exc_info=True)
                continue
        
        # Process results
        all_content = []
        for url, result in state.results.items():
            content = None
            if output_type == OutputType.HTML:
                content = result.get("html", "")
            elif output_type == OutputType.CLEANED_HTML:
                content = result.get("cleaned_html", "")
            elif output_type == OutputType.METADATA:
                content = result.get("metadata", {})
            else:  # MARKDOWN (default)
                content = result.get("markdown", "")
            
            if content:
                formatted_content = {
                    "url": url,
                    "content": content
                }
                all_content.append(formatted_content)
                logger.info(f"Added content for {url}, type: {output_type}")
            else:
                logger.warning(f"No content found for {url} with type {output_type}")
        
        # Create final result
        if all_content:
            result = {
                "status": "success",
                "website_url": website_url,
                "total_pages": len(state.results),
                "results": all_content
            }
            
            crawl_result = CrawlResult.create_with_content(
                user=User.objects.get(id=user_id),
                website_url=website_url,
                content=json.dumps(all_content),
                links_visited={"internal": list(state.visited_urls)},
                total_links=len(state.visited_urls)
            )
            result["crawl_result_id"] = crawl_result.id
            
            if task:
                task.update_progress(
                    current=state.pages_crawled,
                    total=state.pages_crawled,
                    status='Completed successfully',
                    result=result
                )
        else:
            result = {
                "status": "success",
                "warning": "No valid content found",
                "website_url": website_url,
                "total_pages": 0,
                "content": "",
                "content_type": output_type,
            }
        
        logger.info(f"Completed crawl with {len(state.results)} pages")
        return json.dumps(result)

    except Exception as e:
        logger.error(f"Error in crawl_website: {str(e)}", exc_info=True)
        return json.dumps({
            "status": "error",
            "message": str(e)
        })

class CrawlWebsiteAbortableTask(AbortableTask, ProgressTask):
    """Abortable task that supports progress reporting"""
    pass

@shared_task(bind=True, base=CrawlWebsiteAbortableTask)
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
