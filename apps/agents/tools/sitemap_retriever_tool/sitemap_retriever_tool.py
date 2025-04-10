from typing import Type, Optional, List, Dict, Any, Set, ClassVar, Tuple, Callable
from pydantic import BaseModel, Field, field_validator, AnyHttpUrl
from apps.agents.tools.base_tool import BaseTool
import json
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urlunparse
import xml.etree.ElementTree as ET
import csv
import io
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from requests.exceptions import RequestException, Timeout, ConnectionError
import time
import threading
from apps.agents.utils.rate_limited_fetcher import RateLimitedFetcher
from urllib.robotparser import RobotFileParser

logger = logging.getLogger(__name__)

class SitemapRetrieverSchema(BaseModel):
    """Input schema for the Sitemap Retriever Tool."""
    url: AnyHttpUrl = Field(
        ...,
        description="The starting URL of the website (e.g., 'https://example.com')."
    )
    user_id: int = Field(
        ...,
        description="ID of the user initiating the request (for logging/tracking)."
    )
    max_pages: int = Field(
        100,
        description="Maximum number of URLs to return. Applies to both sitemap parsing and crawling.",
        gt=0
    )
    requests_per_second: float = Field(
        5.0,
        description="Maximum desired requests per second. Will be lowered if robots.txt Crawl-delay is stricter.",
        gt=0
    )

    # Pydantic automatically validates AnyHttpUrl and numeric constraints (gt=0)
    model_config = {
        "arbitrary_types_allowed": True,
        "extra": "forbid"
    }

class SitemapRetrieverTool(BaseTool):
    """
    Retrieves website URLs by first searching for and parsing sitemaps (XML or TXT).
    Respects robots.txt directives (Sitemap, Crawl-delay).
    If no sitemaps are found or they yield no URLs, falls back to crawling the site.
    Limits the number of returned URLs via max_pages.
    Uses RateLimitedFetcher for network requests.
    """
    name: str = "Sitemap Retriever Tool"
    description: str = (
        "Finds and parses website sitemaps (robots.txt, common paths) or crawls "
        "the site to retrieve a list of URLs, respecting robots.txt rules and rate limits. "
        "Specify the website's starting URL."
    )
    args_schema: Type[BaseModel] = SitemapRetrieverSchema

    # --- Constants ---
    TIMEOUT: ClassVar[int] = 15  # Increased timeout for potentially slow sites
    MAX_WORKERS_SITEMAP_CHECK: ClassVar[int] = 5
    DEFAULT_USER_AGENT: ClassVar[str] = "NeuralAMI-Agent/1.0"
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
        "sitemap.txt",          # Text-based sitemap
        "sitemap.xml.gz",       # Gzipped XML sitemap
        "sitemap_index.xml.gz"  # Gzipped XML sitemap index
    ]
    # XML namespace for sitemaps
    SITEMAP_XML_NAMESPACE: ClassVar[Dict[str, str]] = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

    # Alternative namespace handling for sites that don't use the standard namespace
    SITEMAP_TAGS: ClassVar[Dict[str, List[str]]] = {
        'sitemapindex': ['{http://www.sitemaps.org/schemas/sitemap/0.9}sitemapindex', 'sitemapindex'],
        'sitemap': ['{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap', 'sitemap'],
        'loc': ['{http://www.sitemaps.org/schemas/sitemap/0.9}loc', 'loc'],
        'urlset': ['{http://www.sitemaps.org/schemas/sitemap/0.9}urlset', 'urlset'],
        'url': ['{http://www.sitemaps.org/schemas/sitemap/0.9}url', 'url'],
        'lastmod': ['{http://www.sitemaps.org/schemas/sitemap/0.9}lastmod', 'lastmod'],
        'changefreq': ['{http://www.sitemaps.org/schemas/sitemap/0.9}changefreq', 'changefreq'],
        'priority': ['{http://www.sitemaps.org/schemas/sitemap/0.9}priority', 'priority']
    }

    # --- Rate Limiting State - REMOVED ---
    # Rate limiting state and methods (_get_domain_lock, _init_rate_limiting, _apply_rate_limit)
    # are now fully handled by the RateLimitedFetcher class.

    # --- Fetching Logic ---
    # REMOVED _fetch_url - RateLimitedFetcher.fetch_url is used directly.

    # --- Sitemap Discovery Logic ---
    # --- Sitemap Discovery Logic ---
    def _check_robots(self, base_url: str, domain: str) -> Tuple[Set[str], Optional[float]]:
        """Fetches and parses robots.txt using RateLimitedFetcher.

        Uses urllib.robotparser for sitemaps.
        Includes a robust manual check for crawl-delay for the '*' agent,
        handling cases where it's not the first directive on the line.
        Returns a set of sitemap URLs found and the crawl delay (float) for the '*' agent, or None.
        Does NOT initialize rate limiting itself.
        """
        robots_url_http = urlunparse(urlparse(base_url)._replace(scheme='http', path='robots.txt', query='', fragment=''))
        robots_url_https = urlunparse(urlparse(base_url)._replace(scheme='https', path='robots.txt', query='', fragment=''))
        sitemap_urls = set()
        crawl_delay = None
        found_authoritative_robots = False
        checked_urls = set()

        for robots_url in [robots_url_https, robots_url_http]:
            if robots_url in checked_urls:
                continue
            checked_urls.add(robots_url)
            # Stop checking (e.g. http) if we successfully parsed one (e.g. https) AND found a delay
            if found_authoritative_robots and crawl_delay is not None:
                break

            logger.debug(f"Checking robots.txt at: {robots_url}")
            response_data = RateLimitedFetcher.fetch_url(robots_url)

            if response_data["success"] and response_data["content"] is not None:
                logger.debug(f"Successfully fetched robots.txt content from {robots_url}")
                robots_content = response_data["content"]
                parser = RobotFileParser()
                manual_crawl_delay = None
                current_agent_is_wildcard = False # Track state across lines

                # 1. Manual check for wildcard crawl-delay and sitemaps
                try:
                    lines = robots_content.splitlines()
                    for line in lines:
                        line = line.strip()
                        if not line or line.startswith('#'): continue

                        line_lower = line.lower()
                        # Check for User-agent change first
                        if line_lower.startswith('user-agent:'):
                            value_part = line.split(':', 1)[-1].strip()
                            # Take only the first part before any space (potential directive)
                            agent = value_part.split(None, 1)[0].strip()
                            current_agent_is_wildcard = (agent == '*')
                            # Don't continue; check current line for delay/sitemap

                        # Check for crawl-delay IF we are in the wildcard block
                        if current_agent_is_wildcard:
                            directive_key_cd = 'crawl-delay:'
                            idx_cd = line_lower.find(directive_key_cd)
                            if idx_cd != -1:
                                # Extract the part after 'crawl-delay:'
                                value_part_cd = line[idx_cd + len(directive_key_cd):].lstrip()
                                try:
                                    # Split by whitespace and take the first part (the number)
                                    value_str_cd = value_part_cd.split(None, 1)[0]
                                    delay = float(value_str_cd)
                                    if delay > 0:
                                        # Check if this is the first delay found OR if it's stricter (smaller value) than a previously found one
                                        # Note: Robot standard typically uses first match, but stricter seems safer if multiple exist. Let's stick to first found for now.
                                        if manual_crawl_delay is None: # Only assign if not already found in this file
                                            manual_crawl_delay = delay
                                            # Don't break, might find Sitemap on same line or later lines
                                    else:
                                         #logger.debug(f"Ignoring non-positive manual crawl-delay value: {value_str_cd} from line '{line}'")
                                         pass
                                except (ValueError, TypeError, IndexError) as e:
                                    logger.warning(f"Could not parse manual crawl-delay value after '{directive_key_cd}' from line '{line}'. Error: {e}")

                        # Check for Sitemap directive (can appear under any user-agent or globally)
                        directive_key_sm = 'sitemap:'
                        idx_sm = line_lower.find(directive_key_sm)
                        if idx_sm != -1:
                            value_part_sm = line[idx_sm + len(directive_key_sm):].lstrip()
                            # Sitemap URL might have spaces if other directives follow, take everything until likely end
                            sitemap_path = value_part_sm.split(None, 1)[0].strip() # Take first part
                            if sitemap_path:
                                try:
                                    # Resolve relative path against the base URL of the robots.txt file itself
                                    absolute_sitemap_url = urljoin(robots_url, sitemap_path)
                                    parsed_sitemap_url = urlparse(absolute_sitemap_url)
                                    # Basic validation: needs scheme and netloc
                                    if parsed_sitemap_url.scheme and parsed_sitemap_url.netloc:
                                         sitemap_urls.add(absolute_sitemap_url)
                                    else:
                                         # logger.warning(f"Ignoring manually found invalid sitemap URL: '{sitemap_path}' derived from line '{line}' in {robots_url}")
                                         pass

                                except Exception as e:
                                     logger.warning(f"Error processing manually found sitemap URL '{sitemap_path}' from line '{line}' in {robots_url}: {e}")
                            else:
                                logger.warning(f"Found '{directive_key_sm}' but no value on line '{line}' in {robots_url}")

                except Exception as e:
                    logger.error(f"Error during manual robots.txt parsing: {e}", exc_info=True)

                # 2. Use standard parser for sitemaps (as fallback/confirmation) and delay (only if manual failed)
                try:
                    # Re-initialize parser for each file's content
                    parser = RobotFileParser()
                    parser.parse(io.StringIO(robots_content).readlines())
                    found_authoritative_robots = True # Mark this file as successfully parsed

                    # Get sitemaps using parser (confirm/add to manually found ones)
                    parser_sitemaps = parser.site_maps()
                    if parser_sitemaps:
                        sitemaps_found_by_parser = set(parser_sitemaps)
                        newly_found_by_parser = sitemaps_found_by_parser - sitemap_urls # Find only those not found manually
                        if newly_found_by_parser:
                             sitemap_urls.update(newly_found_by_parser)

                    # Get crawl delay from parser (only if manual check failed)
                    if manual_crawl_delay is None:
                        parser_crawl_delay_val = parser.crawl_delay('*')
                        if parser_crawl_delay_val is not None:
                            try:
                                parsed_delay_float = float(parser_crawl_delay_val)
                                if parsed_delay_float > 0:
                                     manual_crawl_delay = parsed_delay_float # Use parser's value as final

                            except (ValueError, TypeError):
                                 logger.warning(f"Could not parse parser crawl-delay value '{parser_crawl_delay_val}' from {robots_url}")



                except Exception as e:
                    logger.error(f"Error parsing robots.txt content from {robots_url} with urllib.robotparser: {e}", exc_info=True)
                    # Continue to next URL if parsing fails, keep manually found delay

                # Prioritize the delay found (manual first, then parser) from this file
                if manual_crawl_delay is not None:
                    crawl_delay = manual_crawl_delay


            elif response_data.get("status_code") == 404:
                # 404 errors for robots.txt are common and expected
                logger.debug(f"No robots.txt found at {robots_url} (404)")
            else:
                logger.warning(f"Failed to fetch {robots_url}: Status={response_data.get('status_code')}, Error={response_data.get('error')}")

        return sitemap_urls, crawl_delay

    def _check_common_paths(self, base_url: str, domain: str) -> Set[str]:
        """Checks common sitemap paths concurrently using RateLimitedFetcher."""
        common_urls_to_check = {urljoin(base_url, path) for path in self.COMMON_SITEMAP_PATHS}
        found_sitemaps = set()
        logger.debug(f"Checking {len(common_urls_to_check)} common sitemap paths for {base_url}...")

        # Use ThreadPoolExecutor for concurrent checks
        # Note: RateLimiterFetcher handles domain-level locking internally
        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS_SITEMAP_CHECK) as executor:
            future_to_url = {executor.submit(RateLimitedFetcher.fetch_url, url): url for url in common_urls_to_check}
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    result = future.result()
                    # Check for success and valid content type (XML or TXT)
                    if result["success"]:
                        content_type = result.get("content_type", "").lower()
                        # Basic check for XML/TXT content types or file extensions
                        is_xml = 'xml' in content_type or url.endswith(('.xml', '.xml.gz'))
                        is_txt = 'text/plain' in content_type or url.endswith(('.txt', '.txt.gz'))

                        if is_xml or is_txt:
                            found_sitemaps.add(result["final_url"]) # Use final URL after redirects
                    elif result.get("status_code") == 404:
                        # 404 errors are expected for many sitemap checks, just log at debug level
                        logger.debug(f"Common sitemap path not found (404): {url}")

                except Exception as e:
                    logger.error(f"Exception checking common path {url}: {e}", exc_info=True)

        return found_sitemaps

    # REMOVED _find_sitemap_urls METHOD

    def _parse_single_sitemap(self, sitemap_url: str, domain: str, processed_locs: Set[str], max_pages: int, current_url_count: int) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Parses a single sitemap URL (XML or TXT) or sitemap index."""
        logger.debug(f"Parsing sitemap: {sitemap_url}")
        page_urls = []
        child_sitemap_urls = []

        if current_url_count >= max_pages:
            return page_urls, child_sitemap_urls # Stop early if max_pages reached

        # Fetch sitemap content using RateLimitedFetcher
        result = RateLimitedFetcher.fetch_url(sitemap_url) # Ensure this uses the class method

        if not result["success"] or result["content"] is None:
            # Don't log warnings for 404 errors as they're expected for many sitemap checks
            if result.get("status_code") == 404:
                logger.debug(f"Sitemap not found (404) at {sitemap_url}")
            else:
                logger.warning(f"Failed to fetch sitemap content from {sitemap_url}: {result.get('error')}")
            return page_urls, child_sitemap_urls

        content = result["content"]
        content_type = result.get("content_type", "").lower()
        final_url = result["final_url"] # Use final URL

        # Determine parsing strategy based on content type or URL
        is_xml = 'xml' in content_type or final_url.endswith(('.xml', '.xml.gz'))
        is_txt = 'text/plain' in content_type or final_url.endswith(('.txt', '.txt.gz'))

        # 1. Try XML Parsing (Sitemap Index or URL Set)
        if is_xml:
            try:
                # Attempt to prevent XML vulnerabilities
                # Use defusedxml if available, otherwise standard ET
                try:
                    import defusedxml.ElementTree as SafeET
                    root = SafeET.fromstring(content)
                except ImportError:
                     root = ET.fromstring(content)
                except ET.ParseError as xml_err:
                    root = None # Signal fallback

                if root is not None:
                    # Check if it's a sitemap index (using flexible tag matching)
                    is_sitemap_index = False
                    for tag_variant in self.SITEMAP_TAGS['sitemapindex']:
                        if root.tag.endswith(tag_variant):
                            is_sitemap_index = True
                            break

                    if is_sitemap_index:
                        # Try both namespace and non-namespace approaches
                        sitemaps = []
                        # First try with namespace
                        ns_sitemaps = root.findall('ns:sitemap', self.SITEMAP_XML_NAMESPACE)
                        if ns_sitemaps:
                            sitemaps = ns_sitemaps
                        else:
                            # Try without namespace
                            for tag_variant in self.SITEMAP_TAGS['sitemap']:
                                direct_sitemaps = root.findall(tag_variant)
                                if direct_sitemaps:
                                    sitemaps = direct_sitemaps
                                    break

                        for sitemap_tag in sitemaps:
                            # Try to find loc tag with namespace
                            loc_tag = sitemap_tag.find('ns:loc', self.SITEMAP_XML_NAMESPACE)

                            # If not found, try without namespace
                            if loc_tag is None:
                                for tag_variant in self.SITEMAP_TAGS['loc']:
                                    loc_tag = sitemap_tag.find(tag_variant)
                                    if loc_tag is not None:
                                        break

                            if loc_tag is not None and loc_tag.text:
                                child_sitemap_urls.append(loc_tag.text.strip())

                        # Return early, don't look for <url> tags in an index file
                        logger.debug(f"Finished parsing index {final_url}. Found {len(child_sitemap_urls)} child sitemaps.")
                        return page_urls, child_sitemap_urls

                    # Check if it's a URL set (using flexible tag matching)
                    is_urlset = False
                    for tag_variant in self.SITEMAP_TAGS['urlset']:
                        if root.tag.endswith(tag_variant):
                            is_urlset = True
                            break

                    if is_urlset:
                        # Try both namespace and non-namespace approaches
                        urls = []
                        # First try with namespace
                        ns_urls = root.findall('ns:url', self.SITEMAP_XML_NAMESPACE)
                        if ns_urls:
                            urls = ns_urls
                        else:
                            # Try without namespace
                            for tag_variant in self.SITEMAP_TAGS['url']:
                                direct_urls = root.findall(tag_variant)
                                if direct_urls:
                                    urls = direct_urls
                                    break

                        for url_tag in urls:
                            if current_url_count >= max_pages: break

                            # Try to find loc tag with namespace
                            loc_tag = url_tag.find('ns:loc', self.SITEMAP_XML_NAMESPACE)

                            # If not found, try without namespace
                            if loc_tag is None:
                                for tag_variant in self.SITEMAP_TAGS['loc']:
                                    loc_tag = url_tag.find(tag_variant)
                                    if loc_tag is not None:
                                        break
                            if loc_tag is not None and loc_tag.text:
                                loc_text = loc_tag.text.strip()
                                if loc_text not in processed_locs:
                                    url_data = {'loc': loc_text}
                                    # Optional fields
                                    lastmod = url_tag.find('ns:lastmod', self.SITEMAP_XML_NAMESPACE)
                                    if lastmod is not None: url_data['lastmod'] = lastmod.text
                                    changefreq = url_tag.find('ns:changefreq', self.SITEMAP_XML_NAMESPACE)
                                    if changefreq is not None: url_data['changefreq'] = changefreq.text
                                    priority = url_tag.find('ns:priority', self.SITEMAP_XML_NAMESPACE)
                                    if priority is not None: url_data['priority'] = priority.text

                                    page_urls.append(url_data)
                                    processed_locs.add(loc_text)
                                    current_url_count += 1
                        return page_urls, child_sitemap_urls # Successfully parsed as XML urlset

            except Exception as e:
                # Catch broader errors during XML parsing, including defusedxml/ET issues
                logger.warning(f"Error parsing XML content for {final_url}: {e}. Trying regex/text fallback.", exc_info=False)
                # Fall through to regex/text parsing

        # 2. Try Regex Fallback (for malformed XML or other formats containing <loc>)
        # Only attempt if XML parsing failed or wasn't attempted
        if not page_urls and not child_sitemap_urls:
             try:
                  # Find URLs within <loc>...</loc> tags
                  loc_matches = re.findall(r'<loc>(.*?)</loc>', content, re.IGNORECASE)
                  for loc_text in loc_matches:
                       if current_url_count >= max_pages: break
                       loc_text = loc_text.strip()
                       if loc_text.startswith(('http://', 'https://')) and loc_text not in processed_locs:
                            # Check if it looks like a child sitemap URL first
                            if loc_text.endswith(('.xml', '.xml.gz', '.txt', '.txt.gz')) or 'sitemap' in loc_text.lower():
                                 child_sitemap_urls.append(loc_text)
                            else:
                                 page_urls.append({'loc': loc_text}) # Basic data
                                 processed_locs.add(loc_text)
                                 current_url_count += 1
                  if page_urls or child_sitemap_urls:
                       return page_urls, child_sitemap_urls # Found URLs via regex
             except Exception as e:
                  logger.warning(f"Regex parsing failed for {final_url}: {e}. Trying direct text parsing.")


        # 3. Try Direct Text Parsing (for sitemap.txt or simple lists)
        # Only attempt if XML and Regex failed or wasn't attempted (e.g., is_txt was true)
        if not page_urls and not child_sitemap_urls:
            try:
                lines = content.splitlines()
                for line in lines:
                    if current_url_count >= max_pages: break
                    line = line.strip()
                    if line.startswith(('http://', 'https://')) and line not in processed_locs:
                        # Check if it looks like a child sitemap URL first
                        if line.endswith(('.xml', '.xml.gz', '.txt', '.txt.gz')) or 'sitemap' in line.lower():
                            child_sitemap_urls.append(line)
                        else:
                            page_urls.append({'loc': line}) # Basic data
                            processed_locs.add(line)
                            current_url_count += 1
                # Return after processing all lines, not inside the loop
            except Exception as e:
                logger.warning(f"Direct text parsing failed for {final_url}: {e}")


        logger.debug(f"Finished parsing {final_url}. Found {len(page_urls)} new URLs, {len(child_sitemap_urls)} child sitemaps.")
        return page_urls, child_sitemap_urls


    def _parse_sitemaps(self, initial_sitemap_urls: Set[str], domain: str, max_pages: int) -> List[Dict[str, Any]]:
        """Parses a queue of sitemap URLs, handling nested sitemaps."""
        sitemap_queue = list(initial_sitemap_urls)
        processed_sitemaps = set(initial_sitemap_urls) # Avoid reprocessing
        processed_locs = set() # Track unique page URLs found across all sitemaps
        extracted_urls = []
        total_sitemaps_parsed = 0

        logger.debug(f"Starting sitemap parsing. Queue: {len(sitemap_queue)}, Max pages: {max_pages}")

        while sitemap_queue and len(extracted_urls) < max_pages:
            current_sitemap_url = sitemap_queue.pop(0)
            total_sitemaps_parsed += 1

            page_urls, child_sitemap_urls = self._parse_single_sitemap(
                sitemap_url=current_sitemap_url,
                domain=domain,
                processed_locs=processed_locs,
                max_pages=max_pages,
                current_url_count=len(extracted_urls)
            )

            # Only extend if we haven't hit the limit
            if len(extracted_urls) < max_pages:
                urls_to_add = page_urls[:max_pages - len(extracted_urls)]
                extracted_urls.extend(urls_to_add)

            # Add newly discovered child sitemaps to the queue if not already processed
            # and we haven't hit the max_pages limit (no point parsing more if we can't add URLs)
            if len(extracted_urls) < max_pages:
                for child_url in child_sitemap_urls:
                    if child_url not in processed_sitemaps:
                        sitemap_queue.append(child_url)
                        processed_sitemaps.add(child_url)

            # Early exit if max pages reached
            if len(extracted_urls) >= max_pages:
                logger.debug(f"Reached max_pages limit ({max_pages}) during sitemap parsing.")
                break

        logger.info(f"Sitemap parsing complete. Extracted {len(extracted_urls)} URLs from {total_sitemaps_parsed} files.")
        return extracted_urls # Already sliced to max_pages if limit was hit

    def _format_output(self, success: bool, method: str, urls: List[Dict[str, Any]], start_time: float, crawl_delay: Optional[float], **kwargs) -> Dict[str, Any]:
        """Formats the final output dictionary, including the determined crawl_delay.""" # Updated docstring
        end_time = time.time()
        # Get the actual interval used by the fetcher for this domain
        domain = urlparse(kwargs.get("base_url", "")).netloc.replace("www.", "")
        final_interval = RateLimitedFetcher.get_request_interval(domain) if domain else None

        result = {
            "success": success,
            "method_used": method, # 'sitemap' or 'crawl'
            "total_urls_found": len(urls),
            "urls": urls, # List of dicts, e.g., [{'loc': url, 'lastmod': ...}, ...]
            "duration_seconds": round(end_time - start_time, 2),
            "robots_crawl_delay_found": crawl_delay, # The delay found in robots.txt (or None)
            "final_request_interval_used": final_interval # The actual interval applied by fetcher
        }
        # Add any extra kwargs passed (like error messages or base_url)
        result.update(kwargs)
        logger.info(f"SitemapRetrieverTool finished in {result['duration_seconds']}s. Method: {method}. Found {result['total_urls_found']} URLs. Robots Crawl Delay: {crawl_delay}. Final Interval: {final_interval}s")
        # Return the dictionary directly, Celery task will handle JSON conversion if needed
        return result


    # --- Main Execution ---
    def _run(self, url: str, user_id: int, max_pages: int = 1000, requests_per_second: float = 5.0) -> Dict[str, Any]:
        """
        Orchestrates the process: check robots, init rate limiter, check common paths, parse sitemaps, fallback crawl.
        """
        start_time = time.time()
        parsed_url = urlparse(url)
        base_url = urlunparse(parsed_url._replace(path='', query='', fragment=''))
        domain = parsed_url.netloc.replace("www.", "") # Normalize domain
        if not domain:
             logger.error(f"Could not parse domain from URL: {url}")
             # Use format_output for consistency
             return self._format_output(
                 success=False, method='setup', urls=[], start_time=start_time,
                 error="Invalid URL: Could not parse domain", crawl_delay=None, base_url=url
             )

        logger.info(f"Starting Sitemap Retriever for {url} (Domain: {domain}, Max Pages: {max_pages}, User RPS: {requests_per_second})")

        # 1. Check robots.txt for sitemaps and crawl-delay (DOES NOT init rate limit)
        # Fetching robots.txt uses RateLimitedFetcher default (likely uninitialized/fast rate)
        sitemap_urls_from_robots, robots_crawl_delay = self._check_robots(base_url, domain)

        # 2. Initialize Rate Limiter *LATER* - Only if crawling is needed.

        # 3. Check common sitemap paths (uses RateLimitedFetcher default rate)
        sitemap_urls_from_common = self._check_common_paths(base_url, domain)

        # 4. Combine and Parse Sitemaps (uses RateLimitedFetcher default rate)
        initial_sitemap_urls = sitemap_urls_from_robots.union(sitemap_urls_from_common)
        parsed_urls = [] # Initialize to empty list
        method_used = 'none' # Initialize method

        if initial_sitemap_urls:
            logger.debug(f"Found {len(initial_sitemap_urls)} potential sitemaps from robots.txt and common paths.")
            parsed_urls = self._parse_sitemaps(initial_sitemap_urls, domain, max_pages)
            if parsed_urls:
                # Success via sitemap parsing
                method_used = 'sitemap'
                logger.info(f"Successfully parsed {len(parsed_urls)} URLs via sitemap method.")
                # We have URLs, format output and return
                return self._format_output(
                    success=True,
                    method=method_used,
                    urls=parsed_urls,
                    start_time=start_time,
                    crawl_delay=robots_crawl_delay, # Pass the determined delay
                    base_url=base_url # Include base_url for context
                )
            else:
                logger.warning(f"Parsing {len(initial_sitemap_urls)} potential sitemaps yielded no URLs for {base_url}.")
                method_used = 'sitemap_failed' # Indicate sitemaps were found but empty/failed
                return self._format_output(
                    success=False, method=method_used, urls=[], start_time=start_time,
                    error="No usable URLs found in sitemaps", crawl_delay=robots_crawl_delay, base_url=base_url
                )
        else:
            logger.warning(f"No sitemap URLs found in robots.txt or common paths for {base_url}.")
            method_used = 'no_sitemaps_found'
            return self._format_output(
                success=False, method=method_used, urls=[], start_time=start_time,
                error="No sitemaps found", crawl_delay=robots_crawl_delay, base_url=base_url
            )