import logging
import json
import time
from typing import Optional, List, Dict, Any, ClassVar, Callable
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from apps.agents.tools.base_tool import BaseTool
from pydantic import BaseModel, Field, field_validator, AnyHttpUrl
from apps.agents.tools.sitemap_retriever_tool.sitemap_retriever_tool import SitemapRetrieverTool
from apps.agents.utils.rate_limited_fetcher import RateLimitedFetcher # Import the utility
from celery import shared_task
from apps.agents.tasks.base import ProgressTask
from celery.contrib.abortable import AbortableTask

logger = logging.getLogger(__name__)

# Define Output Formats (similar to WebCrawlerTool but maybe simplified)
class ContentOutputFormat:
    TEXT = "text"
    HTML = "html"
    METADATA = "metadata"

class SitemapCrawlerSchema(BaseModel):
    """Input schema for Sitemap Content Fetcher."""
    url: AnyHttpUrl = Field(
        ...,
        description="The URL of the website to retrieve a sitemap for and fetch content from."
    )
    user_id: int = Field(
        ...,
        description="ID of the user initiating the operation."
    )
    max_sitemap_urls_to_process: int = Field(
        default=50,
        description="Maximum number of URLs from the sitemap to fetch content for.",
        gt=0
    )
    max_sitemap_retriever_pages: int = Field(
        default=1000,
        description="Maximum number of URLs for the SitemapRetrieverTool to find initially.",
        gt=0
    )
    requests_per_second: float = Field(
        default=5.0,
        description="Maximum desired requests per second for fetching page content. Will be lowered if robots.txt Crawl-delay is stricter.",
        gt=0
    )
    output_format: str = Field(
        default=ContentOutputFormat.TEXT,
        description=f"Format of the output content ({ContentOutputFormat.TEXT}, {ContentOutputFormat.HTML}, {ContentOutputFormat.METADATA})."
    )
    timeout: int = Field(
        default=15000, # Milliseconds
        description="Timeout in milliseconds for each page content request.",
        gt=0
    )

    @field_validator('output_format')
    def validate_output_format(cls, v):
        valid_formats = [ContentOutputFormat.TEXT, ContentOutputFormat.HTML, ContentOutputFormat.METADATA]
        if v not in valid_formats:
            raise ValueError(f"output_format must be one of: {', '.join(valid_formats)}")
        return v

    model_config = {
        "arbitrary_types_allowed": True,
        "extra": "forbid"
    }

class SitemapCrawlerTool(BaseTool):
    """
    Retrieves a website's sitemap and then fetches the content of URLs found within it,
    respecting robots.txt rate limits via RateLimitedFetcher.
    """
    name: str = "Sitemap Content Fetcher Tool"
    description: str = (
        "Retrieves a website's sitemap using SitemapRetrieverTool, then fetches the content "
        "(text, HTML, or metadata) for a specified number of URLs found in the sitemap, "
        "respecting robots.txt Crawl-delay."
    )
    args_schema: type = SitemapCrawlerSchema

    # Allow arbitrary types and extra fields for instance attributes like sitemap_retriever
    model_config = {
        "arbitrary_types_allowed": True,
        "extra": "allow"
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.sitemap_retriever = SitemapRetrieverTool()

    # Helper method to determine the progress update function
    def _get_progress_updater(self, progress_callback: Optional[Callable]) -> Callable:
        if progress_callback:
            return progress_callback
        else:
            # Return a no-op function if no callback is provided
            logger.debug("No progress_callback provided to SitemapCrawlerTool, progress updates disabled.")
            return lambda *args, **kwargs: None 

    # Helper method to extract content based on format
    def _extract_content(self, html_content: Optional[str], content_type: str, output_format: str) -> Optional[str]:
        if not html_content:
            return None
        if output_format == ContentOutputFormat.HTML:
            return html_content
        elif output_format == ContentOutputFormat.METADATA:
            return self._extract_metadata(html_content)
        elif output_format == ContentOutputFormat.TEXT:
            try:
                # Use BeautifulSoup to parse HTML and extract text
                soup = BeautifulSoup(html_content, 'html.parser')
                # Remove script and style elements before extracting text
                for script_or_style in soup(["script", "style"]):
                    script_or_style.decompose()
                # Get text, separating blocks with spaces, and stripping whitespace
                return soup.get_text(separator=' ', strip=True)
            except Exception as e:
                logger.warning(f"Failed to extract text from HTML content: {e}")
                # Fallback to returning raw content if parsing fails?
                # Or return None? Returning None might be safer.
                return None
        else:
            raise ValueError(f"Unknown output_format: {output_format}")

    # --- Main Execution ---
    def _run(
        self,
        url: AnyHttpUrl,
        user_id: int,
        max_sitemap_urls_to_process: int = 50, # Limit URLs *processed* after retrieval
        max_sitemap_retriever_pages: int = 1000, # Limit URLs *retrieved* by the sitemap tool
        requests_per_second: float = 5.0, # Default user rate limit
        output_format: ContentOutputFormat = ContentOutputFormat.TEXT,
        timeout: int = 15000,
        progress_callback: Optional[Callable] = None,
    ) -> str:
        start_time = time.time()
        str_url = str(url)
        parsed_url = urlparse(str_url)
        # Normalize domain consistently: remove leading 'www.'
        domain = parsed_url.netloc.replace("www.", "") 
        if not domain:
            # Use a more specific error message
            error_msg = f"Could not parse domain from input URL: {str_url}"
            logger.error(error_msg)
            raise ValueError(error_msg)
            
        processed_content = []
        total_urls_processed = 0
        errors = []
        sitemap_source_url = None
        total_sitemap_urls_found = 0

        # Determine the progress reporting method
        update_progress = self._get_progress_updater(progress_callback)

        try:
            update_progress(0, max_sitemap_urls_to_process, "Retrieving sitemap")
            logger.info(f"Retrieving sitemap for {str_url} (Max URLs: {max_sitemap_retriever_pages}) using SitemapRetrieverTool")
            
            # 1. Retrieve Sitemap URLs and Crawl Delay
            retriever_result = self.sitemap_retriever._run(
                url=str_url,
                user_id=user_id, # Pass user_id if needed by retriever
                max_pages=max_sitemap_retriever_pages,
                requests_per_second=requests_per_second # Pass user RPS setting to retriever (for its internal init)
            )

            if not retriever_result or not retriever_result.get("success"):
                 error_msg = f"SitemapRetrieverTool failed: {retriever_result.get('error', 'Unknown error')}"
                 logger.error(error_msg)
                 raise Exception(error_msg)

            urls_to_process = retriever_result.get("urls", [])
            # Use the specific key from the updated retriever output
            robots_crawl_delay = retriever_result.get("robots_crawl_delay_found") 
            # Get the actual interval used by retriever for logging/comparison if needed
            retriever_interval_used = retriever_result.get("final_request_interval_used") 
            sitemap_source_url = retriever_result.get("sitemap_source_url", "Unknown") # May not always be present
            total_sitemap_urls_found = retriever_result.get("total_urls_found", len(urls_to_process))
            retriever_method = retriever_result.get("method_used", "unknown")
            
            logger.info(f"SitemapRetrieverTool completed (Method: {retriever_method}). Found {total_sitemap_urls_found} total URLs. Robots delay found: {robots_crawl_delay}s. Actual interval used by retriever: {retriever_interval_used}s.")

            if not urls_to_process:
                logger.warning(f"Sitemap retrieved but no URLs found for {str_url}. Returning empty result.")
                final_result = {
                    "success": True,
                    "message": "Sitemap retrieved successfully, but it contained no URLs.",
                    "sitemap_source_url": sitemap_source_url,
                    "total_sitemap_urls_found": total_sitemap_urls_found,
                    "urls_processed": 0,
                    "results": []
                }
                update_progress(100, 100, "Sitemap retrieved, no URLs found", result=final_result)
                return json.dumps(final_result)

            # Limit the number of URLs to process based on the parameter
            if len(urls_to_process) > max_sitemap_urls_to_process:
                logger.info(f"Sitemap contained {len(urls_to_process)} URLs, processing the first {max_sitemap_urls_to_process}.")
                urls_to_process = urls_to_process[:max_sitemap_urls_to_process]
            
            total_urls_to_fetch = len(urls_to_process)
            logger.info(f"Found {total_urls_to_fetch} URLs in sitemap. Will process up to {total_urls_to_fetch}.")

            # 2. Initialize Rate Limiter for *this tool's* fetches
            # Use the delay found by the retriever and the user RPS setting.
            # RateLimitedFetcher.init_rate_limiting handles selecting the stricter limit.
            logger.info(f"Initializing RateLimitedFetcher for SitemapCrawlerTool on domain '{domain}'. User RPS={requests_per_second}, Robots Delay={robots_crawl_delay}")
            try:
                RateLimitedFetcher.init_rate_limiting(
                    domain=domain, # Use normalized domain
                    rate_limit=requests_per_second,
                    crawl_delay=robots_crawl_delay
                )
            except Exception as e:
                 logger.error(f"Error initializing rate limiter for SitemapCrawlerTool on domain {domain}: {e}", exc_info=True)
                 raise Exception(f"Rate limiter initialization failed for crawler: {e}")

            # 3. Fetch content for each URL respecting the initialized rate limit
            for i, sitemap_url_info in enumerate(urls_to_process):
                url_to_fetch = sitemap_url_info.get('loc') # Adjust if URL structure differs
                if not url_to_fetch:
                    logger.warning(f"Skipping entry {i+1} due to missing 'loc': {sitemap_url_info}")
                    continue

                progress_percent = int(((i + 1) / total_urls_to_fetch) * 100)
                message = f"Fetching content ({i + 1}/{total_urls_to_fetch})"
                update_progress(progress_percent, 100, message, url=url_to_fetch)
                logger.info(message + f": {url_to_fetch}")

                # Use RateLimitedFetcher.fetch_url which respects the initialized limit
                fetch_result = RateLimitedFetcher.fetch_url(url_to_fetch)

                if fetch_result["success"]:
                    # Process content based on output_format
                    content = fetch_result.get('content', '')
                    content_bytes = fetch_result.get('content_bytes')
                    content_type = fetch_result.get("content_type", "")
                    final_url = fetch_result.get("final_url", url_to_fetch)
                    status_code = fetch_result.get("status_code", 200)
                    
                    extracted_data = self._extract_content(
                         html_content=content, 
                         content_type=content_type, 
                         output_format=output_format
                    )
                    
                    processed_content.append({
                        "url": final_url,
                        "requested_url": url_to_fetch,
                        "content": extracted_data,
                        "status_code": status_code,
                        # Add other sitemap info if available and needed
                        "lastmod": sitemap_url_info.get('lastmod'),
                        "changefreq": sitemap_url_info.get('changefreq'),
                        "priority": sitemap_url_info.get('priority')
                    })
                    total_urls_processed += 1
                else:
                    error_detail = f"Failed to fetch {url_to_fetch}: {fetch_result.get('error', 'Unknown error')}"
                    logger.warning(error_detail)
                    errors.append({
                        "url": url_to_fetch,
                        "error": fetch_result.get('error', 'Unknown error'),
                    "status_code": fetch_result.get('status_code')
                })

            # Final Result
            elapsed_time = time.time() - start_time
            success_message = f"Sitemap crawl completed in {elapsed_time:.2f}s. Processed {total_urls_processed}/{total_urls_to_fetch} URLs."
            if errors:
                success_message += f" Encountered {len(errors)} errors."
            logger.info(success_message)

            # Success payload definition (Still INSIDE the try block)
            final_result = {
                            "success": True,
                            "message": success_message,
                            "sitemap_source_url": sitemap_source_url,
                            "total_sitemap_urls_found": total_sitemap_urls_found,
                            "urls_processed": total_urls_processed,
                            "results": processed_content,
                            "errors": errors
                        }
            # Send success update (Still INSIDE the try block)
            update_progress(100, 100, "Sitemap crawl processing complete.", result=final_result)
            # Return success JSON (Still INSIDE the try block)
            return json.dumps(final_result)

        except Exception as e:
            elapsed_time = time.time() - start_time
            error_message = f"Error during sitemap crawl after {elapsed_time:.2f}s: {str(e)}"
            logger.error(error_message, exc_info=True)
            # Error payload definition
            final_result = {
                "success": False,
                "message": error_message,
                "sitemap_source_url": sitemap_source_url, # Include info available before error
                "total_sitemap_urls_found": total_sitemap_urls_found,
                "urls_processed": total_urls_processed,
                "results": processed_content, # Include partial results
                "errors": errors + [{"url": str(url), "error": error_message}] # Add the main error
            }
            # Send error update
            update_progress(100, 100, "Sitemap crawl failed.", result=final_result)
            # Return error JSON
            return json.dumps(final_result)

# --- Celery Task (Updated signature) ---
class SitemapCrawlerAbortableTask(AbortableTask, ProgressTask):
    pass

@shared_task(bind=True, base=SitemapCrawlerAbortableTask, time_limit=1200, soft_time_limit=1140)
def sitemap_crawler_task(self, url: str, user_id: int, max_sitemap_urls_to_process: int = 50,
                         max_sitemap_retriever_pages: int = 1000, requests_per_second: float = 5.0,
                         output_format: str = ContentOutputFormat.TEXT, timeout: int = 15000) -> str:
    start_time = time.time()
    logger.info(f"Starting sitemap_crawler_task (content fetch) for {url}, user_id={user_id}, max_urls={max_sitemap_urls_to_process}")

    try:
        tool = SitemapCrawlerTool()
        # Convert Pydantic AnyHttpUrl back to string for the task if needed, although _run handles it now
        result = tool._run(
            url=AnyHttpUrl(url), # Ensure it's passed as AnyHttpUrl if validator expects it
            user_id=user_id,
            max_sitemap_urls_to_process=max_sitemap_urls_to_process,
            max_sitemap_retriever_pages=max_sitemap_retriever_pages,
            requests_per_second=requests_per_second,
            output_format=output_format,
            timeout=timeout,
            task=self
        )
        elapsed_time = time.time() - start_time
        logger.info(f"Completed sitemap_crawler_task (content fetch) for {url} in {elapsed_time:.2f} seconds")
        return result
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(f"Error in sitemap_crawler_task (content fetch) after {elapsed_time:.2f} seconds: {str(e)}", exc_info=True)
        self.update_state(state='FAILURE', meta={'exc_type': type(e).__name__, 'exc_message': str(e)})
        return json.dumps({"status": "error", "message": str(e)}) 