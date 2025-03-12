import asyncio
import logging
import json
from typing import Dict, List, Any, Optional, Type, Set, Literal, Union
from datetime import datetime
from urllib.parse import urljoin, urlparse, urlunparse
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from apps.agents.tools.base_tool import BaseTool
from celery import shared_task
from celery.contrib.abortable import AbortableTask
import aiohttp
import os
import time

from apps.agents.tools.crawl_website_tool.crawl_website_tool import CrawlWebsiteTool
from apps.crawl_website.models import CrawlResult
from apps.common.utils import normalize_url
from apps.agents.utils import URLDeduplicator

logger = logging.getLogger(__name__)

# Define valid page sections
PageSection = Literal[
    "url", "html", "text_content", "title", "meta_description", "meta_keywords", 
    "h1_tags", "links", "status_code", "content_type", "crawl_timestamp",
    "has_header", "has_nav", "has_main", "has_footer", "has_article", "has_section", "has_aside",
    "og_title", "og_description", "og_image",
    "canonical_url", "canonical_tags",
    "viewport",
    "images",
    "internal_links", "external_links"
]

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
    sections: Optional[List[PageSection]] = Field(
        default=None,
        title="Sections to Return",
        description="List of page sections to include in results (default: all sections)"
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
    links: Set[str] = Field(default_factory=set, description="All found links")
    status_code: int = Field(..., description="HTTP status code")
    content_type: str = Field(default="general", description="Content type")
    crawl_timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(), description="When the page was crawled")
    # Semantic structure data
    has_header: bool = Field(default=False, description="Whether the page has a header")
    has_nav: bool = Field(default=False, description="Whether the page has a navigation")
    has_main: bool = Field(default=False, description="Whether the page has a main content area")
    has_footer: bool = Field(default=False, description="Whether the page has a footer")
    has_article: bool = Field(default=False, description="Whether the page has an article")
    has_section: bool = Field(default=False, description="Whether the page has a section")
    has_aside: bool = Field(default=False, description="Whether the page has an aside")
    # OpenGraph data
    og_title: Optional[str] = Field(default=None, description="OpenGraph title")
    og_description: Optional[str] = Field(default=None, description="OpenGraph description")
    og_image: Optional[str] = Field(default=None, description="OpenGraph image")
    # Canonical data
    canonical_url: Optional[str] = Field(default=None, description="Canonical URL")
    canonical_tags: List[str] = Field(default_factory=list, description="Canonical tags")
    # Viewport data
    viewport: Optional[str] = Field(default=None, description="Viewport meta tag")
    # Image data
    images: List[Dict[str, Any]] = Field(default_factory=list, description="Images with attributes")
    # Link categorization
    internal_links: Set[str] = Field(default_factory=set, description="Internal links")
    external_links: Set[str] = Field(default_factory=set, description="External links")

    model_config = {"arbitrary_types_allowed": True}

    def model_dump(self, **kwargs):
        """Override model_dump to ensure datetime is serialized."""
        data = super().model_dump(**kwargs)
        # Ensure crawl_timestamp is a string
        if isinstance(data['crawl_timestamp'], datetime):
            data['crawl_timestamp'] = data['crawl_timestamp'].isoformat()
        # Convert sets to lists for JSON serialization
        if 'links' in data and isinstance(data['links'], set):
            data['links'] = list(data['links'])
        if 'internal_links' in data and isinstance(data['internal_links'], set):
            data['internal_links'] = list(data['internal_links'])
        if 'external_links' in data and isinstance(data['external_links'], set):
            data['external_links'] = list(data['external_links'])
        return data
        
    def filtered_dump(self, sections: Optional[List[PageSection]] = None) -> Dict[str, Any]:
        """Return a filtered dictionary containing only the specified sections."""
        data = self.model_dump()
        
        # If no sections specified, return all data
        if not sections:
            return data
            
        # Filter data to include only requested sections
        return {key: value for key, value in data.items() if key in sections}

class SEOCrawlerToolConfig(BaseModel):
    """Configuration model for SEOCrawlerTool."""
    max_pages: int = Field(default=100, description="Maximum number of pages to crawl")
    max_concurrent: int = Field(default=5, description="Maximum number of concurrent requests")
    visited_urls: Set[str] = Field(default_factory=set, description="Set of visited URLs")
    found_links: Set[str] = Field(default_factory=set, description="Set of links found during crawling")
    pages: List[SEOPage] = Field(default_factory=list, description="List of crawled pages")
    url_deduplicator: URLDeduplicator = Field(default_factory=URLDeduplicator, description="URL deduplication utility")
    crawl_tool: CrawlWebsiteTool = Field(default_factory=CrawlWebsiteTool, description="Crawl tool for making requests")
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
        if not self.config.crawl_tool:
            self.config.crawl_tool = CrawlWebsiteTool()

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
        sections: Optional[Union[List[PageSection], str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Run the crawler asynchronously."""
        # Convert sections from string to list if provided as a string
        if sections and isinstance(sections, str):
            try:
                sections = json.loads(sections)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse sections parameter: {sections}. Using all sections.")
                sections = None
                
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
            progress_callback=progress_callback,
            sections=sections
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
        sections: Optional[Union[List[PageSection], str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Run the crawler synchronously."""
        # Convert sections from string to list if provided as a string
        if sections and isinstance(sections, str):
            try:
                sections = json.loads(sections)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse sections parameter: {sections}. Using all sections.")
                sections = None
                
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
                    sections=sections,
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
        progress_callback = None,
        sections: Optional[List[PageSection]] = None
    ) -> Dict[str, Any]:
        """Crawl the website asynchronously."""
        start_time = datetime.now()
        
        logger.info(f"Starting _async_crawl with max_pages: {max_pages}")
        
        # Ensure website_url has protocol
        if not website_url.startswith(('http://', 'https://')):
            website_url = 'https://' + website_url
            
        # IMPORTANT: Clear state to ensure we start fresh
        self.config.visited_urls = set()
        self.config.pages = []
        self.config.found_links = set()
        
        # Initialize with the start URL
        self.config.found_links.add(website_url)
        
        # Safety counter to prevent infinite loops
        iterations = 0
        max_iterations = max(100, max_pages * 2)
        
        # Error tracking to stop on consecutive failures
        consecutive_errors = 0
        max_consecutive_errors = 3
        
        while len(self.config.visited_urls) < max_pages and self.config.found_links and iterations < max_iterations:
            iterations += 1
            logger.info(f"Crawl iteration {iterations}/{max_iterations}")
            
            # Safety check - stop if we've reached max_pages
            if len(self.config.visited_urls) >= max_pages:
                logger.info(f"Reached max_pages ({max_pages}), stopping crawl")
                break
                
            # Get next batch of URLs to process
            batch_size = min(self.config.max_concurrent, max_pages - len(self.config.visited_urls))
            if batch_size <= 0:
                logger.info(f"No more capacity to crawl pages (visited: {len(self.config.visited_urls)}, max: {max_pages})")
                break
                
            batch_urls = set(list(self.config.found_links)[:batch_size])
            self.config.found_links -= batch_urls
            
            logger.info(f"Crawl loop: visited_urls count: {len(self.config.visited_urls)}, max_pages: {max_pages}, found_links: {len(self.config.found_links)}")
            logger.info(f"Processing batch of {len(batch_urls)} URLs: {batch_urls}")
            
            # Process batch concurrently
            tasks = []
            for url in batch_urls:
                if url not in self.config.visited_urls and len(self.config.visited_urls) < max_pages:
                    tasks.append(self._process_url(url))
                else:
                    logger.info(f"Skipping URL {url}, already visited or at max_pages limit")
            
            if tasks:
                # Use wait instead of gather to not block if a task hangs
                done, pending = await asyncio.wait(tasks, timeout=30)
                
                # Track success/failure for this batch
                successful_pages = 0
                
                if pending:
                    logger.warning(f"{len(pending)} tasks timed out and will be cancelled")
                    for task in pending:
                        task.cancel()
                
                # Check the results from done tasks
                for task in done:
                    try:
                        result = task.result()
                        if result is not None:
                            successful_pages += 1
                    except Exception as e:
                        logger.error(f"Error in task: {str(e)}", exc_info=True)
                
                # If no pages were successfully processed in this batch, increment consecutive errors
                if successful_pages == 0 and len(tasks) > 0:
                    consecutive_errors += 1
                    logger.warning(f"No pages successfully processed in this batch. Consecutive errors: {consecutive_errors}")
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error(f"Too many consecutive errors ({consecutive_errors}), stopping crawl")
                        break
                else:
                    # Reset consecutive errors on success
                    consecutive_errors = 0
                
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
                        'new_links_found': len(self.config.found_links),
                        'remaining_urls': len(self.config.found_links)
                    })
            
            # Extra safety check - stop if we've reached max_pages
            if len(self.config.visited_urls) >= max_pages:
                logger.info(f"Reached max_pages ({max_pages}) after processing batch, stopping crawl")
                break

        logger.info(f"Crawl loop completed. Final visited_urls count: {len(self.config.visited_urls)}, max_pages: {max_pages}")

        # Prepare results
        end_time = datetime.now()
        return {
            "pages": [page.filtered_dump(sections) for page in self.config.pages],
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
            logger.info(f"URL not processable: {url}")
            return None
            
        # Normalize early to prevent duplicate processing
        normalized_url = self.config.url_deduplicator.canonicalize_url(url)
        
        # Check if we've already visited this URL
        if normalized_url in self.config.visited_urls:
            logger.info(f"URL already visited, skipping: {normalized_url}")
            return None
            
        # Mark URL as visited early to prevent duplicates in concurrent processing
        self.config.visited_urls.add(normalized_url)
        logger.info(f"Added URL to visited_urls: {normalized_url} (count now: {len(self.config.visited_urls)})")
            
        # Check if URL points to an image or media file
        async with self.semaphore:
            if self._is_media_url(url):
                logger.info(f"Skipping media URL: {url}")
                return None

            logger.info(f"Processing URL: {url} (normalized: {normalized_url})")

            try:
                # Add a timeout for the crawl_tool._run call
                try:
                    # Use asyncio.wait_for to add a timeout to the to_thread operation
                    result = await asyncio.wait_for(
                        asyncio.to_thread(
                            self.config.crawl_tool._run,
                            website_url=normalized_url,
                            user_id=1,  # TODO: Pass user_id properly
                            max_pages=1,
                            max_depth=0,
                            output_type="full"
                        ),
                        timeout=60  # 60 second timeout for page processing
                    )
                except asyncio.TimeoutError:
                    logger.error(f"Timeout processing URL {normalized_url} after 60 seconds")
                    return None
                
                if isinstance(result, dict):
                    data = result
                else:
                    try:
                        data = json.loads(result)
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse result for {normalized_url}: {result[:100]}...", exc_info=True)
                        return None
                
                if data.get("status") != "success" or not data.get("results"):
                    logger.warning(f"Failed to get content for {normalized_url}")
                    return None

                # Handle different possible response structures
                page_data = None
                if isinstance(data.get("results"), list) and data["results"]:
                    if isinstance(data["results"][0], dict):
                        page_data = data["results"][0].get("content", {})
                elif isinstance(data.get("result"), dict):
                    page_data = data["result"].get("content", {})
                
                if not page_data:
                    logger.warning(f"Invalid page data structure for {normalized_url}")
                    return None

                html_content = page_data.get("html", "")
                if not isinstance(html_content, str):
                    if html_content is None:
                        html_content = ""
                    else:
                        try:
                            html_content = str(html_content)
                        except Exception as e:
                            logger.error(f"Error converting HTML content to string for {normalized_url}: {str(e)}")
                            return None

                metadata = page_data.get("metadata", {})
                
                # Parse HTML to extract additional data
                try:
                    soup = BeautifulSoup(html_content, 'lxml')
                except Exception as e:
                    logger.error(f"Error parsing HTML for {normalized_url}: {str(e)}")
                    return None
                
                # Extract text content from HTML
                text_content = " ".join(soup.stripped_strings)
                
                # Extract h1 tags
                h1_tags = [h1.get_text(strip=True) for h1 in soup.find_all('h1')]
                
                # Determine content type based on HTML structure
                content_type = "general"
                if soup.find('article'):
                    content_type = "article"
                elif soup.find(['form', 'input']):
                    content_type = "form"
                elif soup.find(['table', 'tbody']):
                    content_type = "data"

                # Extract semantic structure data
                has_header = bool(soup.find('header'))
                has_nav = bool(soup.find('nav'))
                has_main = bool(soup.find('main'))
                has_footer = bool(soup.find('footer'))
                has_article = bool(soup.find('article'))
                has_section = bool(soup.find('section'))
                has_aside = bool(soup.find('aside'))

                # Extract OpenGraph tags
                og_title = soup.find('meta', property='og:title')
                og_description = soup.find('meta', property='og:description')
                og_image = soup.find('meta', property='og:image')

                # Extract canonical URL
                canonical_tag = soup.find('link', rel='canonical')
                canonical_url = canonical_tag['href'] if canonical_tag else None
                canonical_tags = soup.find_all('link', rel='canonical')
                
                # Extract viewport meta tag
                viewport = soup.find('meta', attrs={'name': 'viewport'})
                
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
                    
                    images.append(image_data)
                
                # Extract all links and categorize them
                base_domain = urlparse(normalized_url).netloc
                internal_links = set()
                external_links = set()
                
                for a in soup.find_all('a', href=True):
                    href = a["href"].strip()
                    try:
                        # Skip empty, javascript, mailto, tel links
                        if not href or href.startswith(('javascript:', 'mailto:', 'tel:', '#', 'data:', 'file:', 'about:')):
                            continue
                            
                        # Convert to absolute URL
                        absolute_url = urljoin(normalized_url, href)
                        parsed_url = urlparse(absolute_url)
                        
                        # Categorize as internal or external
                        if parsed_url.netloc == base_domain:
                            if self.config.url_deduplicator.should_process_url(absolute_url):
                                internal_links.add(absolute_url)
                        else:
                            external_links.add(absolute_url)
                            
                    except Exception as e:
                        logger.warning(f"Error processing link {href}: {str(e)}")

                # Update found_links with internal links
                self.config.found_links.update(internal_links)
                logger.info(f"Added {len(internal_links)} new internal links from {normalized_url}")

                # Create SEOPage object with enhanced data
                page = SEOPage(
                    url=normalized_url,
                    html=html_content,
                    text_content=text_content,
                    title=metadata.get("title") or "",
                    meta_description=metadata.get("description") or "",
                    meta_keywords=metadata.get("keywords", "").split(",") if metadata.get("keywords") else [],
                    h1_tags=h1_tags,
                    links=internal_links | external_links,  # Combine internal and external links
                    status_code=page_data.get("status_code", 200),
                    content_type=content_type,
                    crawl_timestamp=datetime.now().isoformat(),
                    # Add semantic structure data
                    has_header=has_header,
                    has_nav=has_nav,
                    has_main=has_main,
                    has_footer=has_footer,
                    has_article=has_article,
                    has_section=has_section,
                    has_aside=has_aside,
                    # Add OpenGraph data
                    og_title=og_title.get('content') if og_title else None,
                    og_description=og_description.get('content') if og_description else None,
                    og_image=og_image.get('content') if og_image else None,
                    # Add canonical data
                    canonical_url=canonical_url,
                    canonical_tags=canonical_tags,
                    # Add viewport data
                    viewport=viewport.get('content') if viewport else None,
                    # Add image data
                    images=images,
                    # Add link categorization
                    internal_links=internal_links,
                    external_links=external_links
                )

                # Store the page
                self.config.pages.append(page)
                logger.info(f"Page processed and added to results: {normalized_url}")
                
                # Call the page callback if provided
                if hasattr(self.config, 'page_callback') and self.config.page_callback:
                    try:
                        processed_page = self.config.page_callback(page)
                        if processed_page:
                            page = processed_page
                    except Exception as e:
                        logger.error(f"Error in page callback for {normalized_url}: {str(e)}")
                
                return page

            except Exception as e:
                logger.error(f"Error processing URL {normalized_url}: {str(e)}", exc_info=True)
                return None

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

@shared_task(bind=True, base=AbortableTask, time_limit=600, soft_time_limit=540)
def crawl_website_task(self, website_url: str, user_id: int, max_pages: int = 100, sections: Optional[Union[List[str], str]] = None) -> Optional[int]:
    """Celery task to run the crawler asynchronously."""
    logger.info(f"Starting crawl task for {website_url} with max_pages={max_pages}, sections={sections}")
    
    start_time = time.time()
    
    # Convert sections from string to list if provided as a string
    if sections and isinstance(sections, str):
        try:
            sections = json.loads(sections)
            logger.info(f"Parsed sections from string: {sections}")
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse sections parameter: {sections}. Using all sections.")
            sections = None
    
    crawler = SEOCrawlerTool()
    try:
        logger.info(f"Executing crawler with website_url={website_url}, max_pages={max_pages}, sections={sections}")
        result = crawler._run(website_url, max_pages=max_pages, sections=sections)
        
        visited_count = len(crawler.config.visited_urls)
        logger.info(f"Crawl completed. Visited {visited_count} pages out of max {max_pages}")
        
        # Create CrawlResult
        crawl_result = CrawlResult.objects.create(
            user_id=user_id,
            website_url=website_url,
            content=result["pages"],
            links_visited=list(crawler.config.visited_urls),
            total_links=result["total_links"],
            links_to_visit=list(crawler.config.found_links)
        )
        
        elapsed_time = time.time() - start_time
        logger.info(f"Crawl completed for {website_url} in {elapsed_time:.2f} seconds, created CrawlResult with ID {crawl_result.id}")
        return crawl_result.id
        
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(f"Error during crawl after {elapsed_time:.2f} seconds: {str(e)}", exc_info=True)
        return None
