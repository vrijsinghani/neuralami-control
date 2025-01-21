import asyncio
import logging
import json
from typing import Dict, List, Any, Optional, Type, Set
from datetime import datetime
from urllib.parse import urljoin, urlparse, urlunparse
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
from celery import shared_task
from celery.contrib.abortable import AbortableTask
import aiohttp
import os

from apps.agents.tools.browser_tool.browser_tool import BrowserTool
from apps.crawl_website.models import CrawlResult
from apps.common.utils import normalize_url
from apps.agents.utils import URLDeduplicator

logger = logging.getLogger(__name__)

class SEOCrawlerToolSchema(BaseModel):
    """Input schema for SEOCrawlerTool."""
    website_url: str = Field(
        ..., 
        title="Website URL",
        description="Website URL to crawl (e.g., https://example.com)"
    )
    max_pages: int = Field(
        default=100,
        title="Max Pages",
        description="Maximum number of pages to crawl"
    )
    respect_robots_txt: bool = Field(
        default=True,
        title="Respect Robots.txt",
        description="Whether to respect robots.txt rules"
    )
    crawl_delay: float = Field(
        default=1.0,
        title="Crawl Delay",
        description="Delay between requests in seconds"
    )

class SEOPage(BaseModel):
    """Represents a crawled page with SEO-relevant data."""
    url: str = Field(..., description="URL of the page")
    html: str = Field(..., description="Raw HTML content")
    text_content: str = Field(..., description="Extracted text content")
    title: str = Field(default="", description="Page title")
    meta_description: str = Field(default="", description="Meta description")
    meta_keywords: List[str] = Field(default_factory=list, description="Meta keywords")
    h1_tags: List[str] = Field(default_factory=list, description="H1 headings")
    links: List[str] = Field(default_factory=list, description="Found links")
    status_code: int = Field(..., description="HTTP status code")
    content_type: str = Field(default="general", description="Content type")
    crawl_timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(), description="When the page was crawled")

    model_config = {"arbitrary_types_allowed": True}

    def model_dump(self, **kwargs):
        """Override model_dump to ensure datetime is serialized."""
        data = super().model_dump(**kwargs)
        # Ensure crawl_timestamp is a string
        if isinstance(data['crawl_timestamp'], datetime):
            data['crawl_timestamp'] = data['crawl_timestamp'].isoformat()
        return data

class SEOCrawlerToolConfig(BaseModel):
    """Configuration model for SEOCrawlerTool."""
    max_pages: int = Field(default=100, description="Maximum number of pages to crawl")
    max_concurrent: int = Field(default=5, description="Maximum number of concurrent requests")
    visited_urls: Set[str] = Field(default_factory=set, description="Set of visited URLs")
    found_links: Set[str] = Field(default_factory=set, description="Set of links found during crawling")
    pages: List[SEOPage] = Field(default_factory=list, description="List of crawled pages")
    url_deduplicator: URLDeduplicator = Field(default_factory=URLDeduplicator, description="URL deduplication utility")
    browser_tool: BrowserTool = Field(default_factory=BrowserTool, description="Browser tool for making requests")
    page_callback: Optional[Any] = Field(default=None, description="Callback function for processing pages")

    model_config = {"arbitrary_types_allowed": True}

class SEOCrawlerTool(BaseTool):
    """Tool for crawling websites and extracting SEO-relevant information."""
    name: str = "seo_crawler"
    description: str = "Tool for crawling websites and extracting SEO-relevant information"
    args_schema: Type[SEOCrawlerToolSchema] = SEOCrawlerToolSchema
    config: SEOCrawlerToolConfig = Field(default_factory=SEOCrawlerToolConfig)
    
    def __init__(self, **data):
        super().__init__(**data)
        self._semaphore = None
        # Ensure tools are initialized
        if not self.config.url_deduplicator:
            self.config.url_deduplicator = URLDeduplicator()
        if not self.config.browser_tool:
            self.config.browser_tool = BrowserTool()

    @property
    def semaphore(self) -> Optional[asyncio.Semaphore]:
        return self._semaphore
        
    @semaphore.setter
    def semaphore(self, value: Optional[asyncio.Semaphore]):
        self._semaphore = value

    async def _async_run(
        self,
        website_url: str,
        max_pages: Optional[int] = None,
        max_concurrent: Optional[int] = None,
        respect_robots_txt: bool = True,
        crawl_delay: float = 1.0,
        progress_callback = None,
        page_callback = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Run the crawler asynchronously."""
        if max_pages is not None:
            self.config.max_pages = max_pages
        if max_concurrent is not None:
            self.config.max_concurrent = max_concurrent
        
        self.semaphore = asyncio.Semaphore(self.config.max_concurrent)
        self.config.page_callback = page_callback
        
        return await self._async_crawl(
            website_url=website_url,
            max_pages=self.config.max_pages,
            respect_robots_txt=respect_robots_txt,
            crawl_delay=crawl_delay,
            progress_callback=progress_callback
        )

    def _run(
        self,
        website_url: str,
        max_pages: Optional[int] = None,
        max_concurrent: Optional[int] = None,
        respect_robots_txt: bool = True,
        crawl_delay: float = 1.0,
        progress_callback = None,
        page_callback = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Run the crawler synchronously."""
        # Create a new event loop if one doesn't exist
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        try:
            return loop.run_until_complete(
                self._async_run(
                    website_url=website_url,
                    max_pages=max_pages,
                    max_concurrent=max_concurrent,
                    respect_robots_txt=respect_robots_txt,
                    crawl_delay=crawl_delay,
                    progress_callback=progress_callback,
                    page_callback=page_callback,
                    **kwargs
                )
            )
        finally:
            # Clean up the event loop if we created it
            if not loop.is_running():
                loop.close()

    async def _async_crawl(
        self,
        website_url: str,
        max_pages: int,
        respect_robots_txt: bool,
        crawl_delay: float,
        progress_callback = None
    ) -> Dict[str, Any]:
        """Crawl the website asynchronously."""
        start_time = datetime.now()
        
        # Ensure website_url has protocol
        if not website_url.startswith(('http://', 'https://')):
            website_url = 'https://' + website_url
            
        # Initialize with the start URL
        self.config.found_links.add(website_url)
        
        while len(self.config.visited_urls) < max_pages and self.config.found_links:
            # Get next batch of URLs to process
            batch_size = min(5, max_pages - len(self.config.visited_urls))
            batch_urls = set(list(self.config.found_links)[:batch_size])
            self.config.found_links -= batch_urls
            
            # Process batch concurrently
            tasks = []
            for url in batch_urls:
                if url not in self.config.visited_urls:
                    tasks.append(self._process_url(url))
            
            if tasks:
                await asyncio.gather(*tasks)
                await asyncio.sleep(crawl_delay)  # Respect crawl delay between batches

                # Send progress update
                if progress_callback:
                    pages_analyzed = len(self.config.visited_urls)
                    percent_complete = min(100, int((pages_analyzed / max_pages) * 100))
                    total_links = len(self.config.visited_urls) + len(self.config.found_links)
                    progress_callback({
                        'percent_complete': percent_complete,
                        'pages_analyzed': pages_analyzed,
                        'total_links': total_links,
                        'status': f'Page {pages_analyzed} of {max_pages}...',
                        'current_url': list(batch_urls)[-1] if batch_urls else None,
                        'new_links_found': sum(len(self._extract_links(url, '')) for url in batch_urls),
                        'remaining_urls': len(self.config.found_links)
                    })

        # Prepare results
        end_time = datetime.now()
        return {
            "pages": [page.model_dump() for page in self.config.pages],
            "total_pages": len(self.config.pages),
            "total_links": len(self.config.visited_urls),
            "crawl_time_seconds": (end_time - start_time).total_seconds(),
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "visited_urls": list(self.config.visited_urls),
            "remaining_urls": list(self.config.found_links),
            "timestamp": datetime.now().isoformat()  # Add timestamp for consistency
        }

    async def _process_url(self, url: str, parent_url: Optional[str] = None) -> Optional[SEOPage]:
        """Process a single URL and return a SEOPage object."""
        if not url or not self.config.url_deduplicator.should_process_url(url):
            return None
            
        # Check if URL points to an image or media file
        if self._is_media_url(url):
            # For media URLs, just verify they're accessible but don't create a page
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.head(url, allow_redirects=True) as response:
                        if response.status < 400:
                            return None
                        # If HEAD fails, try GET as some servers don't support HEAD for media
                        async with session.get(url, allow_redirects=True) as get_response:
                            if get_response.status < 400:
                                return None
            except Exception as e:
                logger.warning(f"Failed to verify media URL {url}: {str(e)}")
            return None

        normalized_url = self.config.url_deduplicator._normalize_url(url)
        if normalized_url in self.config.visited_urls:
            return None

        self.config.visited_urls.add(normalized_url)

        # Get page content using BrowserTool
        #logger.info(f"Fetching content for {normalized_url}")
        raw_html = await asyncio.to_thread(
            self.config.browser_tool._run,
            normalized_url,
            output_type="raw"
        )
        
        if not raw_html:
            logger.warning(f"No content received for {normalized_url}")
            return None
        
        # Parse the page
        soup = BeautifulSoup(raw_html, 'lxml')
        
        # Extract text content
        text_content = await asyncio.to_thread(
            self.config.browser_tool._run,
            normalized_url,
            output_type="text"
        )
        
        # Extract links before creating the page object
        base_domain = urlparse(normalized_url).netloc
        extracted_links = self._extract_links(normalized_url, raw_html)
        
        # Filter links to only include same-domain URLs that haven't been visited
        new_links = {
            link for link in extracted_links
            if urlparse(link).netloc == base_domain
            and link not in self.config.visited_urls
            and self.config.url_deduplicator.should_process_url(link)
        }
        
        # Add new links to found_links
        self.config.found_links.update(new_links)
        # logger.info(f"Found {len(new_links)} new links on {normalized_url}")
        
        # Extract SEO relevant data
        page = SEOPage(
            url=normalized_url,
            html=raw_html,
            text_content=text_content,
            title=soup.title.string if soup.title else "",
            meta_description=self._get_meta_content(soup, "description"),
            meta_keywords=self._get_meta_content(soup, "keywords").split(",") if self._get_meta_content(soup, "keywords") else [],
            h1_tags=[h1.get_text(strip=True) for h1 in soup.find_all("h1")],
            links=extracted_links,
            status_code=200,  # BrowserTool would have raised an error if not 200
            content_type=self.config.browser_tool.detect_content_type(normalized_url, raw_html),
            crawl_timestamp=datetime.now().isoformat()
        )

        # Store the page
        self.config.pages.append(page)
        #logger.info(f"Successfully processed {normalized_url}")
        
        # Call the page callback if provided
        if hasattr(self.config, 'page_callback') and self.config.page_callback:
            try:
                processed_page = self.config.page_callback(page)
                if processed_page:
                    page = processed_page
            except Exception as e:
                logger.error(f"Error in page callback for {normalized_url}: {str(e)}")
        
        return page

    def _is_media_url(self, url: str) -> bool:
        """Check if a URL points to an image or media file."""
        parsed_url = urlparse(url)
        path = parsed_url.path.lower()
        return any(path.endswith(ext) for ext in [
            '.jpg', '.jpeg', '.png', '.gif', '.svg', 
            '.webp', '.ico', '.pdf', '.mp4', '.webm'
        ])

    def _get_meta_content(self, soup: BeautifulSoup, name: str) -> str:
        """Extract content from a meta tag."""
        meta = soup.find("meta", attrs={"name": name})
        return meta.get("content", "") if meta else ""

    def _extract_links(self, base_url: str, html_content: str) -> List[str]:
        """Extract and normalize all links from the page."""
        links = set()  # Use a set to avoid duplicates
        base_domain = urlparse(base_url).netloc
        normalized_base = normalize_url(base_url)
        
        soup = BeautifulSoup(html_content, 'lxml')
        
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            try:
                # Skip empty, javascript, mailto, tel links
                if not href or href.startswith(('javascript:', 'mailto:', 'tel:', '#', 'data:', 'file:', 'about:')):
                    continue
                    
                # Convert to absolute URL
                absolute_url = urljoin(normalized_base, href)
                normalized_url = normalize_url(absolute_url)
                parsed_url = urlparse(normalized_url)
                
                # Only include http(s) URLs from the same domain
                if (parsed_url.scheme in ('http', 'https') and 
                    parsed_url.netloc == base_domain):
                    # Normalize URL
                    links.add(normalized_url)
                    
            except Exception as e:
                logger.warning(f"Error processing link {href}: {str(e)}")
                
        return list(links)

    async def _process_page(self, url: str, html_content: str, status_code: int) -> Dict[str, Any]:
        """Process a single page and extract relevant information."""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract images with their attributes
        images = []
        for img in soup.find_all('img'):
            image_data = {
                "src": img.get('src', ''),
                "alt": img.get('alt', ''),
                "width": img.get('width', ''),
                "height": img.get('height', ''),
                "title": img.get('title', ''),
                "loading": img.get('loading', ''),
                "srcset": img.get('srcset', ''),
                "size": 0  # Will be populated for local images
            }
            
            # Normalize image URL
            if image_data["src"]:
                image_data["src"] = urljoin(url, image_data["src"])
                
                # Get image size if it's from the same domain
                if urlparse(image_data["src"]).netloc == urlparse(url).netloc:
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.head(image_data["src"]) as response:
                                if response.status == 200:
                                    image_data["size"] = int(response.headers.get('content-length', 0))
                    except Exception as e:
                        logger.warning(f"Failed to get image size for {image_data['src']}: {str(e)}")
            
            images.append(image_data)

        # Extract existing data
        title = soup.title.string.strip() if soup.title else ""
        meta_desc = ""
        meta_desc_tag = soup.find('meta', attrs={'name': 'description'})
        if meta_desc_tag:
            meta_desc = meta_desc_tag.get('content', '').strip()

        h1_tags = [h1.get_text().strip() for h1 in soup.find_all('h1')]
        
        # Extract links
        links = []
        for link in soup.find_all('a'):
            href = link.get('href')
            if href:
                absolute_url = urljoin(url, href)
                if self._should_include_url(absolute_url):
                    links.append(absolute_url)

        # Get text content
        text_content = ' '.join([
            p.get_text().strip()
            for p in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        ])

        return {
            "url": url,
            "title": title,
            "meta_description": meta_desc,
            "h1_tags": h1_tags,
            "links": links,
            "images": images,  # Add images to the return data
            "text_content": text_content,
            "status_code": status_code,
            "crawl_timestamp": datetime.now().isoformat()
        }

@shared_task(bind=True, base=AbortableTask)
def crawl_website_task(self, website_url: str, user_id: int, max_pages: int = 100) -> Optional[int]:
    """Celery task to run the crawler asynchronously."""
    logger.info(f"Starting crawl task for {website_url}")
    
    crawler = SEOCrawlerTool()
    try:
        result = crawler._run(website_url, max_pages=max_pages)
        
        # Create CrawlResult
        crawl_result = CrawlResult.objects.create(
            user_id=user_id,
            website_url=website_url,
            content=result["pages"],
            links_visited=list(crawler.config.visited_urls),
            total_links=result["total_links"],
            links_to_visit=list(crawler.config.found_links)
        )
        
        logger.info(f"Crawl completed for {website_url}")
        return crawl_result.id
        
    except Exception as e:
        logger.error(f"Error during crawl: {str(e)}")
        return None
