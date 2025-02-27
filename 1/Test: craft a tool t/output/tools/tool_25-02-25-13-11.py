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

class SitemapToolSchema(BaseModel):
    """Input schema for SitemapTool."""
    url: str = Field(
        ...,
        description="The URL of the website to retrieve or generate a sitemap for."
    )
    max_depth: Optional[int] = Field(
        2,
        description="Maximum depth to crawl when generating a sitemap (default: 2)."
    )
    max_urls: Optional[int] = Field(
        100,
        description="Maximum number of URLs to include in the generated sitemap (default: 100)."
    )

class SitemapTool(BaseTool):
    name: str = "Sitemap Tool"
    description: str = """
    A tool to retrieve or generate a sitemap for a given website URL.
    This tool first attempts to find an existing sitemap by checking common sitemap locations.
    If no sitemap is found, it will generate one by crawling the website up to the specified depth.
    """
    args_schema: Type[BaseModel] = SitemapToolSchema

    def _run(self, url: str, max_depth: int = 2, max_urls: int = 100) -> str:
        try:
            logger.debug(f"Attempting to retrieve sitemap for {url}")
            
            # Normalize the URL
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
                
            # First try to find an existing sitemap
            sitemap_urls = self._find_sitemap(url)
            
            if sitemap_urls:
                return json.dumps({
                    "success": True,
                    "method": "retrieved",
                    "urls": sitemap_urls
                })
            
            # If no sitemap found, generate one
            logger.debug(f"No sitemap found for {url}, generating one")
            generated_urls = self._generate_sitemap(url, max_depth, max_urls)
            
            return json.dumps({
                "success": True,
                "method": "generated",
                "urls": generated_urls
            })

        except Exception as e:
            logger.error(f"Error in SitemapTool: {str(e)}")
            return json.dumps({
                "success": False,
                "error": "Operation failed",
                "message": str(e)
            })

    def _find_sitemap(self, url: str) -> list:
        """Attempt to find an existing sitemap."""
        # Common sitemap locations
        sitemap_locations = [
            "/sitemap.xml",
            "/sitemap_index.xml",
            "/sitemap.txt",
            "/sitemap/sitemap.xml"
        ]
        
        # Check robots.txt for sitemap directive
        try:
            robots_url = urljoin(url, "/robots.txt")
            robots_response = requests.get(robots_url, timeout=10)
            if robots_response.status_code == 200:
                for line in robots_response.text.splitlines():
                    if line.lower().startswith("sitemap:"):
                        sitemap_url = line.split(":", 1)[1].strip()
                        sitemap_locations.insert(0, sitemap_url)
        except Exception as e:
            logger.warning(f"Error checking robots.txt: {str(e)}")
        
        # Try each potential sitemap location
        for location in sitemap_locations:
            try:
                sitemap_url = location if location.startswith(('http://', 'https://')) else urljoin(url, location)
                response = requests.get(sitemap_url, timeout=10)
                
                if response.status_code == 200:
                    content_type = response.headers.get('Content-Type', '')
                    
                    # XML sitemap
                    if 'xml' in content_type or sitemap_url.endswith('.xml'):
                        return self._parse_xml_sitemap(response.text)
                    
                    # Text sitemap
                    elif 'text/plain' in content_type or sitemap_url.endswith('.txt'):
                        return [line.strip() for line in response.text.splitlines() if line.strip()]
            
            except Exception as e:
                logger.warning(f"Error checking sitemap at {location}: {str(e)}")
                continue
                
        return []

    def _parse_xml_sitemap(self, xml_content: str) -> list:
        """Parse XML sitemap and extract URLs."""
        urls = []
        try:
            root = ET.fromstring(xml_content)
            
            # Handle sitemap index files
            namespace = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            
            # Check if this is a sitemap index
            sitemaps = root.findall('.//sm:sitemap/sm:loc', namespace)
            if sitemaps:
                # This is a sitemap index, we need to fetch each sitemap
                for sitemap in sitemaps:
                    try:
                        sitemap_url = sitemap.text
                        response = requests.get(sitemap_url, timeout=10)
                        if response.status_code == 200:
                            urls.extend(self._parse_xml_sitemap(response.text))
                    except Exception as e:
                        logger.warning(f"Error fetching sub-sitemap {sitemap.text}: {str(e)}")
            
            # Regular sitemap
            locations = root.findall('.//sm:url/sm:loc', namespace)
            if not locations:
                # Try without namespace
                locations = root.findall('.//url/loc')
            
            for loc in locations:
                if loc.text:
                    urls.append(loc.text)
                    
        except Exception as e:
            logger.error(f"Error parsing XML sitemap: {str(e)}")
            
        return urls

    def _generate_sitemap(self, start_url: str, max_depth: int = 2, max_urls: int = 100) -> list:
        """Generate a sitemap by crawling the website."""
        visited = set()
        to_visit = [(start_url, 0)]  # (url, depth)
        base_domain = urlparse(start_url).netloc
        
        while to_visit and len(visited) < max_urls:
            current_url, depth = to_visit.pop(0)
            
            if current_url in visited:
                continue
                
            visited.add(current_url)
            
            if depth >= max_depth:
                continue
                
            try:
                response = requests.get(current_url, timeout=10)
                if response.status_code != 200:
                    continue
                    
                soup = BeautifulSoup(response.text, 'html.parser')
                
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    full_url = urljoin(current_url, href)
                    
                    # Skip external links, fragments,