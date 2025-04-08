"""
Tool for crawling websites using the new scraper architecture.
"""
import logging
import json
import re
from typing import Optional, Dict, Any, Type, List, Union
from urllib.parse import urlparse
from enum import Enum
from pydantic import BaseModel, Field
from apps.agents.tools.base_tool import BaseTool
from django.conf import settings
from apps.agents.utils.scrape_url import crawl_website, is_excluded_url

logger = logging.getLogger(__name__)

class OutputType(str, Enum):
    """Enum for output types."""
    HTML = "html"
    CLEANED_HTML = "cleaned_html"
    MARKDOWN = "markdown"
    TEXT = "text"
    METADATA = "metadata"
    FULL = "full"

class CacheMode(str, Enum):
    """Enum for cache modes."""
    ENABLED = "enabled"
    DISABLED = "disabled"
    READ_ONLY = "read_only"
    WRITE_ONLY = "write_only"
    BYPASS = "bypass"

class CrawlWebsiteToolSchema(BaseModel):
    """Schema for the Crawl Website Tool."""
    website_url: str = Field(
        ...,
        description="URL of the website to crawl"
    )
    max_pages: int = Field(
        100,
        description="Maximum number of pages to crawl (default: 100)"
    )
    max_depth: int = Field(
        3,
        description="Maximum depth to crawl (default: 3)"
    )
    output_type: str = Field(
        "markdown",
        description="Type of output to return (html, cleaned_html, markdown, text, metadata, full)"
    )
    include_patterns: Optional[List[str]] = Field(
        None,
        description="URL patterns to include in crawl (e.g., ['/blog/.*'])"
    )
    exclude_patterns: Optional[List[str]] = Field(
        None,
        description="URL patterns to exclude from crawl (e.g., ['/admin/.*'])"
    )
    wait_for: Optional[str] = Field(
        None,
        description="Wait for element or time in milliseconds"
    )
    css_selector: Optional[str] = Field(
        None,
        description="CSS selector to extract content from"
    )

class CrawlWebsiteTool(BaseTool):
    """Tool for crawling websites."""
    name: str = "Crawl and Read Website Content"
    description: str = """A tool that can crawl websites and extract content in various formats (HTML, cleaned HTML, metadata, or markdown)."""
    args_schema: Type[BaseModel] = CrawlWebsiteToolSchema

    def _run(self, website_url: str, user_id: Optional[int] = None, max_pages: int = 100, max_depth: int = 3,
             wait_for: Optional[str] = None, css_selector: Optional[str] = None,
             include_patterns: Optional[List[str]] = None, exclude_patterns: Optional[List[str]] = None,
             output_type: str = "markdown",
             progress_callback: Optional[callable] = None,
             **kwargs: Any) -> str:
        """Run the website crawling tool."""
        try:
            # Get current task if available (keep for compatibility if needed, but prefer callback)
            current_task = kwargs.get('task', None)

            # Ensure output_type is valid
            try:
                output_type_enum = OutputType(output_type.lower())
            except ValueError:
                output_type_enum = OutputType.MARKDOWN

            # Parse URLs
            parsed_url = urlparse(website_url)
            domain = parsed_url.netloc

            # Check if URL should be excluded
            if is_excluded_url(website_url):
                logger.info(f"URL {website_url} is in the exclusion list, skipping crawl")
                return json.dumps({
                    "status": "error",
                    "message": f"URL {website_url} is in the exclusion list, skipping crawl"
                })

            # Normalize output type
            output_format = output_type_enum.value

            # Map output format to the format expected by crawl_website
            format_mapping = {
                "html": "html",
                "cleaned_html": "html",
                "markdown": "text",
                "text": "text",
                "metadata": "metadata",
                "links": "links",
                "full": "full"
            }

            # Default to text if format not found
            crawl_format = format_mapping.get(output_format, "text")

            # Update progress if task exists or callback is provided
            if progress_callback:
                progress_callback(0, 100, "Starting crawl")
            elif current_task:
                # Fallback to old method if no callback provided
                try:
                    current_task.update_progress(0, 100, "Starting crawl")
                except AttributeError:
                    logger.warning("Task object does not have update_progress, cannot report initial progress.")

            # Log the request for debugging
            logger.info(f"Crawl request for URL: {website_url}, max_pages: {max_pages}, max_depth: {max_depth}, format: {crawl_format}")

            # Convert wait_for to milliseconds if it's a number
            wait_for_ms = None
            if wait_for:
                if wait_for.isdigit():
                    wait_for_ms = int(wait_for)
                else:
                    # For non-numeric wait_for, we'll pass it as is and let the adapter handle it
                    wait_for_ms = wait_for

            # Process include/exclude patterns
            # Convert comma-separated strings to lists if needed
            processed_include_patterns = include_patterns
            processed_exclude_patterns = exclude_patterns

            if include_patterns and isinstance(include_patterns, str):
                processed_include_patterns = [pattern.strip() for pattern in include_patterns.split(',')]
                logger.info(f"Converted include_patterns string to list: {processed_include_patterns}")

            if exclude_patterns and isinstance(exclude_patterns, str):
                processed_exclude_patterns = [pattern.strip() for pattern in exclude_patterns.split(',')]
                logger.info(f"Converted exclude_patterns string to list: {processed_exclude_patterns}")

            # Convert glob patterns to regex patterns if needed
            def convert_glob_patterns(patterns):
                if not patterns:
                    return patterns

                converted_patterns = []
                for pattern in patterns:
                    # Check if it's a glob pattern (contains *)
                    if '*' in pattern:
                        # Log the original pattern
                        logger.info(f"Converting glob pattern: {pattern}")
                        # Ensure the pattern will match anywhere in the URL
                        if not pattern.startswith('/'):
                            pattern = f"/{pattern}"
                    converted_patterns.append(pattern)
                return converted_patterns

            # Convert glob patterns to more flexible patterns
            if processed_include_patterns:
                processed_include_patterns = convert_glob_patterns(processed_include_patterns)
                logger.info(f"Processed include patterns: {processed_include_patterns}")

            if processed_exclude_patterns:
                processed_exclude_patterns = convert_glob_patterns(processed_exclude_patterns)
                logger.info(f"Processed exclude patterns: {processed_exclude_patterns}")

            # Use the crawl_website function from our new architecture
            result = crawl_website(
                url=website_url,
                output_type=crawl_format,
                max_pages=max_pages,
                max_depth=max_depth,
                include_patterns=processed_include_patterns,
                exclude_patterns=processed_exclude_patterns,
                stay_within_domain=True,
                cache=True,
                stealth=True,
                timeout=60000,  # 60 seconds
                wait_for=wait_for_ms,
                css_selector=css_selector,
                device="desktop"
            )

            # Check if crawl was successful
            if result is None:
                return json.dumps({
                    "status": "error",
                    "message": "Failed to crawl website"
                })

            # Update progress to 100%
            if progress_callback:
                progress_callback(100, 100, "Crawl completed")
            elif current_task:
                try:
                    current_task.update_progress(100, 100, "Crawl completed")
                except AttributeError:
                    logger.warning("Task object does not have update_progress, cannot report final progress.")

            # Process the result based on the requested output format
            if output_format == "html":
                # Return HTML content
                pages_html = []
                for page in result.get('pages', []):
                    if page.get('content'):
                        pages_html.append({
                            'url': page.get('url'),
                            'title': page.get('title', ''),
                            'content': page.get('content')
                        })

                return json.dumps({
                    "status": "success",
                    "pages": pages_html,
                    "total_pages": len(pages_html)
                })

            elif output_format == "cleaned_html":
                # Return cleaned HTML content (same as HTML for now)
                pages_html = []
                for page in result.get('pages', []):
                    if page.get('content'):
                        pages_html.append({
                            'url': page.get('url'),
                            'title': page.get('title', ''),
                            'content': page.get('content')
                        })

                return json.dumps({
                    "status": "success",
                    "pages": pages_html,
                    "total_pages": len(pages_html)
                })

            elif output_format == "markdown" or output_format == "text":
                # Return text content
                pages_text = []
                for page in result.get('pages', []):
                    if page.get('textContent'):
                        pages_text.append({
                            'url': page.get('url'),
                            'title': page.get('title', ''),
                            'content': page.get('textContent')
                        })

                return json.dumps({
                    "status": "success",
                    "pages": pages_text,
                    "total_pages": len(pages_text)
                })

            elif output_format == "metadata":
                # Return metadata
                pages_metadata = []
                for page in result.get('pages', []):
                    if page.get('metadata'):
                        pages_metadata.append({
                            'url': page.get('url'),
                            'title': page.get('title', ''),
                            'metadata': page.get('metadata'),
                            'links': page.get('links', [])
                        })

                return json.dumps({
                    "status": "success",
                    "pages": pages_metadata,
                    "total_pages": len(pages_metadata)
                })

            elif output_format == "full":
                # Return all content
                return json.dumps({
                    "status": "success",
                    "result": result,
                    "total_pages": len(result.get('pages', []))
                })

            else:
                # Default to text
                pages_text = []
                for page in result.get('pages', []):
                    if page.get('textContent'):
                        pages_text.append({
                            'url': page.get('url'),
                            'title': page.get('title', ''),
                            'content': page.get('textContent')
                        })

                return json.dumps({
                    "status": "success",
                    "pages": pages_text,
                    "total_pages": len(pages_text)
                })

        except Exception as e:
            logger.error(f"Error crawling website: {str(e)}")
            return json.dumps({
                "status": "error",
                "message": f"Error crawling website: {str(e)}"
            })
