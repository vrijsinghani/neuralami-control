import logging
import aiohttp
import asyncio
from typing import Optional, Dict, Any, Type, List, Literal
from enum import Enum
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
from celery import shared_task
from celery.contrib.abortable import AbortableTask
from django.contrib.auth.models import User
from django.conf import settings
from apps.crawl_website.models import CrawlResult
from .utils import create_crawl_result
import requests
import time
import json
import os
from datetime import datetime
import base64
from urllib.parse import urlparse

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

class CrawlWebsiteToolSchema(BaseModel):
    """Input for CrawlWebsiteTool."""
    website_url: str = Field(..., description="Mandatory website URL to crawl and read content")
    user_id: int = Field(..., description="ID of the user initiating the crawl")
    max_pages: int = Field(default=100, description="Maximum number of pages to crawl")
    css_selector: Optional[str] = Field(default=None, description="CSS selector for content extraction")
    wait_for: Optional[str] = Field(default=None, description="Wait for element/condition before extraction")
    result_attributes: Optional[List[CrawlResultAttribute]] = Field(
        default=["url", "markdown", "success", "metadata", "error_message", "session_id", "status_code"],
        description="List of CrawlResult attributes to return in the results. Available attributes: url, html, success, cleaned_html, media, links, downloaded_files, screenshot, markdown, markdown_v2, fit_markdown, fit_html, extracted_content, metadata, error_message, session_id, response_headers, status_code"
    )
    save_files: bool = Field(default=False, description="Whether to save crawl results to files")

    model_config = {
        "extra": "forbid"
    }

def get_safe_filename(url: str, max_length: int = 50) -> str:
    """Create a safe filename from URL."""
    return "".join(c if c.isalnum() else "_" for c in url)[-max_length:]

def create_output_directory(website_url: str, user_id: int) -> tuple[str, str]:
    """Create output directory for crawl results."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    domain = urlparse(website_url).netloc
    
    # Create user-specific base directory
    user_base_dir = os.path.join(settings.MEDIA_ROOT, str(user_id), 'crawl_results')
    output_dir = os.path.join(user_base_dir, f"{domain}_{timestamp}")
    
    # Create directory and any necessary parent directories
    os.makedirs(output_dir, exist_ok=True)
    logger.info(f"Created output directory: {output_dir}")
    
    return output_dir, timestamp

def save_crawl_files(output_dir: str, website_url: str, crawl_results: list, timestamp: str) -> dict:
    """Save crawl results to files."""
    logger.info(f"Saving crawl files to {output_dir}")
    file_paths = {}

    # Save sitemap
    sitemap_file = os.path.join(output_dir, f"sitemap_{timestamp}.txt")
    with open(sitemap_file, 'w', encoding='utf-8') as f:
        f.write(f"Sitemap for {website_url}\n")
        f.write(f"Generated on: {datetime.now().isoformat()}\n\n")
        
        # Write successful URLs and their titles
        f.write("Successfully crawled pages:\n")
        successful_results = [r for r in crawl_results if r.get('success')]
        for result in successful_results:
            title = result.get('metadata', {}).get('title', 'Unknown Title')
            f.write(f"- {result['url']}\n    Title: {title}\n")
        
        # Write failed URLs
        failed_results = [r for r in crawl_results if not r.get('success')]
        if failed_results:
            f.write("\nFailed pages:\n")
            for result in failed_results:
                f.write(f"- {result['url']}\n    Error: {result.get('error_message', 'Unknown error')}\n")
    
    file_paths['sitemap'] = sitemap_file

    # Create directories for different content types
    screenshots_dir = os.path.join(output_dir, 'screenshots')
    html_dir = os.path.join(output_dir, 'html')
    markdown_dir = os.path.join(output_dir, 'markdown')
    
    os.makedirs(screenshots_dir, exist_ok=True)
    os.makedirs(html_dir, exist_ok=True)
    os.makedirs(markdown_dir, exist_ok=True)

    # Save content for each successful result
    for result in successful_results:
        safe_name = get_safe_filename(result['url'])
        
        # Save screenshot if available
        if result.get('screenshot'):
            screenshot_file = os.path.join(screenshots_dir, f"{safe_name}.png")
            try:
                screenshot_data = base64.b64decode(result['screenshot'])
                with open(screenshot_file, 'wb') as f:
                    f.write(screenshot_data)
            except Exception as e:
                logger.error(f"Failed to save screenshot for {result['url']}: {e}")

        # Save cleaned HTML if available
        if result.get('cleaned_html'):
            html_file = os.path.join(html_dir, f"{safe_name}.html")
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(result['cleaned_html'])

        # Save markdown if available
        if result.get('markdown'):
            markdown_file = os.path.join(markdown_dir, f"{safe_name}.md")
            with open(markdown_file, 'w', encoding='utf-8') as f:
                f.write(result['markdown'])

    file_paths.update({
        'screenshots_dir': screenshots_dir,
        'html_dir': html_dir,
        'markdown_dir': markdown_dir
    })
    
    return file_paths

def crawl_website(website_url: str, user_id: int, max_pages: int = 100,
                  wait_for: Optional[str] = None, css_selector: Optional[str] = None,
                  result_attributes: Optional[List[str]] = None, save_files: bool = False) -> str:
    """Function to crawl website using Crawl4AI service."""
    logger.info(f"Starting crawl for URL: {website_url} with attributes: {result_attributes}")

    # Use default attributes if none provided
    if result_attributes is None:
        result_attributes = ["url", "markdown", "success", "metadata", "error_message", "session_id", "status_code"]

    # Validate user_id and get user
    if not user_id:
        raise ValueError("user_id is required")
    
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error(f"User with id {user_id} not found")
        raise ValueError(f"User with id {user_id} not found")

    # Prepare request data
    request_data = {
        "url": website_url,
        "max_pages": max_pages,
        "max_depth": 3,
        "batch_size": 10,
        "crawler_params": {
            **settings.CRAWL4AI_CRAWLER_PARAMS,
            "wait_for": wait_for,
            "remove_overlay_elements": True,
            "delay_before_return_html": 2.0,
        },
        "extraction_config": {
            "type": "basic",
            "params": {
                "word_count_threshold": settings.CRAWL4AI_EXTRA_PARAMS.get("word_count_threshold", 10),
                "only_text": settings.CRAWL4AI_EXTRA_PARAMS.get("only_text", True),
                "bypass_cache": settings.CRAWL4AI_EXTRA_PARAMS.get("bypass_cache", False),
                "process_iframes": settings.CRAWL4AI_EXTRA_PARAMS.get("process_iframes", True),
                "excluded_tags": settings.CRAWL4AI_EXTRA_PARAMS.get("excluded_tags", ['nav', 'aside', 'footer']),
                "html2text": {
                    "ignore_links": False,
                    "ignore_images": True,
                    "body_width": 0,
                    "unicode_snob": True,
                    "protect_links": True
                }
            }
        }
    }

    # Add css_selector if provided
    if css_selector:
        request_data["crawler_params"]["css_selector"] = css_selector
        logger.debug(f"Added CSS selector: {css_selector}")

    headers = {"Authorization": f"Bearer {settings.CRAWL4AI_API_KEY}"} if settings.CRAWL4AI_API_KEY else {}
    
    try:
        # Start crawl
        response = requests.post(
            f"{settings.CRAWL4AI_URL}/spider",
            headers=headers,
            json=request_data,
            stream=True  # Enable streaming for ndjson response
        )
        logger.debug(f"Initial response status: {response.status_code}")
        
        if not response.ok:
            error_msg = f"Failed to start crawl: {response.text}"
            logger.error(error_msg)
            raise Exception(error_msg)
        
        # Process the streaming response
        all_content = ""
        all_links = []
        crawl_results = []
        
        for line in response.iter_lines():
            if line:
                try:
                    result_data = json.loads(line)
                    
                    # Handle results data structure
                    if "results" in result_data:
                        for url, page_result in result_data["results"].items():
                            #logger.debug(f"URL: {url}")
                            # Extract only requested attributes
                            filtered_result = {
                                attr: page_result.get(attr)
                                for attr in result_attributes
                                if attr in page_result
                            }
                            filtered_result["success"] = True  # Mark as successful since it's in results
                            crawl_results.append(filtered_result)
                            
                            # Collect content and links
                            content = page_result.get("markdown", "")
                            if content:
                                all_content += f"\n---\nURL: {url}\n{content}"
                            
                            links = page_result.get("links", {}).get("internal", [])
                            if links:
                                all_links.extend(links)
                    
                    # Handle failed URLs
                    elif "failed_urls" in result_data:
                        for url, error in result_data["failed_urls"].items():
                            logger.warning(f"Failed URL {url}: {error}")
                            failed_result = {
                                "url": url,
                                "success": False,
                                "error_message": error,
                                "status_code": None
                            }
                            filtered_failed_result = {
                                attr: failed_result.get(attr)
                                for attr in result_attributes
                                if attr in failed_result
                            }
                            crawl_results.append(filtered_failed_result)
                    
                    # Log crawl progress
                    if result_data.get("crawled_count"):
                        logger.info(f"Crawl progress: {result_data['crawled_count']} pages crawled")

                except json.JSONDecodeError as e:
                    logger.error(f"Failed to decode JSON from line: {line}, Error: {e}")
                except Exception as e:
                    logger.error(f"Error processing line: {line}, Error: {e}")

        logger.info(f"Finished processing stream. Total results: {len(crawl_results)}")
        
        # Structure the links in a dictionary format
        links_data = {
            "internal": all_links,
            "total": len(all_links)
        }
        
        # Create CrawlResult using the create_with_content class method
        crawl_result = CrawlResult.create_with_content(
            user=user,
            website_url=website_url,
            content=all_content,
            links_visited=links_data,
            total_links=len(all_links)
        )
        
        result = {
            "status": "success",
            "website_url": crawl_result.website_url,
            "crawl_results": crawl_results,
            "total_pages": len(crawl_results),
            "links_visited": crawl_result.links_visited.get('internal', []),
            "total_links": crawl_result.total_links,
            "file_url": crawl_result.get_file_url(),
            "crawl_result_id": crawl_result.id
        }
        logger.info(f"Returning final result with {len(crawl_results)} pages crawled")

        if save_files:
            output_dir, timestamp = create_output_directory(website_url, user_id)
            file_paths = save_crawl_files(output_dir, website_url, crawl_results, timestamp)
            # Add relative media URL paths for frontend access
            media_paths = {
                key: os.path.relpath(path, settings.MEDIA_ROOT)
                for key, path in file_paths.items()
            }
            result['saved_files'] = {
                'absolute_paths': file_paths,
                'media_urls': media_paths
            }

        return json.dumps(result)

    except Exception as e:
        logger.error(f"Error during crawl: {e}", exc_info=True)
        return json.dumps({
            "status": "error",
            "message": str(e)
        })

class CrawlWebsiteTool(BaseTool):
    name: str = "Crawl and Read Website Content"
    description: str = """A tool that can crawl a website and read its content, including content from internal links on the same page.
    
    Example usage:
    1. Basic crawl with default attributes:
       {
           "website_url": "https://example.com",
           "user_id": 1
       }
    
    2. Crawl with custom attributes and limits:
       {
           "website_url": "https://example.com",
           "user_id": 1,
           "max_pages": 50,
           "result_attributes": ["url", "html", "links", "markdown"]
       }
    
    3. Crawl with CSS selector and wait condition:
       {
           "website_url": "https://example.com",
           "user_id": 1,
           "css_selector": "article.content",
           "wait_for": "#main-content",
           "result_attributes": ["url", "markdown", "metadata", "status_code"]
       }
    
    Available result_attributes:
    - url: The page URL
    - html: Raw HTML content
    - success: Whether the crawl was successful
    - cleaned_html: Processed HTML content
    - media: Media elements found
    - links: Internal and external links
    - downloaded_files: Any downloaded files
    - screenshot: Page screenshot
    - markdown: Content in markdown format
    - markdown_v2: Alternative markdown format
    - fit_markdown: Fitted markdown content
    - fit_html: Fitted HTML content
    - extracted_content: Extracted text content
    - metadata: Page metadata
    - error_message: Any error messages
    - session_id: Crawl session ID
    - response_headers: HTTP response headers
    - status_code: HTTP status code
    """
    args_schema: Type[BaseModel] = CrawlWebsiteToolSchema
    
    def _run(
        self,
        website_url: str,
        user_id: int,
        max_pages: int = 100,
        css_selector: Optional[str] = None,
        wait_for: Optional[str] = None,
        result_attributes: Optional[List[str]] = None,
        save_files: bool = False,
        **kwargs: Any
    ) -> str:
        """Run the tool and return crawl results as a JSON string."""
        return crawl_website(
            website_url=website_url,
            user_id=user_id,
            max_pages=max_pages,
            wait_for=wait_for,
            css_selector=css_selector,
            result_attributes=result_attributes,
            save_files=save_files
        )

@shared_task(bind=True, base=AbortableTask)
def crawl_website_task(self, website_url: str, user_id: int, max_pages: int = 100, save_file: bool = True,
                      wait_for: Optional[str] = None, css_selector: Optional[str] = None) -> str:
    """Celery task to crawl website using Crawl4AI service."""
    try:
        result = crawl_website(
            website_url=website_url,
            user_id=user_id,
            max_pages=max_pages,
            wait_for=wait_for,
            css_selector=css_selector
        )
        # Return the JSON string directly
        return result
    except Exception as e:
        logger.error(f"Error in crawl_website_task: {e}")
        return json.dumps({
            "status": "error",
            "message": str(e)
        })
