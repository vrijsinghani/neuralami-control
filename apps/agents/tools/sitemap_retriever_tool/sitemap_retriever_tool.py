from typing import Type, Optional, List, Dict, Any, Set, ClassVar, Tuple, Callable
from pydantic import BaseModel, Field, validator
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
from time import time

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
    
    @validator('url')
    def validate_url(cls, v):
        if not v.startswith(('http://', 'https://')):
            raise ValueError("URL must start with http:// or https://")
        return v
    
    @validator('output_format')
    def validate_output_format(cls, v):
        if v.lower() not in ["json", "csv"]:
            raise ValueError("output_format must be either 'json' or 'csv'")
        return v.lower()
    
    model_config = {
        "extra": "forbid"
    }

class SitemapRetrieverTool(BaseTool):
    name: str = "Sitemap Retriever Tool"
    description: str = """
    A tool that retrieves or generates a sitemap for a given URL.
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

    def _run(self, url: str, user_id: int, max_pages: int = 50, output_format: str = "json") -> str:
        """
        Main execution method that retrieves sitemap data or crawls a website.
        Returns formatted data in JSON or CSV format.
        """
        start_time = time()
        try:
            logger.info(f"Attempting to retrieve sitemap for {url} (User ID: {user_id})")
            
            # Normalize URL by removing trailing slash if present
            base_url = url.rstrip('/')
            
            # Try to get sitemaps using standard methods
            sitemap_urls = self._find_sitemap_urls(base_url)
            
            if sitemap_urls:
                logger.info(f"Found {len(sitemap_urls)} potential sitemap URL(s) for {url}")
                # Parse sitemaps and extract URLs
                url_entries = self._parse_sitemaps(sitemap_urls)
                
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
                    row = [url_data.get(field, "") for field in header_fields]
                    csv_writer.writerow(row)
            
            return output.getvalue()
        
        # Fallback to JSON if format is invalid (should be prevented by validator)
        logger.warning(f"Invalid output format '{output_format}', falling back to JSON")
        return json.dumps(data, indent=2)

    # Helper function to fetch a URL, with caching for efficiency
    def fetch_url(self, url: str) -> Dict[str, Any]:
        """
        Fetch a URL and return its content with metadata.
        This version doesn't use caching to avoid the unhashable type error.
        """
        try:
            logger.debug(f"Fetching: {url}")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xml,application/xhtml+xml,text/plain'
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

    def _parse_sitemaps(self, sitemap_urls: List[str]) -> List[Dict[str, Any]]:
        """Parse sitemap XML files to extract URLs and metadata."""
        all_urls = []
        processed_urls = set()  # Keep track of processed URLs to avoid duplication
        
        for sitemap_url in sitemap_urls:
            # Skip if already processed this URL
            if sitemap_url in processed_urls:
                continue
            processed_urls.add(sitemap_url)
            
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
                        
                        # Process child sitemaps and collect results
                        if child_url_batch:
                            child_results = self._parse_sitemaps(child_url_batch) 
                            all_urls.extend(child_results)
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
                            url_data = {}
                            
                            # Extract standard fields
                            loc_match = re.search(r'<loc>(.*?)</loc>', url_element)
                            if loc_match:
                                url = loc_match.group(1).strip()
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
                                sitemap_urls_data.append({"loc": loc.strip()})
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
                                            child_results = self._parse_sitemaps([url])
                                            all_urls.extend(child_results)
                                    else:
                                        # Regular URL for the sitemap
                                        sitemap_urls_data.append({"loc": url})
                    
                    # Only fetch meta descriptions if we found URLs
                    if sitemap_urls_data:
                        # Fetch meta descriptions in parallel
                        meta_descriptions = self._fetch_meta_descriptions_parallel(sitemap_urls_data)
                        
                        # Add meta descriptions to URL data and add to results
                        for url_data in sitemap_urls_data:
                            url = url_data["loc"]
                            if url in meta_descriptions and meta_descriptions[url]:
                                url_data["meta_description"] = meta_descriptions[url]
                            all_urls.append(url_data)
                    
            except Exception as e:
                logger.error(f"Error processing sitemap {sitemap_url}: {str(e)}")
        
        logger.info(f"Total URLs found across all sitemaps: {len(all_urls)}")
        return all_urls
    
    def _fetch_meta_descriptions_parallel(self, urls_data: List[Dict[str, Any]], batch_size: int = 100) -> List[Dict[str, Any]]:
        """
        Fetch meta descriptions for multiple URLs in parallel.
        
        Args:
            urls_data: List of URL data dictionaries
            batch_size: Size of batches to process in parallel
            
        Returns:
            Updated list of URL data with meta descriptions
        """
        logger.info(f"Fetching meta descriptions for {len(urls_data)} URLs in parallel")
        
        # Process URLs in batches to avoid creating too many threads
        results = []
        for i in range(0, len(urls_data), batch_size):
            batch = urls_data[i:i+batch_size]
            logger.info(f"Processing batch {i//batch_size + 1} with {len(batch)} URLs")
            
            with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
                # Map URLs to futures
                future_to_url_data = {
                    executor.submit(self._extract_meta_description, url_data["loc"]): url_data 
                    for url_data in batch
                }
                
                # Process completed futures
                for future in as_completed(future_to_url_data):
                    url_data = future_to_url_data[future]
                    try:
                        meta_description = future.result()
                        if meta_description:
                            url_data["meta_description"] = meta_description
                    except Exception as e:
                        logger.error(f"Error extracting meta description for {url_data['loc']}: {str(e)}")
                    
                    results.append(url_data)
        
        logger.info(f"Completed fetching meta descriptions. Found descriptions for {sum(1 for u in results if 'meta_description' in u)} URLs")
        return results

    def _extract_meta_description(self, url: str) -> Optional[str]:
        """Extract meta description from a URL."""
        try:
            response = self.fetch_url(url)
            if not response:
                return None
            
            soup = BeautifulSoup(response["content"], 'html.parser')
            
            # Try standard meta description
            meta_tag = soup.find('meta', attrs={'name': 'description'})
            if meta_tag and meta_tag.get('content'):
                return meta_tag.get('content')[:500]  # Truncate long descriptions
            
            # Try Open Graph description
            og_tag = soup.find('meta', attrs={'property': 'og:description'})
            if og_tag and og_tag.get('content'):
                return og_tag.get('content')[:500]
            
            return None
        except Exception as e:
            logger.error(f"Error extracting meta description from {url}: {str(e)}")
            return None

    def _crawl_website(self, base_url: str, max_pages: int) -> List[Dict[str, Any]]:
        """Crawl a website to generate a sitemap."""
        visited_urls = set()
        to_visit = [base_url]
        results = []
        base_domain = urlparse(base_url).netloc
        
        # Store a set of URLs we've already queued to visit
        queued = set(to_visit)
        
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
            results.extend(batch_results)
            
            # Add new URLs to the queue
            for new_url in new_urls:
                if (new_url not in visited_urls and 
                    new_url not in queued and 
                    len(queued) < max_pages * 2):  # Limit queue size
                    to_visit.append(new_url)
                    queued.add(new_url)
        
        logger.info(f"Crawl complete. Visited {len(visited_urls)} URLs, found {len(results)} results.")
        return results
        
    def _process_url_batch(self, urls: List[str], base_domain: str) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Process a batch of URLs in parallel."""
        batch_results = []
        all_new_urls = []
        
        # Use ThreadPoolExecutor for parallel processing
        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
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
                
                # Extract meta description
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
                
                # Extract links from the page
                soup = BeautifulSoup(response_data["content"], 'html.parser')
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