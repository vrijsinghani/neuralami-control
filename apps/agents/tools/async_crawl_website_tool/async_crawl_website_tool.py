import asyncio
from typing import Optional, Type, List, Dict, Any
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
from urllib.parse import urlparse, urlunparse
from celery import shared_task
from celery.contrib.abortable import AbortableTask
from django.contrib.auth.models import User
from django.conf import settings
import logging
import os
import re
from apps.crawl_website.models import CrawlResult
from crawl4ai import AsyncWebCrawler
import time
from apps.agents.utils import URLDeduplicator

logger = logging.getLogger(__name__)

class AsyncCrawlResponse:
    """Response object for async crawling with redirect tracking"""
    def __init__(self, url: str, final_url: str, html: str, status_code: int = 200, response_headers: dict = None):
        self.url = url
        self.final_url = final_url
        self.html = html
        self.status_code = status_code
        self.response_headers = response_headers or {}
        self.redirected = url != final_url
        
    def to_dict(self):
        """Convert response to dictionary for JSON serialization"""
        return {
            'url': self.url,
            'final_url': self.final_url,
            'html': self.html,
            'status_code': self.status_code,
            'response_headers': self.response_headers,
            'redirected': self.redirected
        }

class AsyncCrawlWebsiteToolSchema(BaseModel):
    """Input for AsyncCrawlWebsiteTool."""
    website_url: str = Field(..., description="Mandatory website URL to crawl and read content")
    max_pages: int = Field(default=100, description="Maximum number of pages to crawl")

class AsyncCrawlWebsiteTool(BaseTool):
    name: str = "Async Crawl and Read Website Content"
    description: str = "An asynchronous tool that can crawl a website and read its content, including content from internal links on the same page."
    args_schema: Type[BaseModel] = AsyncCrawlWebsiteToolSchema
    website_url: Optional[str] = None
    max_pages: int = 100
    _domain_last_hit = {}  # Track last hit time per domain
    _url_deduplicator: URLDeduplicator = None  # Define the field with type annotation

    def __init__(self, website_url: Optional[str] = None, max_pages: int = 100, **kwargs):
        super().__init__(**kwargs)
        self.max_pages = max_pages
        self._url_deduplicator = URLDeduplicator()  # Initialize the deduplicator
        if website_url:
            self.website_url = website_url
            self.description = f"An asynchronous tool to crawl {website_url} and read its content, including content from internal links."

    async def _run(self, website_url: str = None, max_pages: int = None) -> dict:
        url = website_url or self.website_url
        if not url:
            raise ValueError("No website URL provided")
        
        self.max_pages = max_pages or self.max_pages
        logger.info(f"Starting crawl for URL: {url} with max_pages: {self.max_pages}")
        
        try:
            result = await self.crawl_website(url)
            logger.info(f"Crawl completed. Total links: {result['total_links']}, Links visited: {len(result['links_visited'])}")
            return result
        except Exception as e:
            logger.error(f"Error during crawl: {e}")
            raise

    async def crawl_website(self, url: str) -> Dict[str, Any]:
        domain = urlparse(url).netloc
        current_time = time.time()
        if domain in self._domain_last_hit:
            time_since_last = current_time - self._domain_last_hit[domain]
            if time_since_last < 1:  # 1 second minimum delay between requests to same domain
                await asyncio.sleep(1 - time_since_last)
        self._domain_last_hit[domain] = current_time

        async with AsyncWebCrawler(
            browser_type="chromium",
            headless=True,
            verbose=True,
            magic=True,
            sleep_on_close=False,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        ) as crawler:
            links_visited = set()
            content = []
            total_links = 0
            urls_to_crawl = [url]  # Initialize queue with starting URL
            
            # Process pages in batches
            remaining_pages = self.max_pages
            logger.info(f"Starting crawl with {remaining_pages} pages remaining")
            
            while remaining_pages > 0 and urls_to_crawl:
                current_url = urls_to_crawl.pop(0)  # Get next URL from queue
                #logger.info(f"Processing URL: {current_url} | Pages remaining: {remaining_pages} | Queue size: {len(urls_to_crawl)}")
                
                # Use URL deduplicator to check if we should process this URL
                if not self._url_deduplicator.should_process_url(current_url):
                    continue

                try:
                    result = await crawler.arun(
                        url=current_url,
                        # Content processing settings
                        word_count_threshold=10,
                        excluded_tags=['style', 'script', 'noscript', 'iframe'],
                        remove_overlay_elements=True,
                        
                        # Link handling
                        exclude_external_links=True,
                        extract_links=True,
                        extract_link_selector='a[href]',  # Extract all links with href
                        
                        # Browser control
                        page_timeout=60000,
                        wait_for="body",
                        delay_before_return_html=3.0,  # Increased delay to ensure JS loads
                        wait_for_selector='a[href]',  # Wait for links to be present
                        
                        # Anti-bot features
                        magic=True,
                        simulate_user=True,
                        
                        # Additional settings
                        ignore_robots_txt=True,  # Some sites block bots
                        follow_redirects=True
                    )
                    
                    if not result or not result.success:
                        logger.warning(f"Failed to crawl {current_url}: {getattr(result, 'error_message', 'Unknown error')}")
                        continue

                    # Get content using fit_markdown or fallback to markdown
                    extracted_content = None
                    if hasattr(result, 'fit_markdown') and result.fit_markdown:
                        extracted_content = result.fit_markdown
                    elif hasattr(result, 'markdown') and result.markdown:
                        extracted_content = result.markdown

                    if extracted_content:
                        content.append(f"---link: {current_url}\n{extracted_content}\n---page-end---\n")
                        links_visited.add(current_url)
                        total_links += 1
                        remaining_pages -= 1
                        logger.info(f"Successfully processed {current_url} | Pages remaining: {remaining_pages}")
                        
                        # Process internal links from the result
                        if hasattr(result, 'links') and 'internal' in result.links:
                            base_domain = urlparse(current_url).netloc.lower()
                            # Remove 'www.' if present for domain matching
                            base_domain = base_domain.replace('www.', '')
                            
                            for link_data in result.links['internal']:
                                next_url = link_data.get('href', '').strip()
                                if not next_url or next_url == '#' or next_url.startswith('javascript:'):
                                    continue
                                    
                                try:
                                    # Handle relative URLs
                                    if next_url.startswith('//'):
                                        next_url = f"https:{next_url}"
                                    elif next_url.startswith('/'):
                                        next_url = f"https://{base_domain}{next_url}"
                                    elif not next_url.startswith(('http://', 'https://')):
                                        next_url = f"https://{base_domain}/{next_url.lstrip('/')}"
                                    
                                    parsed_next = urlparse(next_url)
                                    next_domain = parsed_next.netloc.lower().replace('www.', '')
                                    
                                    # Only process URLs from the same domain (ignoring www)
                                    if next_domain != base_domain:
                                        logger.debug(f"Skipping external domain: {next_domain} != {base_domain}")
                                        continue
                                        
                                    # Remove fragments and normalize
                                    normalized_url = urlunparse((
                                        parsed_next.scheme,
                                        parsed_next.netloc.lower(),  # Keep the original www/non-www version
                                        parsed_next.path.rstrip('/'),
                                        '',
                                        parsed_next.query,
                                        ''
                                    ))
                                    
                                    # Add to queue if not visited and not a binary file
                                    if (normalized_url not in links_visited and 
                                        normalized_url not in urls_to_crawl and
                                        not any(normalized_url.lower().endswith(ext) for ext in [
                                            '.pdf', '.jpg', '.jpeg', '.png', '.gif', '.zip', 
                                            '.doc', '.docx', '.xls', '.xlsx', '.css', '.js'
                                        ])):
                                        urls_to_crawl.append(normalized_url)
                                        #logger.info(f"Added URL to crawl queue: {normalized_url} | Queue size: {len(urls_to_crawl)}")
                                except Exception as e:
                                    logger.error(f"Error processing link {next_url}: {e}")
                                    continue
                    else:
                        remaining_pages -= 1
                        logger.warning(f"Failed to extract content from {current_url} | Pages remaining: {remaining_pages}")
                    
                except Exception as e:
                    logger.error(f"Error processing page {current_url}: {e}")
                    continue

            final_content = "".join(content)
            logger.info(f"Crawl finished. Total links: {total_links}, Links visited: {len(links_visited)}")

            return {
                "content": final_content,
                "links_visited": list(links_visited),
                "total_links": total_links,
                "links_to_visit": urls_to_crawl
            }

    @staticmethod
    def _get_relative_path(url: str) -> str:
        parsed_url = urlparse(url)
        if parsed_url.query:
            return f"{parsed_url.path}?{parsed_url.query}"
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
def crawl_website_task(self, website_url: str, user_id: int, max_pages: int = 100):
    logger.info(f"Starting crawl_website_task for URL: {website_url}")
    
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error(f"User with id {user_id} not found")
        return None

    async_tool = AsyncCrawlWebsiteTool(website_url=website_url, max_pages=max_pages)
    
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
