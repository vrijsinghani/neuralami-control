import logging
import aiohttp
import asyncio
from typing import Optional, Dict, Any, Type
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

logger = logging.getLogger(__name__)

class CrawlWebsiteToolSchema(BaseModel):
    """Input for CrawlWebsiteTool."""
    website_url: str = Field(..., description="Mandatory website URL to crawl and read content")
    max_pages: int = Field(default=100, description="Maximum number of pages to crawl")
    css_selector: Optional[str] = Field(default=None, description="CSS selector for content extraction")
    wait_for: Optional[str] = Field(default=None, description="Wait for element/condition before extraction")

    model_config = {
        "extra": "forbid"
    }

@shared_task(bind=True, base=AbortableTask)
def crawl_website_task(self, website_url: str, user_id: int, max_pages: int = 100, save_file: bool = True,
                      wait_for: Optional[str] = None, css_selector: Optional[str] = None) -> int:
    """Celery task to crawl website using Crawl4AI service."""
    logger.info(f"Starting crawl for URL: {website_url}")

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error(f"User with id {user_id} not found")
        raise

    # Prepare request data
    request_data = {
        "urls": website_url,
        "max_pages": max_pages,
        "priority": 10,
        "crawler_params": {
            **settings.CRAWL4AI_CRAWLER_PARAMS,
            "wait_for": wait_for,  # Using the parameter directly instead of kwargs
            "remove_overlay_elements": True,
            "delay_before_return_html": 2.0,
        },
        "extra": {
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

    # Add css_selector if provided
    if css_selector:
        request_data["extra"]["css_selector"] = css_selector

    headers = {"Authorization": f"Bearer {settings.CRAWL4AI_API_KEY}"} if settings.CRAWL4AI_API_KEY else {}

    try:
        # Start crawl
        response = requests.post(
            f"{settings.CRAWL4AI_URL}/crawl",
            headers=headers,
            json=request_data
        )
        if not response.ok:
            raise Exception(f"Failed to start crawl: {response.text}")
        
        data = response.json()
        crawl_task_id = data["task_id"]
        
        # Poll for results
        while True:
            result_response = requests.get(
                f"{settings.CRAWL4AI_URL}/task/{crawl_task_id}",
                headers=headers
            )
            if not result_response.ok:
                raise Exception(f"Failed to get results: {result_response.text}")
            
            result_data = result_response.json()
            status = result_data.get("status")
            progress = result_data.get("progress", {})
            
            # Update task progress
            self.update_state(
                state='PROGRESS',
                meta={
                    'current': progress.get("current", 0),
                    'total': progress.get("total", max_pages),
                    'status': progress.get("status", "Processing..."),
                }
            )
            
            if status == "completed":
                # Get the markdown content
                markdown_content = result_data.get("result", {}).get("markdown", "")
                
                # Get the fit_markdown if available, otherwise use regular markdown
                content = result_data.get("result", {}).get("fit_markdown", markdown_content)
                
                # Structure the links in a dictionary format
                links = result_data.get("result", {}).get("links", [])
                links_data = {
                    "internal": links,
                    "total": len(links)
                }
                
                # Create CrawlResult using the create_with_content class method
                crawl_result = CrawlResult.create_with_content(
                    user=user,
                    website_url=website_url,
                    content=content,
                    links_visited=links_data,
                    total_links=len(links)
                )
                
                return crawl_result.id
            
            elif status == "failed":
                raise Exception(f"Crawl failed: {result_data.get('error')}")
            
            time.sleep(2)

    except Exception as e:
        logger.error(f"Error during crawl: {e}")
        raise

class CrawlWebsiteTool(BaseTool):
    name: str = "Crawl and Read Website Content"
    description: str = "A tool that can crawl a website and read its content, including content from internal links on the same page."
    args_schema: Type[BaseModel] = CrawlWebsiteToolSchema
    
    def _run(self, website_url: Optional[str] = None, max_pages: int = 100, **kwargs: Any) -> Dict:
        """Run the tool by creating a Celery task."""
        try:
            # Handle both direct website_url parameter and kwargs
            url_to_crawl = website_url or kwargs.get('website_url')
            if not url_to_crawl:
                raise ValueError("No website URL provided")

            # Get the user ID from kwargs or context
            user_id = kwargs.get('user_id')
            if not user_id:
                raise ValueError("No user_id provided")

            # Start celery task with explicit parameters
            task = crawl_website_task.delay(
                website_url=url_to_crawl,
                user_id=user_id,
                max_pages=max_pages,
                wait_for=kwargs.get('wait_for'),
                css_selector=kwargs.get('css_selector'),
                save_file=kwargs.get('save_file', True)
            )

            # Return task ID for progress tracking
            return {
                "task_id": str(task.id),
                "status": "started",
                "message": f"Crawl task started for {url_to_crawl}"
            }

        except Exception as e:
            error_msg = f"Error starting crawl: {str(e)}"
            logger.error(error_msg)
            return {
                "status": "error",
                "message": error_msg
            }
