import logging
import json
from typing import Optional, List, Type, Dict, Any, Union
from enum import Enum
from pydantic import BaseModel, Field, field_validator
from apps.agents.tools.base_tool import BaseTool
from django.conf import settings
from urllib.parse import urlparse
import time
from celery import shared_task
from apps.agents.tasks.base import ProgressTask
from celery.contrib.abortable import AbortableTask
import inspect # Keep inspect for task deserialization if needed

# Import the crawl_url functionality
from apps.agents.utils.crawl_url import crawl_url, check_crawl_status

logger = logging.getLogger(__name__)

class FireCrawlOutputFormat(str, Enum):
    MARKDOWN = "markdown"
    HTML = "html"
    BOTH = "both"

class FireCrawlToolSchema(BaseModel):
    """Input schema for FireCrawlTool."""
    url: str = Field(..., description="URL to start crawling from")
    limit: int = Field(default=100, description="Maximum number of pages to crawl")
    max_depth: int = Field(default=10, description="Maximum depth for crawling relative to base URL")
    max_discovery_depth: Optional[int] = Field(
        default=None, 
        description="Maximum depth to crawl based on discovery order. Root site and sitemapped pages have depth 0."
    )
    output_format: str = Field(
        default=FireCrawlOutputFormat.MARKDOWN, 
        description="Format of the output content (markdown, html, both)"
    )
    include_paths: Optional[List[str]] = Field(
        default=None,
        description="URL pathname regex patterns to include in crawl"
    )
    exclude_paths: Optional[List[str]] = Field(
        default=None,
        description="URL pathname regex patterns to exclude from crawl"
    )
    ignore_sitemap: bool = Field(
        default=False,
        description="Ignore the website sitemap when crawling"
    )
    ignore_query_parameters: bool = Field(
        default=False,
        description="Do not re-scrape the same path with different query parameters"
    )
    allow_backward_links: bool = Field(
        default=False,
        description="Enable crawler to navigate from a specific URL to previously linked pages"
    )
    allow_external_links: bool = Field(
        default=False,
        description="Allow crawler to follow links to external websites"
    )
    wait_for_completion: bool = Field(
        default=True,
        description="Wait for crawl to complete before returning results"
    )
    timeout: int = Field(
        default=3600,
        description="Maximum seconds to wait for crawl completion"
    )
    poll_interval: int = Field(
        default=30,
        description="Seconds between status checks when waiting for completion"
    )
    # Additional scrape options for each page
    only_main_content: bool = Field(
        default=True,
        description="Only extract the main content of each page, ignoring headers, footers, etc."
    )
    timeout_ms: int = Field(
        default=30000,
        description="Timeout in milliseconds for each page request"
    )
    remove_base64_images: bool = Field(
        default=True,
        description="Remove base64-encoded images from HTML content"
    )
    block_ads: bool = Field(
        default=True,
        description="Block ads and trackers when scraping pages"
    )
    
    @field_validator('url')
    def validate_url(cls, v):
        """Validate URL format."""
        if not v.startswith(('http://', 'https://')):
            raise ValueError("URL must start with http:// or https://")
        return v
        
    @field_validator('output_format')
    def normalize_output_format(cls, v):
        """Handle any format of output format specification."""
        try:
            logger.debug(f"Normalizing output_format: {repr(v)}")
            
            # Convert any input to a string first for consistency
            input_str = str(v)
            
            # Remove all quotes (both single and double)
            cleaned = input_str.replace('"', '').replace("'", '')
            cleaned = cleaned.lower().strip()
            
            # Check for valid values
            if cleaned == "both" or cleaned == "markdown,html" or cleaned == "html,markdown":
                return FireCrawlOutputFormat.BOTH
            elif cleaned == "markdown":
                return FireCrawlOutputFormat.MARKDOWN
            elif cleaned == "html":
                return FireCrawlOutputFormat.HTML
            else:
                logger.warning(f"Invalid output format: {cleaned}, defaulting to MARKDOWN")
                return FireCrawlOutputFormat.MARKDOWN
            
        except Exception as e:
            logger.error(f"Error normalizing output_format {repr(v)}: {str(e)}")
            # Default to MARKDOWN if there's an error
            logger.warning(f"Defaulting to MARKDOWN output_format due to validation error")
            return FireCrawlOutputFormat.MARKDOWN

class FireCrawlAbortableTask(AbortableTask, ProgressTask):
    """Abortable task that supports progress reporting"""
    pass

class FireCrawlTool(BaseTool):
    """
    A tool that crawls websites using FireCrawl's API starting from a URL,
    following links up to a specified depth, and extracting content in markdown and/or HTML format.
    Can be configured to include/exclude URL patterns and other crawl settings.
    """
    name: str = "FireCrawl Tool"
    description: str = """
    A tool that crawls websites using FireCrawl's powerful crawling capabilities.
    It starts from a URL, recursively follows links based on your configuration,
    and extracts content in markdown and/or HTML format.
    
    You can configure:
    - Maximum pages to crawl
    - Maximum crawl depth
    - URL patterns to include or exclude
    - Whether to stay within domain or follow external links
    - Whether to use the sitemap or ignore it
    - And more advanced options
    
    This tool is especially useful for comprehensive data collection from websites.
    """
    args_schema: Type[BaseModel] = FireCrawlToolSchema
    
    def _run(self, url: str, limit: int = 100, max_depth: int = 10,
             max_discovery_depth: Optional[int] = None, output_format: str = "markdown",
             include_paths: Optional[List[str]] = None, exclude_paths: Optional[List[str]] = None,
             ignore_sitemap: bool = False, ignore_query_parameters: bool = False,
             allow_backward_links: bool = False, allow_external_links: bool = False,
             wait_for_completion: bool = True, timeout: int = 3600, poll_interval: int = 30,
             only_main_content: bool = True, timeout_ms: int = 30000,
             remove_base64_images: bool = True, block_ads: bool = True,
             **kwargs) -> str:
        """
        Run the FireCrawl crawling tool.
        
        Args:
            url: URL to start crawling from
            limit: Maximum number of pages to crawl
            max_depth: Maximum depth for crawling
            max_discovery_depth: Maximum depth based on discovery order
            output_format: Format of output content (markdown, html, both)
            include_paths: URL pathname regex patterns to include
            exclude_paths: URL pathname regex patterns to exclude
            ignore_sitemap: Whether to ignore the sitemap
            ignore_query_parameters: Whether to ignore query parameters
            allow_backward_links: Whether to allow backward links
            allow_external_links: Whether to allow external links
            wait_for_completion: Wait for crawl to complete before returning
            timeout: Maximum seconds to wait for crawl completion
            poll_interval: Seconds between status checks
            only_main_content: Only extract the main content of each page
            timeout_ms: Timeout in milliseconds for each page request
            remove_base64_images: Remove base64-encoded images from HTML content
            block_ads: Block ads and trackers when scraping pages
            
        Returns:
            JSON string with crawling results
        """
        try:
            # Debug logging for parameters
            logger.debug(f"FireCrawlTool._run called with: url={url}, limit={limit}, max_depth={max_depth}, output_format={repr(output_format)}")
            logger.debug(f"Scrape options args: only_main_content={only_main_content}, timeout_ms={timeout_ms}, remove_base64_images={remove_base64_images}, block_ads={block_ads}")
            
            # Get current task if available
            current_task = kwargs.get('task', None)
            
            # Prepare scrape options based on output format
            include_html = False
            include_markdown = False
            
            # Ensure output_format is validated enum value or string
            try:
                # Validate directly from the input string
                validated_output_format = FireCrawlToolSchema(url="http://example.com", output_format=output_format).output_format
                logger.debug(f"Validated output_format using schema: {validated_output_format}")
            except Exception as e:
                logger.warning(f"Could not validate output_format '{output_format}' via schema: {e}. Using raw value.")
                # Attempt manual normalization as fallback
                cleaned = str(output_format).replace('"', '').replace("'", '').lower().strip()
                if cleaned == "both" or cleaned == "markdown,html" or cleaned == "html,markdown":
                     validated_output_format = FireCrawlOutputFormat.BOTH
                elif cleaned == "html":
                    validated_output_format = FireCrawlOutputFormat.HTML
                else:
                    # Default to markdown if any issue
                    if cleaned != "markdown":
                        logger.warning(f"Defaulting to MARKDOWN for output_format: {output_format}")
                    validated_output_format = FireCrawlOutputFormat.MARKDOWN
            
            if validated_output_format == FireCrawlOutputFormat.MARKDOWN:
                include_markdown = True
            elif validated_output_format == FireCrawlOutputFormat.HTML:
                include_html = True
            elif validated_output_format == FireCrawlOutputFormat.BOTH:
                include_html = True
                include_markdown = True
            
            # Prepare scrape options dictionary
            scrape_options = {
                "formats": []
            }
            
            if include_markdown:
                scrape_options["formats"].append("markdown")
                logger.debug("Added 'markdown' to scrape formats.")
            if include_html:
                scrape_options["formats"].append("html")
                logger.debug("Added 'html' to scrape formats.")
                
            # Ensure formats list is not empty; default to markdown if it is
            if not scrape_options["formats"]:
                 logger.warning("Formats list was empty, defaulting to include markdown.")
                 scrape_options["formats"].append("markdown")
                 include_markdown = True
            
            scrape_options["onlyMainContent"] = only_main_content
            scrape_options["timeout"] = timeout_ms
            scrape_options["removeBase64Images"] = remove_base64_images
            scrape_options["blockAds"] = block_ads
            
            logger.debug(f"Final scrape_options passed to crawl_url: {json.dumps(scrape_options)}")
            
            # Update progress if task is provided
            if current_task:
                current_task.update_progress(0, 100, "Starting crawl", url=url)
            
            # Call the crawl_url function
            result_dict = crawl_url(
                url=url,
                limit=limit,
                exclude_paths=exclude_paths,
                include_paths=include_paths,
                max_depth=max_depth,
                max_discovery_depth=max_discovery_depth,
                ignore_sitemap=ignore_sitemap,
                ignore_query_parameters=ignore_query_parameters,
                allow_backward_links=allow_backward_links,
                allow_external_links=allow_external_links,
                scrape_options=scrape_options,
                include_html=include_html,
                include_markdown=include_markdown,
                poll_interval=poll_interval,
                wait_for_completion=wait_for_completion,
                timeout=timeout
            )
            
            # Log the result structure
            if result_dict:
                logger.debug(f"Result keys from crawl_url: {list(result_dict.keys() if isinstance(result_dict, dict) else [])}")
                if isinstance(result_dict, dict) and 'pages' in result_dict:
                    logger.debug(f"Total pages in result: {len(result_dict['pages'])}")
                    if result_dict['pages']:
                        first_page = result_dict['pages'][0]
                        logger.debug(f"First page keys: {list(first_page.keys())}")
                        logger.debug(f"First page content length: {len(first_page.get('content', ''))}, textContent length: {len(first_page.get('textContent', ''))}")
            
            # Update task progress
            if current_task and result_dict and wait_for_completion:
                current_task.update_progress(
                    100, 100, 
                    "Crawl completed successfully", 
                    url=url, 
                    total_pages=result_dict.get("total_pages", 0)
                )
            
            # Convert result to JSON string
            if result_dict:
                if isinstance(result_dict, dict) and result_dict.get("success") and "pages" in result_dict and result_dict["pages"]:
                    if not result_dict["pages"][0].get("content") and not result_dict["pages"][0].get("textContent"):
                        logger.warning("Result has pages but the first page has empty content/textContent.")
                        
                return json.dumps(result_dict, indent=2)
            else:
                return json.dumps({"status": "error", "message": "Crawl failed or returned no results"})
                
        except Exception as e:
            logger.error(f"Error in FireCrawlTool: {str(e)}", exc_info=True)
            if current_task:
                current_task.update_progress(100, 100, f"Error: {str(e)}", url=url, error=str(e))
            return json.dumps({"status": "error", "message": str(e)})

# Add model_config for pydantic v2 compatibility
model_config = {
    "arbitrary_types_allowed": True,
    "extra": "forbid"
} 