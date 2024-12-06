import asyncio
from typing import Optional, Type, List, Dict, Any
from pydantic import BaseModel, Field
from crewai_tools import BaseTool
from urllib.parse import urlparse
from trafilatura import extract
from celery import shared_task
from celery.contrib.abortable import AbortableTask
from django.contrib.auth.models import User
from django.conf import settings
import logging
import os
import re
from apps.crawl_website.models import CrawlResult
from spider_rs import Website, Page
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

class AsyncCrawlWebsiteToolSchema(BaseModel):
    """Input for AsyncCrawlWebsiteTool."""
    website_url: str = Field(..., description="Mandatory website URL to crawl and read content")

class AsyncCrawlWebsiteTool(BaseTool):
    name: str = "Async Crawl and Read Website Content"
    description: str = "An asynchronous tool that can crawl a website and read its content, including content from internal links on the same page."
    args_schema: Type[BaseModel] = AsyncCrawlWebsiteToolSchema
    website_url: Optional[str] = None

    def __init__(self, website_url: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        if website_url:
            self.website_url = website_url
            self.description = f"An asynchronous tool to crawl {website_url} and read its content, including content from internal links."

    async def _run(self, website_url: str = None) -> dict:
        url = website_url or self.website_url
        if not url:
            raise ValueError("No website URL provided")

        logger.info(f"Starting crawl for URL: {url}")
        
        try:
            result = await self.crawl_website(url)
            logger.info(f"Crawl completed. Total links: {result['total_links']}, Links visited: {len(result['links_visited'])}")
            return result
        except Exception as e:
            logger.error(f"Error during crawl: {e}")
            raise

    async def crawl_website(self, url: str) -> Dict[str, Any]:
        website = Website(url)
        website.with_budget({"*": 1000})  # Set a high limit for comprehensive crawling
        website.with_respect_robots_txt(True)
        website.with_subdomains(False)  # Stick to the main domain
        website.with_tld(False)  # Don't crawl top-level domain
        website.with_delay(1)  # Be respectful with a 1-second delay between requests

        pages_queue = asyncio.Queue()
        total_links = 0
        links_visited = set()
        content = ""
        crawl_complete = asyncio.Event()
        semaphore = asyncio.Semaphore(5)  # Limit concurrent processing

        def on_page_event(page: Page):
            nonlocal total_links
            total_links += 1
            logger.info(f"Received page: {page.url}")
            asyncio.run_coroutine_threadsafe(pages_queue.put_nowait(page), asyncio.get_event_loop())

        logger.info("Starting website crawl")
        with ThreadPoolExecutor() as executor:
            crawl_future = executor.submit(website.crawl, on_page_event=on_page_event)

        async def process_pages():
            nonlocal content
            while True:
                try:
                    page = await asyncio.wait_for(pages_queue.get(), timeout=5.0)
                    async with semaphore:
                        logger.info(f"Processing page: {page.url}")
                        page_content = await self._extract_content(page)
                        content += page_content
                        links_visited.add(self._get_relative_path(page.url))
                        pages_queue.task_done()
                        logger.info(f"Processed page: {page.url}, Content length: {len(page_content)}")
                except asyncio.TimeoutError:
                    if crawl_complete.is_set() and pages_queue.empty():
                        logger.info("No more pages to process")
                        break
                    logger.info("Waiting for more pages...")
                except Exception as e:
                    logger.error(f"Error processing page: {e}")

        async def monitor_crawl():
            while not crawl_future.done():
                await asyncio.sleep(1)
            crawl_complete.set()
            logger.info("Crawl completed")

        processing_task = asyncio.create_task(process_pages())
        monitoring_task = asyncio.create_task(monitor_crawl())

        await asyncio.gather(processing_task, monitoring_task)

        if not crawl_future.done():
            logger.warning("Crawl future not completed, waiting for completion")
            crawl_future.result()  # This will raise any exceptions that occurred during crawling

        logger.info(f"Crawl finished. Total links: {total_links}, Links visited: {len(links_visited)}")

        return {
            "content": content,
            "links_visited": list(links_visited),
            "total_links": total_links,
            "links_to_visit": list(set(page.url for page in website.get_pages()) - links_visited)
        }

    async def _extract_content(self, page: Page) -> str:
        try:
            html_content = page.content
            extracted_content = extract(html_content)
            logger.info(f"Extracted content length for {page.url}: {len(extracted_content) if extracted_content else 0}")
            return f"---link: {page.url}\n{extracted_content}\n---page-end---\n" if extracted_content else ""
        except Exception as e:
            logger.error(f"Error extracting content from {page.url}: {e}")
            return ""

    @staticmethod
    def _get_relative_path(url: str) -> str:
        parsed_url = urlparse(url)
        return parsed_url.path or '/'

def sanitize_url(url: str) -> str:
    """Sanitize the URL to create a valid folder name."""
    url = re.sub(r'^https?://(www\.)?', '', url)
    return re.sub(r'[^a-zA-Z0-9]', '_', url)

def save_crawl_result(user_id: int, website_url: str, content: str, links_visited: List[str], total_links: int, links_to_visit: List[str]) -> str:
    """Save the crawl result to a file in the user's directory."""
    sanitized_url = sanitize_url(website_url)
    user_dir = os.path.join(settings.MEDIA_ROOT, f'{user_id}', 'Crawled Websites')
    result_dir = os.path.join(user_dir, sanitized_url)
    os.makedirs(result_dir, exist_ok=True)

    file_path = os.path.join(result_dir, f'{sanitized_url}--content.txt')
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(f"Website URL: {website_url}\n\n")
        f.write(f"Links Visited:\n{', '.join(links_visited)}\n\n")
        f.write(f"Total Links: {total_links}\n\n")
        f.write("Content:\n")
        f.write(content)

    return file_path

@shared_task(bind=True, base=AbortableTask)
def crawl_website_task(self, website_url: str, user_id: int):
    logger.info(f"Starting crawl_website_task for URL: {website_url}")
    
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error(f"User with id {user_id} not found")
        return None

    async_tool = AsyncCrawlWebsiteTool(website_url=website_url)
    
    async def run_crawl():
        return await async_tool._run(website_url)

    try:
        result = asyncio.run(run_crawl())
        logger.info(f"Crawl completed. Total links: {result['total_links']}, Links visited: {len(result['links_visited'])}")
    except Exception as e:
        logger.error(f"Error during crawl: {e}")
        return None

    file_path = save_crawl_result(
        user_id,
        website_url,
        result["content"],
        result["links_visited"],
        result["total_links"],
        result["links_to_visit"]
    )

    crawl_result = CrawlResult.objects.create(
        user=user,
        website_url=website_url,
        content=result["content"],
        links_visited=result["links_visited"],
        total_links=result["total_links"],
        links_to_visit=result["links_to_visit"],
        result_file_path=file_path
    )
    
    logger.info(f"Crawl task completed for URL: {website_url}")
    return crawl_result.id
