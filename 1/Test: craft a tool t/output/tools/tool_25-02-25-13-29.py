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
        description="The base URL of the website to retrieve or generate a sitemap for"
    )
    max_pages: Optional[int] = Field(
        50,
        description="Maximum number of pages to include when generating a sitemap (only used if sitemap needs to be generated)"
    )

class SitemapRetrieverTool(BaseTool):
    name: str = "Sitemap Retriever Tool"
    description: str = """
    A tool that retrieves the sitemap for a given website URL or generates one if not available.
    The tool first tries to fetch the sitemap.xml file directly, then checks robots.txt for sitemap references,
    and finally crawls the site to generate a basic sitemap if needed.
    """
    args_schema: Type[BaseModel] = SitemapRetrieverSchema

    def _run(self, url: str, max_pages: int = 50) -> str:
        try:
            # Normalize the URL
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            # Remove trailing slash if present
            if url.endswith('/'):
                url = url[:-1]
                
            logger.debug(f"Attempting to retrieve sitemap for {url}")
            
            # Method 1: Try to get sitemap.xml directly
            sitemap_urls = self._get_sitemap_from_sitemap_xml(url)
            
            # Method 2: If sitemap.xml not found, check robots.txt
            if not sitemap_urls:
                logger.debug(f"Sitemap.xml not found, checking robots.txt for {url}")
                sitemap_urls = self._get_sitemap_from_robots_txt(url)
            
            # Method 3: If still no sitemap, generate one by crawling
            if not sitemap_urls:
                logger.debug(f"No sitemap found, generating sitemap for {url}")
                sitemap_urls = self._generate_sitemap(url, max_pages)
            
            # Format the result
            result = {
                "success": True,
                "sitemap_url": None,
                "sitemap_entries": sitemap_urls,
                "count": len(sitemap_urls)
            }
            
            logger.debug(f"Successfully retrieved sitemap with {len(sitemap_urls)} entries")
            return json.dumps(result)
            
        except Exception as e:
            logger.error(f"Error in SitemapRetrieverTool: {str(e)}")
            return json.dumps({
                "success": False,
                "error": "Failed to retrieve or generate sitemap",
                "message": str(e)
            })

    def _get_sitemap_from_sitemap_xml(self, base_url: str) -> list:
        """Try to get sitemap directly from sitemap.xml"""
        try:
            sitemap_url = f"{base_url}/sitemap.xml"
            response = requests.get(sitemap_url, timeout=10)
            
            if response.status_code == 200:
                return self._parse_sitemap_xml(response.text)
            return []
        except Exception as e:
            logger.debug(f"Error fetching sitemap.xml: {str(e)}")
            return []
    
    def _parse_sitemap_xml(self, xml_content: str) -> list:
        """Parse sitemap XML content to extract URLs"""
        try:
            urls = []
            root = ET.fromstring(xml_content)
            
            # Handle standard sitemap
            namespace = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            for url_element in root.findall('.//sm:url/sm:loc', namespace):
                urls.append(url_element.text)
            
            # If this is a sitemap index, we need to process each sitemap
            if not urls:
                for sitemap_element in root.findall('.//sm:sitemap/sm:loc', namespace):
                    sitemap_url = sitemap_element.text
                    try:
                        response = requests.get(sitemap_url, timeout=10)
                        if response.status_code == 200:
                            urls.extend(self._parse_sitemap_xml(response.text))
                    except Exception as e:
                        logger.debug(f"Error fetching sub-sitemap {sitemap_url}: {str(e)}")
            
            return urls
        except ET.ParseError:
            logger.debug("XML parsing error, content might not be a valid sitemap")
            return []
    
    def _get_sitemap_from_robots_txt(self, base_url: str) -> list:
        """Try to get sitemap URL from robots.txt"""
        try:
            robots_url = f"{base_url}/robots.txt"
            response = requests.get(robots_url, timeout=10)
            
            if response.status_code == 200:
                sitemap_urls = []
                for line in response.text.splitlines():
                    if line.lower().startswith("sitemap:"):
                        sitemap_url = line.split(":", 1)[1].strip()
                        try:
                            sitemap_response = requests.get(sitemap_url, timeout=10)
                            if sitemap_response.status_code == 200:
                                sitemap_urls.extend(self._parse_sitemap_xml(sitemap_response.text))
                        except Exception as e:
                            logger.debug(f"Error fetching sitemap from robots.txt: {str(e)}")
                return sitemap_urls
            return []
        except Exception as e:
            logger.debug(f"Error fetching robots.txt: {str(e)}")
            return []
    
    def _generate_sitemap(self, base_url: str, max_pages: int) -> list:
        """Generate a sitemap by crawling the website"""
        visited = set()
        to_visit = [base_url]
        found_urls = []
        
        # Parse the base domain to avoid crawling external sites
        base_domain = urlparse(base_url).netloc
        
        while to_visit and len(found_urls) < max_pages:
            current_url = to_visit.pop(0)
            
            if current_url in visited:
                continue
                
            visited.add(current_url)
            
            try:
                response = requests.get(current_url, timeout=10)
                
                if response.status_code == 200 and 'text/html' in response.headers.get('Content-Type', ''):
                    found_urls.append(current_url)
                    
                    # Parse