import requests
from bs4 import BeautifulSoup
from typing import Optional, Type, Any, List
from pydantic.v1 import BaseModel, Field
from crewai_tools import BaseTool
from urllib.parse import urljoin
from trafilatura import fetch_url, extract, sitemaps, spider

class FixedCrawlWebsiteToolSchema(BaseModel):
    """Input for CrawlWebsiteTool."""
    pass

class CrawlWebsiteToolSchema(FixedCrawlWebsiteToolSchema):
    """Input for CrawlWebsiteTool."""
    website_url: str = Field(..., description="Mandatory website url to crawl and read content")

class CrawlWebsiteTool(BaseTool):
    name: str = "Crawl and read website content"
    description: str = "A tool that can be used to crawl a website and read its content, including content from internal links on the same page."
    args_schema: Type[BaseModel] = CrawlWebsiteToolSchema
    website_url: Optional[str] = None
    headers: Optional[dict] = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://www.google.com/'
    }

    def __init__(self, website_url: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        if website_url is not None:
            self.website_url = website_url
            self.description = f"A tool that can be used to crawl {website_url} and read its content, including content from internal links on the same page."
            self.args_schema = FixedCrawlWebsiteToolSchema

    def _run(self, **kwargs: Any) -> str:
        website_url = kwargs.get('website_url', self.website_url)
        print(f"Processing {website_url}")
        content = self._crawl_website(website_url)
        return content

    def _crawl_website(self, url: str) -> str:
        links_to_visit = self._get_links_to_visit(url)
        content = ""
        print(f"Reading {len(links_to_visit)} pages.")
        for link in links_to_visit:
            page_content = self._fetch_and_extract_content(link)
            content += page_content
        
        return content

    def _get_links_to_visit(self, url: str) -> List[str]:
#        sitemap_links = sitemaps.sitemap_search(url)
        sitemap_links = []
        if sitemap_links:
            print(f"Found {len(sitemap_links)} pages from sitemap.")
            return sitemap_links
        else:
            _, known_urls = spider.focused_crawler(url, max_seen_urls=10, max_known_urls=1000)
            print(f"Found {len(known_urls)} from crawling the website.")
            return list(known_urls)

    def _fetch_and_extract_content(self, url: str) -> str:
        html_content = fetch_url(url)
        if html_content:
            extracted_content = f"---link: {url}\n{extract(html_content,url=url)}\n---page-end---\n"
            return extracted_content or ""
        else:
            return ""
