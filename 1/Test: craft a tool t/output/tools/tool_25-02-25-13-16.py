```python
from typing import Type, Optional
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
import json
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

class SitemapRetrieverSchema(BaseModel):
    """Input schema for SitemapRetriever tool."""
    url: str = Field(
        ...,
        description="The URL of the website to retrieve or generate a sitemap for"
    )
    max_pages: int = Field(
        100,
        description="Maximum number of pages to crawl if generating a sitemap"
    )
    depth: int = Field(
        2,
        description="Maximum depth to crawl if generating a sitemap"
    )

class SitemapRetrieverTool(BaseTool):
    name: str = "Sitemap Retriever Tool"
    description: str = """
    A tool to retrieve an existing sitemap from a website or generate one by crawling the site.
    This tool attempts to find standard sitemap files (sitemap.xml, sitemap_index.xml) and falls back
    to crawling the site to generate a sitemap if none is found.
    """
    args_schema: Type[BaseModel] = SitemapRetrieverSchema

    def _run(self, url: str, max_pages: int = 100, depth: int = 2) -> str:
        try:
            logger.info(f"Attempting to retrieve sitemap for {url}")
            
            # Normalize URL
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            # Remove trailing slash if present
            base_url = url.rstrip('/')
            
            # First try to find an existing sitemap
            sitemap_urls = self._find_sitemap(base_url)
            
            if sitemap_urls:
                # If sitemap exists, parse and return it
                return json.dumps({
                    "success": True,
                    "method": "existing_sitemap",
                    "sitemap_urls": sitemap_urls,
                    "urls": self._parse_sitemaps(sitemap_urls)
                })
            else:
                # If no sitemap found, generate one by crawling
                logger.info(f"No sitemap found for {url}, generating by crawling")
                crawled_urls = self._crawl_site(base_url, max_pages, depth)
                
                return json.dumps({
                    "success": True,
                    "method": "generated_by_crawling",
                    "urls": crawled_urls
                })
                
        except Exception as e:
            logger.error(f"Error in SitemapRetrieverTool: {str(e)}")
            return json.dumps({
                "success": False,
                "error": "Operation failed",
                "message": str(e)
            })
    
    def _find_sitemap(self, base_url: str) -> list:
        """Try to find existing sitemaps on the website."""
        sitemap_urls = []
        
        # Common sitemap locations
        sitemap_locations = [
            "/sitemap.xml",
            "/sitemap_index.xml",
            "/sitemap.php",
            "/sitemap.txt"
        ]
        
        # Check robots.txt for sitemap references
        try:
            robots_url = f"{base_url}/robots.txt"
            response = requests.get(robots_url, timeout=10)
            if response.status_code == 200:
                for line in response.text.splitlines():
                    if line.lower().startswith("sitemap:"):
                        sitemap_url = line.split(":", 1)[1].strip()
                        sitemap_urls.append(sitemap_url)
        except Exception as e:
            logger.warning(f"Error checking robots.txt: {str(e)}")
        
        # Check common sitemap locations
        for location in sitemap_locations:
            try:
                sitemap_url = base_url + location
                response = requests.get(sitemap_url, timeout=10)
                if response.status_code == 200:
                    sitemap_urls.append(sitemap_url)
            except Exception as e:
                logger.warning(f"Error checking {sitemap_url}: {str(e)}")
        
        return sitemap_urls
    
    def _parse_sitemaps(self, sitemap_urls: list) -> list:
        """Parse sitemap XML files to extract URLs."""
        all_urls = []
        
        for sitemap_url in sitemap_urls:
            try:
                response = requests.get(sitemap_url, timeout=10)
                if response.status_code == 200:
                    # Parse XML content
                    root = ET.fromstring(response.content)
                    
                    # Handle sitemap index files
                    if "sitemapindex" in root.tag:
                        # Extract child sitemap URLs
                        namespace = root.tag.split('}')[0] + '}' if '}' in root.tag else ''
                        for sitemap in root.findall(f".//{namespace}sitemap"):
                            loc = sitemap.find(f"{namespace}loc")
                            if loc is not None and loc.text:
                                child_urls = self._parse_sitemaps([loc.text])
                                all_urls.extend(child_urls)
                    else:
                        # Handle regular sitemap files
                        namespace = root.tag.split('}')[0] + '}' if '}' in root.tag else ''
                        for url in root.findall(f".//{namespace}url"):
                            loc = url.find(f"{namespace}loc")
                            if loc is not None and loc.text:
                                all_urls.append(loc.text)
            except Exception as e:
                logger.warning(f"Error parsing sitemap {sitemap_url}: {str(e)}")
        
        return all_urls
    
    def _crawl_site(self, base_url: str, max_pages: int = 100, max_depth: int = 2) -> list:
        """Crawl a website to generate a sitemap."""
        visited_urls = set()
        to_visit = [(base_url, 0)]  # (url, depth)
        crawled_urls = []
        base_domain = urlparse(base_url).netloc
        
        while to_visit and len(visited_urls) < max_pages:
            current_url, current_depth = to_visit.pop(0)
            
            if current_url in visited_urls:
                continue
                
            visited_urls.add(current_url)
            crawled_urls.append(current_url)
            
            # Don't crawl deeper than max_depth
            if current_depth >= max_depth:
                continue
                
            try:
                response = requests.get(current_url, timeout=10)
                if response.status_code == 200 and 'text/html' in response.headers.get('Content-Type', '