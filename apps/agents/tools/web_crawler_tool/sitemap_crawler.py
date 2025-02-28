import logging
import json
from typing import Optional, List, Dict, Any, Union
from crewai.tools import BaseTool
from pydantic import BaseModel, Field, validator
from apps.agents.tools.sitemap_retriever_tool import SitemapRetrieverTool
from apps.agents.tools.web_crawler_tool import WebCrawlerTool, CrawlOutputFormat
from celery import shared_task
from apps.agents.tasks.base import ProgressTask
from celery.contrib.abortable import AbortableTask
import time

logger = logging.getLogger(__name__)

class SitemapCrawlerSchema(BaseModel):
    """Input schema for SitemapCrawler."""
    url: str = Field(
        ...,
        description="The URL of the website to retrieve a sitemap for and then crawl"
    )
    user_id: int = Field(
        ..., 
        description="ID of the user initiating the crawl"
    )
    max_sitemap_urls: int = Field(
        default=20,
        description="Maximum number of URLs to retrieve from the sitemap"
    )
    max_pages_per_url: int = Field(
        default=1,
        description="Maximum number of pages to crawl for each URL from the sitemap"
    )
    max_depth: int = Field(
        default=0,
        description="Maximum depth for crawling each URL (0 means just the URL itself)"
    )
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
    
    @validator('url')
    def validate_url(cls, v):
        """Validate URL format."""
        if not v.startswith(('http://', 'https://')):
            raise ValueError("URL must start with http:// or https://")
        return v

class SitemapCrawlerTool(BaseTool):
    """
    A tool that first retrieves a sitemap for a website and then crawls the URLs found in the sitemap.
    This combines the functionality of the SitemapRetrieverTool and WebCrawlerTool.
    """
    name: str = "Sitemap Crawler Tool"
    description: str = """
    A tool that first retrieves a sitemap for a website and then crawls the URLs found in the sitemap.
    This is useful for efficiently crawling websites with a large number of pages, as it first identifies
    the most important URLs from the sitemap and then crawls those URLs to extract content.
    """
    args_schema: type = SitemapCrawlerSchema
    
    def _run(self, url: str, user_id: int, max_sitemap_urls: int = 20, max_pages_per_url: int = 1,
             max_depth: int = 0, output_format: str = "text", include_patterns: Optional[List[str]] = None,
             exclude_patterns: Optional[List[str]] = None, stay_within_domain: bool = True,
             cache: bool = True, stealth: bool = True, device: str = "desktop", 
             timeout: int = 60000, **kwargs) -> str:
        """
        Run the sitemap crawler tool.
        
        Args:
            url: URL of the website to retrieve a sitemap for and then crawl
            user_id: ID of the user initiating the crawl
            max_sitemap_urls: Maximum number of URLs to retrieve from the sitemap
            max_pages_per_url: Maximum number of pages to crawl for each URL from the sitemap
            max_depth: Maximum depth for crawling each URL
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
            # Get current task if available
            current_task = kwargs.get('task', None)
            
            # Step 1: Retrieve sitemap
            logger.info(f"Retrieving sitemap for {url}")
            if current_task:
                current_task.update_progress(0, 100, "Retrieving sitemap", url=url)
            
            sitemap_tool = SitemapRetrieverTool()
            sitemap_result_json = sitemap_tool._run(
                url=url,
                user_id=user_id,
                max_pages=max_sitemap_urls,
                output_format="json"
            )
            
            sitemap_result = json.loads(sitemap_result_json)
            
            if not sitemap_result.get("success", False):
                logger.error(f"Failed to retrieve sitemap for {url}: {sitemap_result.get('message', 'Unknown error')}")
                return json.dumps({
                    "status": "error",
                    "message": f"Failed to retrieve sitemap: {sitemap_result.get('message', 'Unknown error')}"
                })
            
            # Extract URLs from sitemap
            sitemap_urls = []
            for url_entry in sitemap_result.get("urls", []):
                if "loc" in url_entry:
                    sitemap_urls.append(url_entry["loc"])
            
            if not sitemap_urls:
                logger.warning(f"No URLs found in sitemap for {url}")
                return json.dumps({
                    "status": "warning",
                    "message": "No URLs found in sitemap",
                    "sitemap_result": sitemap_result
                })
            
            logger.info(f"Found {len(sitemap_urls)} URLs in sitemap for {url}")
            
            # Step 2: Crawl each URL from the sitemap
            crawler_tool = WebCrawlerTool()
            all_results = []
            
            for i, sitemap_url in enumerate(sitemap_urls[:max_sitemap_urls]):
                logger.info(f"Crawling URL {i+1}/{min(len(sitemap_urls), max_sitemap_urls)}: {sitemap_url}")
                
                if current_task:
                    progress_percentage = int((i / min(len(sitemap_urls), max_sitemap_urls)) * 100)
                    current_task.update_progress(
                        progress_percentage, 
                        100, 
                        f"Crawling URL {i+1}/{min(len(sitemap_urls), max_sitemap_urls)}", 
                        url=sitemap_url
                    )
                
                try:
                    crawler_result_json = crawler_tool._run(
                        start_url=sitemap_url,
                        user_id=user_id,
                        max_pages=max_pages_per_url,
                        max_depth=max_depth,
                        output_format=output_format,
                        include_patterns=include_patterns,
                        exclude_patterns=exclude_patterns,
                        stay_within_domain=stay_within_domain,
                        cache=cache,
                        stealth=stealth,
                        device=device,
                        timeout=timeout
                    )
                    
                    crawler_result = json.loads(crawler_result_json)
                    
                    if crawler_result.get("status") == "success":
                        # Add the sitemap URL to the result for reference
                        crawler_result["sitemap_url"] = sitemap_url
                        all_results.append(crawler_result)
                    else:
                        logger.warning(f"Failed to crawl {sitemap_url}: {crawler_result.get('message', 'Unknown error')}")
                        
                except Exception as e:
                    logger.error(f"Error crawling {sitemap_url}: {str(e)}", exc_info=True)
            
            # Create final result
            final_result = {
                "status": "success",
                "sitemap_url": url,
                "total_sitemap_urls": len(sitemap_urls),
                "crawled_urls": len(all_results),
                "results": all_results
            }
            
            if current_task:
                current_task.update_progress(100, 100, "Completed successfully", result=final_result)
            
            logger.info(f"Completed sitemap crawl for {url} with {len(all_results)} URLs crawled")
            return json.dumps(final_result, indent=2)
            
        except Exception as e:
            logger.error(f"Error in SitemapCrawlerTool: {str(e)}", exc_info=True)
            return json.dumps({
                "status": "error",
                "message": str(e)
            })

class SitemapCrawlerAbortableTask(AbortableTask, ProgressTask):
    """Abortable task that supports progress reporting"""
    pass

@shared_task(bind=True, base=SitemapCrawlerAbortableTask, time_limit=1200, soft_time_limit=1140)
def sitemap_crawler_task(self, url: str, user_id: int, max_sitemap_urls: int = 20, max_pages_per_url: int = 1,
                         max_depth: int = 0, output_format: str = "text", include_patterns: Optional[List[str]] = None,
                         exclude_patterns: Optional[List[str]] = None, stay_within_domain: bool = True,
                         cache: bool = True, stealth: bool = True, device: str = "desktop",
                         timeout: int = 60000) -> str:
    """Celery task wrapper for SitemapCrawlerTool."""
    start_time = time.time()
    logger.info(f"Starting sitemap_crawler_task for {url}, user_id={user_id}, max_sitemap_urls={max_sitemap_urls}")
    
    try:
        tool = SitemapCrawlerTool()
        result = tool._run(
            url=url,
            user_id=user_id,
            max_sitemap_urls=max_sitemap_urls,
            max_pages_per_url=max_pages_per_url,
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
        logger.info(f"Completed sitemap_crawler_task for {url} in {elapsed_time:.2f} seconds")
        return result
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(f"Error in sitemap_crawler_task after {elapsed_time:.2f} seconds: {str(e)}", exc_info=True)
        return json.dumps({
            "status": "error",
            "message": str(e)
        }) 