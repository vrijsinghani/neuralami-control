import logging
from typing import Optional, Dict, Any, Type
from pydantic import BaseModel, Field
from crewai_tools.tools.base_tool import BaseTool
from urllib.parse import urljoin, urlparse
from spider_rs import Website, Page
from trafilatura import extract


logger = logging.getLogger(__name__)

class CrawlWebsiteToolSchema(BaseModel):
    """Input for CrawlWebsiteTool."""
    website_url: str = Field(..., description="Mandatory website URL to crawl and read content")
    max_pages: int = Field(default=100, description="Maximum number of pages to crawl")

    model_config = {
        "extra": "forbid"
    }      

class CrawlWebsiteTool(BaseTool):
    name: str = "Crawl and Read Website Content"
    description: str = "A tool that can crawl a website and read its content, including content from internal links on the same page."
    args_schema: Type[BaseModel] = CrawlWebsiteToolSchema
    website_url: Optional[str] = None
    max_pages: int = 100
    
    def __init__(self, website_url: Optional[str] = None, max_pages: int = 100, **kwargs):
        super().__init__(**kwargs)
        self.max_pages = max_pages
        if website_url:
            self.website_url = website_url
            self.description = f"A tool to crawl {website_url} and read its content, including content from internal links."

    def _run(self, website_url: str = None, max_pages: int = None) -> dict:
        """Run the tool."""
        url = website_url or self.website_url
        if not url:
            raise ValueError("No website URL provided")
            
        self.max_pages = max_pages or self.max_pages
        logger.info(f"Starting crawl for URL: {url} with max_pages: {self.max_pages}")

        try:
            result = self.crawl_website(url)
            logger.info(f"Crawl completed. Total links: {result['total_links']}, Links visited: {len(result['links_visited'])}")
            return result
        except Exception as e:
            logger.error(f"Error during crawl: {e}")
            raise

    def crawl_website(self, url: str) -> Dict[str, Any]:
        """Crawl website and extract content."""
        website = Website(url)
        website.with_budget({"*": self.max_pages})  # Limit to max_pages
        website.with_respect_robots_txt(True)
        website.with_subdomains(False)  # Stick to the main domain
        website.with_tld(False)  # Don't crawl top-level domain
        website.with_delay(1)  # Be respectful with a 1-second delay between requests

        links_visited = set()
        content = ""

        # Use scrape() for consistency with async version
        website.scrape()
        pages = website.get_pages()
        total_links = len(pages)
        
        # Limit pages to max_pages
        pages = list(pages)[:self.max_pages]
        logger.info(f"Limited pages to {len(pages)} out of {total_links} total links")

        for page in pages:
            try:
                logger.info(f"Processing page: {page.url}")
                page_content = self._extract_content(page)
                if page_content:  # Only add to visited if we got content
                    links_visited.add(page.url)
                    content += f"---link: {page.url}\n{page_content}\n---page-end---\n"
            except Exception as e:
                logger.error(f"Error processing page {page.url}: {e}")
                continue

        logger.info(f"Crawl finished. Total links: {total_links}, Links visited: {len(links_visited)}")

        return {
            "content": content,
            "links_visited": list(links_visited),
            "total_links": total_links,
            "links_to_visit": list(set(page.url for page in pages) - links_visited)
        }

    def _extract_content(self, page: Page) -> str:
        try:
            html_content = page.content
            extracted_content = extract(html_content)
            logger.info(f"Extracted content length for {page.url}: {len(extracted_content) if extracted_content else 0}")
            return extracted_content if extracted_content else ""
        except Exception as e:
            logger.error(f"Error extracting content from {page.url}: {e}")
            return ""
