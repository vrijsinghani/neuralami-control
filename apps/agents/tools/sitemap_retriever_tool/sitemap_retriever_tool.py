from typing import Type, Optional, List, Dict, Any, Set, ClassVar, Tuple, Callable
from pydantic import BaseModel, Field, field_validator
from crewai.tools import BaseTool
import json
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET
import csv
import io
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from requests.exceptions import RequestException, Timeout, ConnectionError
from time import time, sleep
import threading
from apps.agents.utils.get_targeted_keywords import get_targeted_keywords

logger = logging.getLogger(__name__)

class SitemapRetrieverSchema(BaseModel):
    """Input schema for SitemapRetriever."""
    url: str = Field(
        ...,
        description="The URL of the website to retrieve or generate a sitemap for"
    )
    max_pages: int = Field(
        50,
        description="Maximum number of pages to crawl when generating a sitemap"
    )
    user_id: int = Field(
        ..., 
        description="ID of the user initiating the sitemap retrieval"
    )
    output_format: str = Field(
        "json",
        description="Format to output results in - 'json' or 'csv'"
    )
    requests_per_second: float = Field(
        5.0,
        description="Maximum number of requests to make per second (rate limit)"
    )
    
    @field_validator('url')
    def validate_url(cls, v):
        if not v.startswith(('http://', 'https://')):
            raise ValueError("URL must start with http:// or https://")
        return v
    
    @field_validator('output_format')
    def validate_output_format(cls, v):
        if v.lower() not in ["json", "csv"]:
            raise ValueError("output_format must be either 'json' or 'csv'")
        return v.lower()
    
    @field_validator('requests_per_second')
    def validate_requests_per_second(cls, v):
        if v <= 0:
            raise ValueError("requests_per_second must be greater than 0")
        return v
    
    model_config = {
        "arbitrary_types_allowed": True,
        "extra": "forbid"
    }

class SitemapRetrieverTool(BaseTool):
    name: str = "Sitemap Retriever Tool"
    description: str = """
    A tool that retrieves or generates a sitemap (including targeted keywords, meta description, and H1 and H2 headers) for a given URL.
    It first tries to find an existing sitemap.xml file. If not found,
    it crawls the website to generate a sitemap of internal links.
    Results can be output in JSON or CSV format.
    """
    args_schema: Type[BaseModel] = SitemapRetrieverSchema
    
    # Constants for optimization (with proper ClassVar type annotations)
    TIMEOUT: ClassVar[int] = 10
    MAX_WORKERS: ClassVar[int] = 5
    COMMON_SITEMAP_PATHS: ClassVar[List[str]] = [
        "sitemap.xml",          # Standard sitemap location
        "sitemap_index.xml",    # Common WordPress/RankMath/Yoast index
        "sitemap/",             # Sitemap directory
        "sitemap1.xml",         # Numbered sitemap
        "post-sitemap.xml",     # Content type specific sitemap (WordPress/RankMath)
        "page-sitemap.xml",     # Content type specific sitemap (WordPress/RankMath)
        "category-sitemap.xml", # Category specific sitemap (WordPress/RankMath)
        "sitemapindex.xml",     # Alternative index naming
        "sitemap-index.xml",    # Alternative index naming with hyphen
        "sitemap.php",          # Dynamic sitemap
        "sitemap.txt"           # Text-based sitemap
    ]
    
    # Rate limiting parameters
    _rate_limiter_lock: ClassVar[threading.Lock] = threading.Lock()
    _last_request_time: ClassVar[Dict[str, float]] = {}
    _domain_request_counts: ClassVar[Dict[str, int]] = {}
    _request_timestamps: ClassVar[Dict[str, List[float]]] = {}
    _current_rate_limit: ClassVar[float] = 5.0  # Default rate limit

    def _run(self, url: str, user_id: int, max_pages: int = 50, output_format: str = "json", requests_per_second: float = 5.0) -> str:
        """
        Main execution method that retrieves sitemap data or crawls a website.
        Returns formatted data in JSON or CSV format.
        """
        start_time = time()
        try:
            logger.info(f"Attempting to retrieve sitemap for {url} (User ID: {user_id}) with rate limit of {requests_per_second} req/s and max_pages={max_pages}")
            
            # Store the rate limit as a class variable instead of an instance attribute
            with self._rate_limiter_lock:
                self.__class__._current_rate_limit = requests_per_second
            
            # Initialize rate limiting for this domain
            domain = urlparse(url).netloc
            self._init_rate_limiting(domain)
            
            # Normalize URL by removing trailing slash if present
            base_url = url.rstrip('/')
            
            # For max_pages=1, just process the given URL directly without looking for a sitemap
            if max_pages == 1:
                logger.info(f"max_pages=1, processing only the provided URL: {base_url}")
                # Create a single entry for the given URL with metadata
                single_url_data = self._process_url(base_url, urlparse(base_url).netloc)[0]
                if single_url_data:
                    result_data = {
                        "success": True,
                        "method": "single_url",
                        "url_count": 1,
                        "urls": [single_url_data]
                    }
                    logger.info(f"Successfully processed single URL in {time() - start_time:.2f}s")
                    return self._format_output(result_data, output_format)
                else:
                    logger.warning(f"Failed to process URL: {base_url}, falling back to crawling")
            
            # Try to get sitemaps using standard methods (only if max_pages > 1)
            sitemap_urls = self._find_sitemap_urls(base_url)
            
            if sitemap_urls:
                logger.info(f"Found {len(sitemap_urls)} potential sitemap URL(s) for {url}")
                # Parse sitemaps and extract URLs, respecting max_pages
                url_entries = self._parse_sitemaps(sitemap_urls, max_pages)
                
                # Only consider sitemap valid if it contains actual URLs
                if url_entries:
                    result_data = {
                        "success": True,
                        "method": "existing_sitemap",
                        "sitemap_urls": sitemap_urls,
                        "url_count": len(url_entries),
                        "urls": url_entries
                    }
                    logger.info(f"Successfully extracted {len(url_entries)} URLs from sitemaps in {time() - start_time:.2f}s")
                    return self._format_output(result_data, output_format)
                else:
                    logger.warning(f"Found sitemap files but couldn't extract any valid URLs - falling back to crawling")
            
            # If no valid sitemap found or no URLs extracted, generate one by crawling
            logger.info(f"No valid sitemap found for {url}, generating by crawling")
            crawled_urls = self._crawl_website(base_url, max_pages)
            
            result_data = {
                "success": True,
                "method": "generated",
                "url_count": len(crawled_urls),
                "urls": crawled_urls
            }
            logger.info(f"Successfully crawled {len(crawled_urls)} URLs in {time() - start_time:.2f}s")
            return self._format_output(result_data, output_format)
            
        except Exception as e:
            logger.error(f"Error in SitemapRetrieverTool: {str(e)}", exc_info=True)
            result_data = {
                "success": False,
                "error": "Operation failed",
                "message": str(e),
                "execution_time": f"{time() - start_time:.2f}s"
            }
            return self._format_output(result_data, output_format)
    
    def _init_rate_limiting(self, domain: str) -> None:
        """Initialize rate limiting for a domain."""
        with self._rate_limiter_lock:
            if domain not in self._last_request_time:
                self._last_request_time[domain] = 0
            if domain not in self._domain_request_counts:
                self._domain_request_counts[domain] = 0
            if domain not in self._request_timestamps:
                self._request_timestamps[domain] = []
    
    def _apply_rate_limit(self, domain: str) -> None:
        """
        Apply rate limiting for requests to a specific domain.
        Uses a sliding window approach to maintain the specified requests per second.
        """
        with self._rate_limiter_lock:
            current_time = time()
            
            # Update request timestamps list for this domain
            self._request_timestamps[domain].append(current_time)
            
            # Remove timestamps older than 1 second
            cutoff_time = current_time - 1.0
            while self._request_timestamps[domain] and self._request_timestamps[domain][0] < cutoff_time:
                self._request_timestamps[domain].pop(0)
            
            # Calculate current requests per second
            requests_in_last_second = len(self._request_timestamps[domain])
            
            # Get current rate limit value
            current_rate_limit = self.__class__._current_rate_limit
            
            # If we're making too many requests per second, sleep to enforce the rate limit
            if requests_in_last_second > current_rate_limit:
                # Calculate sleep time based on how much we're over the limit
                sleep_time = (1.0 / current_rate_limit) * (requests_in_last_second - current_rate_limit)
                logger.debug(f"Rate limiting: sleeping for {sleep_time:.4f}s for domain {domain}")
                sleep(sleep_time)
    
    def _format_output(self, data: Dict[str, Any], output_format: str) -> str:
        """Format output data according to the specified format (json or csv)."""
        if output_format == "json":
            return json.dumps(data, indent=2)
        
        elif output_format == "csv":
            output = io.StringIO()
            csv_writer = csv.writer(output)
            
            # Handle different result types
            if not data.get("success", False):
                # Error case
                csv_writer.writerow(["success", "error", "message"])
                csv_writer.writerow([data.get("success", False), 
                                    data.get("error", ""), 
                                    data.get("message", "")])
                return output.getvalue()
            
            # First write summary row
            if data.get("method") == "existing_sitemap":
                csv_writer.writerow(["success", "method", "url_count", "sitemap_count"])
                csv_writer.writerow([data.get("success", True), 
                                    data.get("method", ""), 
                                    data.get("url_count", 0),
                                    len(data.get("sitemap_urls", []))])
            else:  # generated method
                csv_writer.writerow(["success", "method", "url_count"])
                csv_writer.writerow([data.get("success", True), 
                                    data.get("method", ""), 
                                    data.get("url_count", 0)])
            
            # Add a blank row as separator
            csv_writer.writerow([])
            
            # Write the URLs data
            urls = data.get("urls", [])
            if urls:
                # Get all possible fields from the first 100 URL entries
                sample_urls = urls[:100]
                all_fields = set()
                for url_data in sample_urls:
                    all_fields.update(url_data.keys())
                
                # Prioritize standard sitemap fields
                standard_fields = ["loc", "lastmod", "changefreq", "priority", "status_code"]
                header_fields = [f for f in standard_fields if f in all_fields]
                # Add any remaining fields
                header_fields.extend([f for f in all_fields if f not in standard_fields])
                
                # Write header row
                csv_writer.writerow(header_fields)
                
                # Write data rows
                for url_data in urls:
                    # Process each field, handling special cases like lists
                    row = []
                    for field in header_fields:
                        value = url_data.get(field, "")
                        
                        # Special handling for targeted_keywords which is a list
                        if field == "targeted_keywords" and isinstance(value, list):
                            # Join keywords with pipe character to avoid CSV delimiter conflicts
                            value = "|".join(value)
                        
                        row.append(value)
                    
                    csv_writer.writerow(row)
            
            return output.getvalue()
        
        # Fallback to JSON if format is invalid (should be prevented by validator)
        logger.warning(f"Invalid output format '{output_format}', falling back to JSON")
        return json.dumps(data, indent=2)

    # Helper function to fetch a URL, with caching for efficiency
    def fetch_url(self, url: str) -> Dict[str, Any]:
        """
        Fetch a URL and return its content with metadata.
        Applies rate limiting to respect target servers.
        """
        domain = urlparse(url).netloc
        self._init_rate_limiting(domain)
        self._apply_rate_limit(domain)
        
        try:
            logger.debug(f"Fetching: {url}")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xml,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0'
            }
            response = requests.get(url, timeout=self.TIMEOUT, allow_redirects=True, headers=headers)
            logger.debug(f"Response for {url}: status={response.status_code}, content-type={response.headers.get('Content-Type', '')}")
            return {
                "status_code": response.status_code,
                "content": response.text,
                "content_type": response.headers.get('Content-Type', '').lower(),
                "success": response.status_code == 200
            }
        except (RequestException, Timeout, ConnectionError) as e:
            logger.debug(f"Error fetching {url}: {str(e)}")
            return {
                "status_code": 0,
                "content": "",
                "content_type": "",
                "success": False,
                "error": str(e)
            }

    def _find_sitemap_urls(self, base_url: str) -> List[str]:
        """Try to locate sitemap URLs through common methods."""
        sitemap_urls = set()
        
        # Determine alternate protocol URL to try if the first one fails
        parsed_url = urlparse(base_url)
        alt_protocol = "https" if parsed_url.scheme == "http" else "http"
        alt_base_url = f"{alt_protocol}://{parsed_url.netloc}{parsed_url.path}".rstrip('/')
        logger.debug(f"Original base URL: {base_url}, alternate protocol URL: {alt_base_url}")
        
        # Create work queue of URLs to check
        work_queue = []
        
        # Add sitemap URL checks to work queue
        for path in self.COMMON_SITEMAP_PATHS:
            # Original protocol
            work_queue.append((urljoin(base_url, path), 'sitemap'))
            
            # Alternate protocol
            work_queue.append((urljoin(alt_base_url, path), 'sitemap'))
        
        # Add robots.txt checks to work queue
        work_queue.append((urljoin(base_url, "robots.txt"), 'robots'))
        work_queue.append((urljoin(alt_base_url, "robots.txt"), 'robots'))
        
        # Process URLs in parallel using threads
        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            # Instead of submitting instance methods, use a simpler approach with a lambda
            # that doesn't require the instance to be hashable
            future_to_url = {}
            for url, check_type in work_queue:
                if check_type == 'sitemap':
                    future = executor.submit(self._check_single_sitemap, url)
                else:  # robots.txt
                    future = executor.submit(self._check_single_robots, url)
                future_to_url[future] = url
            
            # Collect results
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    # Get any found sitemap URLs from this check
                    found_urls = future.result()
                    if found_urls:
                        sitemap_urls.update(found_urls)
                except Exception as e:
                    logger.error(f"Error checking {url}: {str(e)}")
        
        logger.info(f"Found {len(sitemap_urls)} sitemap URLs: {sitemap_urls}")
        return list(sitemap_urls)

    def _check_single_sitemap(self, sitemap_url: str) -> Set[str]:
        """Check if a URL contains a valid sitemap and return any found sitemap URLs."""
        found_urls = set()
        response_data = self.fetch_url(sitemap_url)
        
        # Always attempt to process content if it's a sitemap URL, even if status is not 200
        # This helps with sites that return 403 but still serve content or redirects
        is_sitemap_url = 'sitemap' in sitemap_url.lower() and sitemap_url.endswith(('.xml', '.txt'))
        
        if not response_data["success"] and not is_sitemap_url:
            return found_urls
                
        content_type = response_data["content_type"]
        content_text = response_data["content"]
        
        # Skip empty responses completely
        if not content_text:
            return found_urls
        
        # HTML content may contain links to XML sitemaps
        if 'text/html' in content_type and sitemap_url.endswith('/'):
            soup = BeautifulSoup(content_text, 'html.parser')
            for link in soup.find_all('a', href=True):
                href = link['href']
                if href.endswith('.xml') and 'sitemap' in href.lower():
                    xml_url = urljoin(sitemap_url, href)
                    logger.debug(f"Found XML sitemap link in directory: {xml_url}")
                    found_urls.add(xml_url)
        
        # Accept as sitemap if it looks like XML with sitemap content
        elif any(indicator in content_text.lower() for indicator in [
                '<urlset', '<sitemapindex', '<?xml', '<loc>', '</loc>'
            ]) or any(xml_type in content_type for xml_type in [
                'xml', 'application/xml', 'text/xml'
            ]):
            
            logger.debug(f"Found potential sitemap: {sitemap_url}")
            found_urls.add(sitemap_url)
            
            # Try to extract child sitemap URLs directly
            if '<sitemapindex' in content_text or any(path in sitemap_url.lower() for path in 
                                                    ['sitemap_index', 'sitemapindex', 'sitemap-index']):
                # First try standard XML format with <loc> tags
                child_urls = re.findall(r'<loc>(.*?)</loc>', content_text)
                
                # If no URLs found with standard format, try extracting URLs directly
                if not child_urls:
                    # Extract any URLs that end with .xml
                    child_urls = re.findall(r'(https?://[^\s<>"\']+\.xml)', content_text)
                
                for child_url in child_urls:
                    child_url = child_url.strip()
                    if child_url.endswith('.xml'):
                        logger.debug(f"Found child sitemap in index: {child_url}")
                        found_urls.add(child_url)
        
        # Check for text-based sitemap index even if not XML
        elif 'sitemap' in sitemap_url.lower() and sitemap_url.endswith(('.xml', '.txt')):
            # For any sitemap-looking URL, try extracting embedded sitemap URLs
            xml_urls = re.findall(r'(https?://[^\s<>"\']+\.xml)', content_text)
            if xml_urls:
                logger.debug(f"Found plain text sitemap index at {sitemap_url}")
                for xml_url in xml_urls:
                    xml_url = xml_url.strip()
                    logger.debug(f"Found sitemap URL in plain text: {xml_url}")
                    found_urls.add(xml_url)
                
                # Also add the original sitemap if we found child sitemaps
                if xml_urls:
                    found_urls.add(sitemap_url)
        
        return found_urls

    def _check_single_robots(self, robots_url: str) -> Set[str]:
        """Check robots.txt for Sitemap directives."""
        found_urls = set()
        response_data = self.fetch_url(robots_url)
        
        if not response_data["success"]:
            return found_urls
            
        for line in response_data["content"].splitlines():
            if line.lower().startswith("sitemap:"):
                sitemap_url = line.split(":", 1)[1].strip()
                logger.debug(f"Found sitemap in robots.txt: {sitemap_url}")
                found_urls.add(sitemap_url)
        
        return found_urls

    def _parse_sitemaps(self, sitemap_urls: List[str], max_pages: int = None) -> List[Dict[str, Any]]:
        """Parse sitemap XML files to extract URLs and metadata."""
        all_urls = []
        processed_urls = set()  # Keep track of processed sitemap files
        processed_locs = set()  # Keep track of processed location URLs to avoid duplicates
        
        for sitemap_url in sitemap_urls:
            # Skip if already processed this URL
            if sitemap_url in processed_urls:
                continue
            processed_urls.add(sitemap_url)
            
            # If we've reached max_pages, stop processing more URLs
            if max_pages is not None and len(all_urls) >= max_pages:
                logger.info(f"Reached max_pages limit ({max_pages}), stopping sitemap parsing")
                break
            
            try:
                response_data = self.fetch_url(sitemap_url)
                if not response_data["success"]:
                    logger.warning(f"Failed to fetch sitemap {sitemap_url}: HTTP {response_data['status_code']}")
                    # Try to process the content even with non-200 status codes
                    if not response_data["content"]:
                        continue
                    logger.debug(f"Attempting to process sitemap content despite status code {response_data['status_code']}")
                
                content = response_data["content"]
                
                # Try to detect if this is a sitemap index
                is_sitemap_index = (
                    "sitemapindex" in sitemap_url.lower() or
                    "sitemap-index" in sitemap_url.lower() or
                    "sitemap_index" in sitemap_url.lower() or
                    "<sitemapindex" in content
                )
                
                if is_sitemap_index:
                    # This is a sitemap index, find all child sitemaps
                    logger.debug(f"Processing sitemap index: {sitemap_url}")
                    
                    # First try standard XML format
                    child_urls = re.findall(r'<loc>(.*?)</loc>', content)
                    
                    # If no standard child URLs found, try extracting URLs directly
                    if not child_urls:
                        logger.debug(f"No standard <loc> tags found in sitemap index, trying direct URL extraction")
                        child_urls = re.findall(r'(https?://[^\s<>"\']+\.xml)', content)
                        
                    if child_urls:
                        logger.debug(f"Found {len(child_urls)} child sitemaps in {sitemap_url}")
                        # Process each child sitemap
                        child_url_batch = []
                        for child_url in child_urls:
                            child_url = child_url.strip()
                            if child_url not in processed_urls:
                                processed_urls.add(child_url)
                                child_url_batch.append(child_url)
                        
                        # Process child sitemaps and collect results, respecting max_pages
                        if child_url_batch:
                            # Calculate how many more URLs we can process
                            remaining_pages = None if max_pages is None else max_pages - len(all_urls)
                            if remaining_pages is not None and remaining_pages <= 0:
                                # If we've already hit the limit, don't process more
                                continue
                                
                            child_results = self._parse_sitemaps(child_url_batch, remaining_pages) 
                            # Only add URLs that we haven't seen before
                            for url_data in child_results:
                                if "loc" in url_data and url_data["loc"] not in processed_locs:
                                    processed_locs.add(url_data["loc"])
                                    all_urls.append(url_data)
                            
                            # Check if we've hit max_pages after processing child sitemaps
                            if max_pages is not None and len(all_urls) >= max_pages:
                                logger.info(f"Reached max_pages limit ({max_pages}) after processing child sitemaps")
                                break
                    else:
                        # If we can't find any child sitemaps, treat it as a regular sitemap
                        logger.debug(f"No child sitemaps found in sitemap index, treating as regular sitemap")
                        is_sitemap_index = False
                
                # Process as a regular sitemap
                if not is_sitemap_index:
                    # First collect all URLs from the sitemap without meta descriptions
                    sitemap_urls_data = []
                    
                    # Extract URLs using standard <url> tags
                    url_elements = re.findall(r'<url>(.*?)</url>', content, re.DOTALL)
                    
                    if url_elements:
                        for url_element in url_elements:
                            # If we've reached max_pages, stop processing more URLs
                            if max_pages is not None and len(all_urls) + len(sitemap_urls_data) >= max_pages:
                                logger.debug(f"Reached max_pages limit ({max_pages}) during sitemap URL extraction")
                                break
                                
                            url_data = {}
                            
                            # Extract standard fields
                            loc_match = re.search(r'<loc>(.*?)</loc>', url_element)
                            if loc_match:
                                url = loc_match.group(1).strip()
                                # Skip if we've already processed this URL
                                if url in processed_locs:
                                    continue
                                processed_locs.add(url)
                                url_data["loc"] = url
                                
                                # Extract other standard sitemap fields
                                for field in ["lastmod", "changefreq", "priority"]:
                                    field_match = re.search(f'<{field}>(.*?)</{field}>', url_element)
                                    if field_match:
                                        url_data[field] = field_match.group(1).strip()
                                
                                sitemap_urls_data.append(url_data)
                    else:
                        # If no <url> tags found, try looking for <loc> tags directly
                        loc_matches = re.findall(r'<loc>(.*?)</loc>', content)
                        if loc_matches:
                            for loc in loc_matches:
                                url = loc.strip()
                                # Skip if we've already processed this URL
                                if url in processed_locs:
                                    continue
                                processed_locs.add(url)
                                sitemap_urls_data.append({"loc": url})
                        else:
                            # Handle text-based sitemaps or malformed XML
                            extracted_urls = []
                            
                            # Try line by line for text sitemaps
                            for line in content.splitlines():
                                line = line.strip()
                                if line and line.startswith(('http://', 'https://')):
                                    urls_in_line = re.findall(r'(https?://[^\s<>"\']+)', line)
                                    extracted_urls.extend(urls_in_line)
                            
                            # If that didn't work, use regex to find all URLs
                            if not extracted_urls:
                                extracted_urls = re.findall(r'https?://[^\s<>"\']+\.[a-zA-Z]{2,}', content)
                            
                            # Deduplicate and filter URLs
                            for url in set(extracted_urls):
                                url = url.strip()
                                # Filter out non-HTML URLs and common sitemap XML URLs
                                if not url.endswith(('.jpg', '.jpeg', '.png', '.gif', '.css', '.js')) and not any(
                                    url.endswith(path) for path in [
                                    '/post-sitemap.xml', '/page-sitemap.xml', '/category-sitemap.xml'
                                    ]):
                                    # Special handling for URLs that were part of a sitemap index
                                    if "sitemap" in sitemap_url.lower() and url.endswith(".xml"):
                                        # This is likely a child sitemap URL, process it separately
                                        if url not in processed_urls:
                                            processed_urls.add(url)
                                            logger.debug(f"Found child sitemap URL in text content: {url}")
                                            child_results = self._parse_sitemaps([url], max_pages)
                                            # Only add URLs that we haven't seen before
                                            for url_data in child_results:
                                                if "loc" in url_data and url_data["loc"] not in processed_locs:
                                                    processed_locs.add(url_data["loc"])
                                                    all_urls.append(url_data)
                                    else:
                                        # Skip if we've already processed this URL
                                        if url in processed_locs:
                                            continue
                                        processed_locs.add(url)
                                        # Regular URL for the sitemap
                                        sitemap_urls_data.append({"loc": url})
                    
                    # Only fetch meta descriptions if we found URLs
                    if sitemap_urls_data:
                        # Fetch meta descriptions in parallel
                        meta_descriptions = self._fetch_meta_descriptions_parallel(sitemap_urls_data)
                        
                        # Add meta descriptions to URL data and add to results
                        for url_data in sitemap_urls_data:
                            url = url_data["loc"]
                            if url in meta_descriptions:
                                meta_data = meta_descriptions[url]
                                
                                # Add meta description if available
                                if "meta_description" in meta_data:
                                    url_data["meta_description"] = meta_data["meta_description"]
                                
                                # Add targeted keywords if available
                                if "targeted_keywords" in meta_data:
                                    url_data["targeted_keywords"] = meta_data["targeted_keywords"]
                            
                            all_urls.append(url_data)
                            
                            # Check if we've hit max_pages after adding each URL
                            if max_pages is not None and len(all_urls) >= max_pages:
                                logger.info(f"Reached max_pages limit ({max_pages}) during meta description processing")
                                break
            
            except Exception as e:
                logger.error(f"Error processing sitemap {sitemap_url}: {str(e)}")
        
        logger.info(f"Total URLs found across all sitemaps: {len(all_urls)}, unique URLs: {len(processed_locs)}")
        return all_urls
    
    def _fetch_meta_descriptions_parallel(self, urls_data: List[Dict[str, Any]], batch_size: int = 100) -> Dict[str, Dict[str, Any]]:
        """
        Fetch meta descriptions for multiple URLs in parallel with rate limiting.
        Returns a dictionary mapping URLs to their metadata.
        """
        logger.info(f"Fetching meta descriptions for {len(urls_data)} URLs in parallel")
        
        # Process URLs in batches to avoid creating too many threads
        results = {}
        for i in range(0, len(urls_data), batch_size):
            batch = urls_data[i:i+batch_size]
            logger.info(f"Processing batch {i//batch_size + 1} with {len(batch)} URLs")
            
            # Adjust number of workers based on rate limit
            current_rate_limit = self.__class__._current_rate_limit
            effective_workers = min(self.MAX_WORKERS, max(1, int(current_rate_limit)))
            
            with ThreadPoolExecutor(max_workers=effective_workers) as executor:
                # Map URLs to futures
                future_to_url_data = {
                    executor.submit(self._extract_meta_and_keywords, url_data["loc"]): url_data 
                    for url_data in batch
                }
                
                # Process completed futures
                for future in as_completed(future_to_url_data):
                    url_data = future_to_url_data[future]
                    url = url_data["loc"]
                    try:
                        meta_data = future.result()
                        # Store result in dictionary by URL
                        results[url] = meta_data
                    except Exception as e:
                        logger.error(f"Error extracting data for {url}: {str(e)}")
                        # Store empty result to avoid errors
                        results[url] = {}
            
            # Add a small delay between batches for better rate control
            if i + batch_size < len(urls_data):
                current_rate_limit = self.__class__._current_rate_limit
                delay = 0.5 / current_rate_limit  # Adjust based on rate limit
                logger.debug(f"Pausing between batches for {delay:.2f}s to respect rate limits")
                sleep(delay)
        
        logger.info(f"Completed fetching metadata. Found descriptions for {sum(1 for u, d in results.items() if 'meta_description' in d)} URLs and keywords for {sum(1 for u, d in results.items() if 'targeted_keywords' in d)} URLs")
        return results

    def _extract_meta_and_keywords(self, url: str) -> Dict[str, Any]:
        """Extract meta description and targeted keywords from a URL."""
        try:
            response = self.fetch_url(url)
            if not response or not response["success"]:
                return {}
            
            result = {}
            html_content = response["content"]
            
            # Extract meta description
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Try standard meta description
            meta_tag = soup.find('meta', attrs={'name': 'description'})
            if meta_tag and meta_tag.get('content'):
                result["meta_description"] = meta_tag.get('content')[:500]  # Truncate long descriptions
            else:
                # Try Open Graph description
                og_tag = soup.find('meta', attrs={'property': 'og:description'})
                if og_tag and og_tag.get('content'):
                    result["meta_description"] = og_tag.get('content')[:500]
            
            # Extract targeted keywords
            try:
                keywords = get_targeted_keywords(html_content, top_n=10)
                if keywords:
                    result["targeted_keywords"] = keywords
            except Exception as e:
                logger.error(f"Error extracting targeted keywords from {url}: {str(e)}")
            
            return result
        except Exception as e:
            logger.error(f"Error extracting meta and keywords from {url}: {str(e)}")
            return {}

    def _crawl_website(self, base_url: str, max_pages: int) -> List[Dict[str, Any]]:
        """Crawl a website to generate a sitemap."""
        visited_urls = set()  # URLs we've already visited
        to_visit = [base_url]
        results = []
        base_domain = urlparse(base_url).netloc
        
        # Store a set of URLs we've already queued to visit
        queued = set(to_visit)
        
        # Track URLs we've already added to results to avoid duplicates
        result_urls = set()
        
        logger.info(f"Starting crawl of {base_url} with max_pages={max_pages}")
        
        while to_visit and len(visited_urls) < max_pages:
            # Calculate how many URLs we can process in this batch
            remaining = max_pages - len(visited_urls)
            if remaining <= 0:
                break
                
            # Process URLs in batches
            batch_size = min(self.MAX_WORKERS, len(to_visit), remaining)
            batch = [to_visit.pop(0) for _ in range(batch_size) if to_visit]
            
            # Skip URLs we've already visited
            batch = [url for url in batch if url not in visited_urls]
            if not batch:
                continue
            
            # Mark batch URLs as visited to prevent duplicates
            for url in batch:
                visited_urls.add(url)
            
            # Process batch in parallel
            batch_results, new_urls = self._process_url_batch(batch, base_domain)
            
            # Add only unique results
            for result in batch_results:
                if "loc" in result and result["loc"] not in result_urls:
                    result_urls.add(result["loc"])
                    results.append(result)
            
            # Add new URLs to the queue
            for new_url in new_urls:
                if (new_url not in visited_urls and 
                    new_url not in queued and 
                    len(queued) < max_pages * 2):  # Limit queue size
                    to_visit.append(new_url)
                    queued.add(new_url)
        
        logger.info(f"Crawl complete. Visited {len(visited_urls)} URLs, found {len(results)} unique results.")
        return results
        
    def _process_url_batch(self, urls: List[str], base_domain: str) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Process a batch of URLs in parallel with rate limiting.
        This method uses a reduced number of workers if the rate limit is low.
        """
        batch_results = []
        all_new_urls = []
        
        # Adjust number of workers based on rate limit to avoid excessive rate limiting
        current_rate_limit = self.__class__._current_rate_limit
        effective_workers = min(self.MAX_WORKERS, max(1, int(current_rate_limit)))
        
        # Use ThreadPoolExecutor for parallel processing
        with ThreadPoolExecutor(max_workers=effective_workers) as executor:
            # Create a future-to-url mapping
            future_to_url = {executor.submit(self._process_url, url, base_domain): url for url in urls}
            
            # Process completed futures
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    # Get result and new URLs from processing this URL
                    result, new_urls = future.result()
                    if result:
                        batch_results.append(result)
                    all_new_urls.extend(new_urls)
                except Exception as e:
                    logger.error(f"Error processing URL {url}: {str(e)}")
                    batch_results.append({
                        "loc": url,
                        "error": str(e)
                    })
        
        return batch_results, all_new_urls

    def _process_url(self, url: str, base_domain: str) -> Tuple[Dict[str, Any], List[str]]:
        """Process a single URL during crawling."""
        new_urls = []
        
        try:
            response_data = self.fetch_url(url)
            
            # Create result regardless of status
            result = {
                "loc": url,
                "status_code": response_data["status_code"]
            }
            
            # Only extract links if this is a successful HTML page
            if (response_data["success"] and 
                'text/html' in response_data["content_type"]):
                
                # Extract meta description and targeted keywords
                if response_data["content"]:
                    soup = BeautifulSoup(response_data["content"], 'html.parser')
                    
                    # Look for meta description tag
                    meta_tag = soup.find('meta', attrs={'name': 'description'})
                    if meta_tag and meta_tag.get('content'):
                        result["meta_description"] = meta_tag.get('content').strip()
                    else:
                        # Try Open Graph description as fallback
                        og_tag = soup.find('meta', attrs={'property': 'og:description'})
                        if og_tag and og_tag.get('content'):
                            result["meta_description"] = og_tag.get('content').strip()
                    
                    # Extract targeted keywords
                    try:
                        keywords = get_targeted_keywords(response_data["content"], top_n=10)
                        if keywords:
                            result["targeted_keywords"] = keywords
                    except Exception as e:
                        logger.error(f"Error extracting targeted keywords from {url}: {str(e)}")
                
                # Extract links from the page
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    
                    # Convert relative URLs to absolute
                    absolute_url = urljoin(url, href)
                    
                    # Only process internal links from the same domain
                    parsed_url = urlparse(absolute_url)
                    if (parsed_url.netloc == base_domain and 
                        parsed_url.scheme in ('http', 'https') and
                        '#' not in absolute_url):
                        new_urls.append(absolute_url)
            
            return result, new_urls
        
        except Exception as e:
            logger.debug(f"Error processing {url}: {str(e)}")
            return {"loc": url, "error": str(e)}, []