import logging
import threading
import time
import gzip
from typing import Dict, Any, Optional, ClassVar, Tuple
from urllib.parse import urlparse

import requests
from requests.exceptions import RequestException, Timeout, ConnectionError

logger = logging.getLogger(__name__)

class RateLimitedFetcher:
    """Utility class for fetching URLs with thread-safe rate limiting."""

    # --- Constants ---
    TIMEOUT: ClassVar[int] = 15
    DEFAULT_USER_AGENT: ClassVar[str] = "NeuralAMI-Agent/1.0"

    # --- Rate Limiting State (Thread-Safe) ---
    _rate_limiter_lock: ClassVar[threading.Lock] = threading.Lock()
    _domain_locks: ClassVar[Dict[str, threading.Lock]] = {}
    _last_request_time: ClassVar[Dict[str, float]] = {}
    _request_interval: ClassVar[Dict[str, float]] = {} # Stores calculated interval

    @classmethod
    def _get_domain_lock(cls, domain: str) -> threading.Lock:
        """Gets or creates a lock specific to a domain."""
        # Use the class lock to safely access/modify the shared _domain_locks dict
        with cls._rate_limiter_lock:
            if domain not in cls._domain_locks:
                cls._domain_locks[domain] = threading.Lock()
            return cls._domain_locks[domain]

    @classmethod
    def init_rate_limiting(cls, domain: str, rate_limit: float, crawl_delay: Optional[float]):
        """Initializes rate limiting state for a domain, considering crawl_delay.

        Selects the stricter (longer interval) between the user-provided rate limit
        and the crawl_delay found in robots.txt.
        """
        user_interval = 1.0 / rate_limit if rate_limit > 0 else float('inf')
        robots_interval = crawl_delay if crawl_delay is not None and crawl_delay > 0 else 0.0

        logger.debug(f"Rate limit inputs for {domain}: User RPS={rate_limit} (Interval={user_interval:.3f}s), Robots Crawl-Delay={crawl_delay}s")

        effective_interval = user_interval
        source = f"user setting ({rate_limit} rps)"

        if robots_interval > 0:
            if robots_interval > user_interval:
                effective_interval = robots_interval
                source = f"robots.txt crawl-delay ({crawl_delay}s)"
                logger.info(f"Rate limit for {domain}: Using stricter crawl-delay ({crawl_delay}s). User interval was {user_interval:.3f}s.")
            else:
                 logger.info(f"Rate limit for {domain}: User setting ({user_interval:.3f}s) is stricter than or equal to crawl-delay ({robots_interval}s). Using user setting.")
        else:
            logger.info(f"Rate limit for {domain}: No valid crawl-delay found in robots.txt. Using user setting ({user_interval:.3f}s interval).")
        
        logger.info(f"Rate limit for {domain} set: interval={effective_interval:.3f}s (Source: {source})")

        # Use the specific domain lock to safely update its rate limit info
        with cls._get_domain_lock(domain):
            # Initialize last request time relative to the interval to allow the first request immediately
            cls._last_request_time[domain] = time.time() - effective_interval 
            cls._request_interval[domain] = effective_interval

    @classmethod
    def _apply_rate_limit(cls, domain: str):
        """Applies rate limiting delay for the given domain (BLOCKING)."""
        # Use the specific domain lock to safely access/update its state
        with cls._get_domain_lock(domain):
            interval = cls._request_interval.get(domain)
            last_time = cls._last_request_time.get(domain)

            # If not initialized (should not happen if init is called properly), log and return
            if interval is None or last_time is None:
                logger.warning(f"Rate limit not initialized for domain: {domain}. Skipping delay.")
                return

            current_time = time.time()
            time_since_last = current_time - last_time

            if time_since_last < interval:
                sleep_time = interval - time_since_last
                #logger.debug(f"Rate limiting: sleeping for {sleep_time:.4f}s for domain {domain}")
                # CRITICAL: Sleep *within* the domain lock to ensure serialization
                time.sleep(sleep_time)

            # Update last request time *after* potential sleep, still within the lock
            cls._last_request_time[domain] = time.time()
            
    @classmethod
    def get_request_interval(cls, domain: str) -> Optional[float]:
        """Gets the configured request interval for a domain."""
        with cls._get_domain_lock(domain):
            return cls._request_interval.get(domain)

    @classmethod
    def fetch_url(cls, url: str) -> Dict[str, Any]:
        """Fetches a URL, handles errors, respects rate limits, handles Gzip and BOM."""
        try:
            parsed_url = urlparse(url)
            # Normalize domain consistently: remove leading 'www.'
            domain = parsed_url.netloc.replace("www.", "")
            if not domain:
                 logger.error(f"Could not extract domain from URL: {url}")
                 # Use requested_url in error dict for consistency
                 return {"success": False, "error": "Invalid URL: No domain", "requested_url": url}
        except Exception as e:
             logger.error(f"Error parsing URL '{url}': {e}", exc_info=True)
             return {"success": False, "error": f"URL parsing error: {e}", "requested_url": url}
        
        cls._apply_rate_limit(domain) # Use normalized domain
        
        #logger.debug(f"Fetching: {url}")
        try:
            response = requests.get(
                url,
                timeout=cls.TIMEOUT,
                headers={'User-Agent': cls.DEFAULT_USER_AGENT},
                allow_redirects=True,
                stream=True
            )
            response.raise_for_status()

            content_type = response.headers.get('content-type', '').lower()
            content = None
            content_bytes = None

            content_bytes = response.raw.read() # Read the raw content
            
            if content_bytes:
                 # 1. Check for and handle Gzip *FIRST*
                if content_bytes.startswith(b'\x1f\x8b'):
                    try:
                        decompressed_bytes = gzip.decompress(content_bytes)
                        content_bytes = decompressed_bytes # Replace original bytes with decompressed ones
                        # Update content_type if it wasn't set correctly
                        if 'xml' not in content_type and 'text' not in content_type:
                             if url.endswith(('.xml', '.xml.gz')):
                                 content_type = 'application/xml'
                                 logger.debug(f"Corrected content type to xml based on extension for {url}")
                             elif url.endswith(('.txt', '.txt.gz')):
                                 content_type = 'text/plain'
                                 logger.debug(f"Corrected content type to text based on extension for {url}")
                                 
                    except gzip.BadGzipFile as gzip_err:
                         logger.error(f"BadGzipFile error for {url}: {gzip_err}. Treating as non-gzipped.")
                         # Keep original content_bytes if decompression fails
                    except Exception as e:
                         logger.error(f"Failed to decompress assumed gzipped content for {url}: {e}", exc_info=True)
                         # Return error if decompression fails when expected
                         return {"success": False, "status_code": response.status_code, "error": f"Gzip decompression error: {e}", "content_bytes": content_bytes, "requested_url": url}
                else:
                     logger.debug(f"No Gzip magic bytes detected for {url}")

                 # 2. Decode Handling (with BOM detection on potentially decompressed bytes)
                try:
                    # Check for UTF-8 BOM first
                    if content_bytes.startswith(b'\xef\xbb\xbf'):
                        logger.debug(f"Detected and removing UTF-8 BOM for {url}")
                        content = content_bytes[3:].decode('utf-8', errors='replace')
                    else:
                        # No BOM detected, proceed with normal decoding
                        # Use encoding from headers if available and reliable, else default to utf-8
                        detected_encoding = response.encoding if response.encoding else 'utf-8'
                        content = content_bytes.decode(detected_encoding, errors='replace')
                except UnicodeDecodeError as decode_err:
                     logger.warning(f"Decoding failed for {url} using {detected_encoding}: {decode_err}. Trying latin-1.")
                     try:
                          content = content_bytes.decode('latin-1')
                     except Exception as final_decode_err:
                          logger.error(f"Failed decode even with latin-1 for {url}: {final_decode_err}")
                          content = None
                          return {"success": False, "status_code": response.status_code, "error": "Content decoding failed", "content_bytes": content_bytes, "requested_url": url}
                except Exception as e:
                     logger.error(f"Error during content decoding/BOM check for {url}: {e}", exc_info=True)
                     content = None
                     return {"success": False, "status_code": response.status_code, "error": f"Content decoding/BOM error: {e}", "content_bytes": content_bytes, "requested_url": url}
            else:
                 logger.debug("Received empty content_bytes.")
                 content = '' # Treat empty bytes as empty string

            return {
                "success": True,
                "status_code": response.status_code,
                "content_type": content_type,
                "content": content,
                "content_bytes": content_bytes if len(content_bytes) <= 5000 else b'[content_bytes truncated]', # Avoid huge logs
                "final_url": response.url,
                "requested_url": url
            }

        except Timeout:
            logger.warning(f"Request timed out for {url}")
            return {"success": False, "error": "Timeout", "requested_url": url}
        except ConnectionError as e:
            logger.warning(f"Connection error for {url}: {e}")
            return {"success": False, "error": f"ConnectionError: {e}", "requested_url": url}
        except requests.exceptions.HTTPError as e:
            logger.warning(f"HTTP error for {url}: {e.response.status_code}")
            content_bytes_error = None
            try: 
                content_bytes_error = e.response.content
            except: pass
            return {"success": False, "status_code": e.response.status_code, "error": f"HTTP {e.response.status_code}", "content_bytes": content_bytes_error, "requested_url": url}
        except RequestException as e:
            logger.error(f"Request failed for {url}: {e}", exc_info=True)
            return {"success": False, "error": f"RequestException: {e}", "requested_url": url}
        except Exception as e:
            logger.error(f"Unexpected error fetching {url}: {e}", exc_info=True)
            return {"success": False, "error": f"Unexpected error: {e}", "requested_url": url} 