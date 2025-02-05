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
from .utils import sanitize_url
import requests
import time
import json
import os
from datetime import datetime
import base64
from urllib.parse import urlparse
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import re

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
    """
    Create a safe filename from URL.
    
    Args:
        url: The URL to convert to a filename
        max_length: Maximum length of the filename
        
    Returns:
        str: A safe filename
    """
    return "".join(c if c.isalnum() else "_" for c in url)[-max_length:]

def create_output_directory(website_url: str, user_id: int) -> tuple[str, str]:
    """Create output directory structure for crawl results in cloud storage."""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        domain = re.sub(r'[^\w\-]', '_', urlparse(website_url).netloc)
        
        # Create base path - using consistent naming
        base_path = os.path.join(
            str(user_id),
            'crawled_websites',  # Lowercase, consistent with model
            f"{domain}_{timestamp}"
        )
        
        # Create subdirectories
        subdirs = ['screenshots', 'html', 'markdown']
        for subdir in subdirs:
            dir_path = os.path.join(base_path, subdir)
            # Create a marker file to ensure directory exists
            marker_path = os.path.join(dir_path, '.keep')
            default_storage.save(marker_path, ContentFile(''))
        
        logger.info(f"Created output directory structure at: {base_path}")
        return base_path, timestamp
        
    except Exception as e:
        error_msg = f"Error creating output directory structure: {str(e)}"
        logger.error(error_msg)
        raise

def get_storage_url(relative_path: str) -> str:
    """
    Get the URL for accessing a file in storage.
    
    Args:
        relative_path: The relative path to the file
        
    Returns:
        str: The URL to access the file
    """
    try:
        return default_storage.url(relative_path)
    except Exception as e:
        logger.error(f"Error getting storage URL: {str(e)}")
        return None

def ensure_directory_exists(relative_path: str) -> bool:
    """
    Ensure a directory exists in cloud storage.
    
    Args:
        relative_path: The relative path to ensure exists
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        marker_path = os.path.join(relative_path, '.keep')
        if not default_storage.exists(marker_path):
            default_storage.save(marker_path, ContentFile(''))
        return True
    except Exception as e:
        logger.error(f"Error ensuring directory exists: {str(e)}")
        return False

def save_crawl_files(output_dir: str, website_url: str, crawl_results: list, timestamp: str) -> dict:
    """Save crawl results to files."""
    try:
        logger.debug(f"Starting save_crawl_files for dir: {output_dir}")
        file_paths = {}

        # Save sitemap
        sitemap_path = os.path.join(output_dir, f"sitemap_{timestamp}.txt")
        logger.debug(f"Saving sitemap to: {sitemap_path}")
        sitemap_content = []
        sitemap_content.append(f"Sitemap for {website_url}")
        sitemap_content.append(f"Generated on: {datetime.now().isoformat()}\n")
        
        # Write successful URLs and their titles
        sitemap_content.append("Successfully crawled pages:")
        successful_results = [r for r in crawl_results if r.get('success')]
        for result in successful_results:
            title = result.get('metadata', {}).get('title', 'Unknown Title')
            sitemap_content.append(f"- {result['url']}\n    Title: {title}")
        
        # Write failed URLs
        failed_results = [r for r in crawl_results if not r.get('success')]
        if failed_results:
            sitemap_content.append("\nFailed pages:")
            for result in failed_results:
                sitemap_content.append(f"- {result['url']}\n    Error: {result.get('error_message', 'Unknown error')}")

        # Join content and log length
        content = '\n'.join(sitemap_content)
        logger.debug(f"Sitemap content length: {len(content)}")
        
        # Save the content
        default_storage.save(sitemap_path, ContentFile(content))
        logger.debug(f"Saved sitemap file")
        
        # Save individual files
        for result in successful_results:
            safe_name = get_safe_filename(result['url'])
            logger.debug(f"Processing files for URL: {safe_name}")
            
            if result.get('screenshot'):
                screenshot_path = os.path.join(output_dir, 'screenshots', f"{safe_name}.png")
                logger.debug(f"Saving screenshot to: {screenshot_path}")
                screenshot_data = base64.b64decode(result['screenshot'])
                default_storage.save(screenshot_path, ContentFile(screenshot_data))
                
            if result.get('cleaned_html'):
                html_path = os.path.join(output_dir, 'html', f"{safe_name}.html")
                logger.debug(f"Saving HTML to: {html_path}")
                default_storage.save(html_path, ContentFile(result['cleaned_html']))
                
            if result.get('markdown'):
                markdown_path = os.path.join(output_dir, 'markdown', f"{safe_name}.md")
                logger.debug(f"Saving markdown to: {markdown_path}")
                default_storage.save(markdown_path, ContentFile(result['markdown']))
                
        logger.debug("Completed save_crawl_files")
        return file_paths
    except Exception as e:
        logger.error(f"Error in save_crawl_files: {str(e)}", exc_info=True)
        raise


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
        return crawl_website_task(
            website_url=website_url,
            user_id=user_id,
            max_pages=max_pages,
            wait_for=wait_for,
            css_selector=css_selector,
            result_attributes=result_attributes,
            save_files=save_files
        )

@shared_task(bind=True, base=AbortableTask)
def crawl_website_task(self, website_url: str, user_id: int, max_pages: int = 100, 
                      save_files: bool = True, wait_for: Optional[str] = None, 
                      css_selector: Optional[str] = None, 
                      result_attributes: Optional[List[str]] = None) -> str:
    """Celery task to crawl website using Crawl4AI service."""
    try:
        logger.info(f"Starting crawl for URL: {website_url}")
        
        # Use default result attributes if none provided
        if result_attributes is None:
            result_attributes = ["url", "markdown", "success", "metadata", 
                               "error_message", "session_id", "status_code"]
        
        # Initialize progress - with safe state update
        try:
            if hasattr(self.request, 'id') and self.request.id:
                self.update_state(state='PROGRESS', meta={
                    'current': 0,
                    'total': max_pages,
                    'status_message': 'Starting crawl...'
                })
        except Exception as e:
            logger.warning(f"Could not update task state: {e}")

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

        headers = {"Authorization": f"Bearer {settings.CRAWL4AI_API_KEY}"} if settings.CRAWL4AI_API_KEY else {}
        
        # Make the request and process the stream directly in the task
        response = requests.post(
            f"{settings.CRAWL4AI_URL}/spider",
            headers=headers,
            json=request_data,
            stream=True
        )
        
        if not response.ok:
            raise Exception(f"Failed to start crawl: {response.text}")
        
        logger.debug(f"Initial response status: {response.status_code}")
        
        # Process the streaming response
        all_content = []  # Change to list to collect content
        all_links = set()
        crawl_results = []
        pages_crawled = 0
        
        for line in response.iter_lines():
            if line:
                try:
                    result_data = json.loads(line)
                    
                    # Safe progress update when we receive any data
                    try:
                        if hasattr(self.request, 'id') and self.request.id:
                            self.update_state(state='PROGRESS', meta={
                                'current': pages_crawled,
                                'total': max_pages,
                                'status_message': f'Processing stream data: {list(result_data.keys())}'
                            })
                    except Exception as e:
                        logger.warning(f"Could not update task state during processing: {e}")

                    # Handle results
                    if "results" in result_data:
                        for url, page_result in result_data["results"].items():
                            all_links.add(url)
                            
                            # Create filtered result with all necessary data
                            filtered_result = {
                                "url": url,
                                "success": True,
                                "markdown": page_result.get('markdown', ''),
                                "cleaned_html": page_result.get('cleaned_html', ''),
                                "metadata": page_result.get('metadata', {}),
                                "screenshot": page_result.get('screenshot'),
                            }
                            crawl_results.append(filtered_result)
                            
                            # Add content to all_content list
                            content = f"URL: {url}\n\n"
                            if filtered_result['metadata'].get('title'):
                                content += f"Title: {filtered_result['metadata']['title']}\n\n"
                            content += filtered_result['markdown']
                            content += "\n\n---\n\n"
                            all_content.append(content)
                    
                    # Handle explicit progress updates
                    if "crawled_count" in result_data:
                        pages_crawled = result_data["crawled_count"]
                        logger.info(f"External progress update: {pages_crawled}")
                        self.update_state(state='PROGRESS', meta={
                            'current': pages_crawled,
                            'total': max_pages,
                            'status_message': f'External report: {pages_crawled} pages'
                        })

                    # Add small delay to allow state updates to propagate
                    time.sleep(0.1)

                except Exception as e:
                    logger.error(f"Error processing line: {e}")

        # Convert set to list for JSON serialization
        links_list = list(all_links)
        
        # Create crawl result in database with combined content
        crawl_result = CrawlResult.create_with_content(
            user=User.objects.get(id=user_id),
            website_url=website_url,
            content='\n'.join(all_content),
            links_visited={"internal": links_list},
            total_links=len(links_list)
        )

        # Build result
        result = {
            "status": "success",
            "website_url": website_url,
            "crawl_results": crawl_results,
            "total_pages": len(crawl_results),
            "links_visited": links_list,
            "total_links": len(links_list),
            "file_url": crawl_result.get_file_url(),
            "crawl_result_id": crawl_result.id
        }

        logger.info(f"Returning final result with {len(crawl_results)} pages crawled and {len(links_list)} unique links")
        return json.dumps(result)

    except Exception as e:
        logger.error(f"Error in crawl_website_task: {e}", exc_info=True)
        return json.dumps({
            "status": "error",
            "message": str(e)
        })
