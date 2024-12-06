from typing import Optional, Type, Any, List

from embedchain.models.data_type import DataType
from pydantic.v1 import BaseModel, Field

from crewai_tools import RagTool

from tools.custom_browserless_loader import CustomBrowserlessLoader
from trafilatura import fetch_url, extract, sitemaps, spider

import os

class FixedCrawlWebsiteSearchToolSchema(BaseModel):
    """Input for CrawlWebsiteTool."""

    search_query: str = Field(
        ...,
        description = "Mandatory search query  you want to use to search a specific website and it's internal pages."
    )
    pass

class CrawlWebsiteSearchToolSchema(FixedCrawlWebsiteSearchToolSchema):
    """Input for CrawlWebsiteTool."""
    website: str = Field(
        ..., 
        description="Mandatory website url to crawl and read content")

class CrawlWebsiteSearchTool(RagTool):
    name: str = "Crawl and search website content"
    description: str = "A tool that can be used to crawl a website and read its content, including content from internal links on the same page."
    args_schema: Type[BaseModel] = CrawlWebsiteSearchToolSchema
    # website: Optional[str] = None
    # api_token: str = ""
    # base_url: str = ""

    def __init__(self, website: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        # self.api_token = os.environ.get("BROWSERLESS_API_KEY")
        # self.base_url = os.environ.get("BROWSERLESS_BASE_URL")
        if website is not None:
            self._crawl_website(website)
            self.description = f"A tool that can be used to crawl {website} and read its content, including content from internal links on the same page."
            self.args_schema = FixedCrawlWebsiteSearchToolSchema

    def add(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        kwargs["data_type"] = DataType.WEB_PAGE
        super().add(*args, **kwargs)

    def _crawl_website(self, url: str) -> str:
        links_to_visit = self._get_links_to_visit(url)
        print(f"Reading {len(links_to_visit)} pages.")
        for link in links_to_visit:
            try:
                self.add(link) # Assuming this is a method that adds the link to some data structure
            except Exception as e:
                print(f"Failed to read page at '{link}'. Error: {e}")

        
    def _get_links_to_visit(self, url: str) -> List[str]:
        sitemap_links = sitemaps.sitemap_search(url)
        # if sitemap_links:
        if 0:
            print(f"Found {len(sitemap_links)} pages from sitemap.")
            return sitemap_links
        else:
            _, known_urls = spider.focused_crawler(url, max_seen_urls=10, max_known_urls=50)
            print(f"Found {len(known_urls)} from crawling the website.")
            return list(known_urls)

    def _before_run(
        self,
        query: str,
        **kwargs: Any,
    ) -> Any:
        if "website" in kwargs:
            self.add(kwargs["website"])

    def _run(
        self,
        search_query: str,
        **kwargs: Any,
    )-> Any:
        return super()._run(query=search_query)