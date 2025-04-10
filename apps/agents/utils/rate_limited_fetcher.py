import logging
import threading
import time
import gzip
import random
from typing import Dict, Any, Optional, ClassVar, List
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

class RateLimitedFetcher:
    """Utility class for fetching URLs with thread-safe rate limiting and backoff strategy."""

    # --- Constants ---
    TIMEOUT: ClassVar[int] = 15
    DEFAULT_USER_AGENT: ClassVar[str] = "NeuralAMI-Agent/1.0"

    # List of common user agents for rotation
    USER_AGENTS: ClassVar[List[str]] = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (iPad; CPU OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
        "NeuralAMI-Agent/1.0"
    ]

    # --- Rate Limiting State (Thread-Safe) ---
    _rate_limiter_lock: ClassVar[threading.Lock] = threading.Lock()
    _domain_locks: ClassVar[Dict[str, threading.Lock]] = {}
    _last_request_time: ClassVar[Dict[str, float]] = {}
    _request_interval: ClassVar[Dict[str, float]] = {} # Stores calculated interval

    # --- Backoff Strategy State ---
    _domain_failures: ClassVar[Dict[str, int]] = {}  # Count of consecutive failures per domain
    _domain_backoff_until: ClassVar[Dict[str, float]] = {}  # Timestamp until which to apply backoff
    _session_start_time: ClassVar[Dict[str, float]] = {}  # When the session for this domain started

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
            # Initialize backoff strategy state
            cls._domain_failures[domain] = 0
            cls._domain_backoff_until[domain] = 0
            cls._session_start_time[domain] = time.time()

    @classmethod
    def _apply_rate_limit(cls, domain: str):
        """Applies rate limiting delay for the given domain (BLOCKING)."""
        # Use the specific domain lock to safely access/update its state
        with cls._get_domain_lock(domain):
            interval = cls._request_interval.get(domain)
            last_time = cls._last_request_time.get(domain)
            backoff_until = cls._domain_backoff_until.get(domain, 0)

            # If not initialized (should not happen if init is called properly), log and return
            if interval is None or last_time is None:
                return

            current_time = time.time()

            # Check if we're in a backoff period
            if backoff_until > current_time:
                backoff_sleep = backoff_until - current_time
                logger.info(f"Backoff in effect for {domain}: sleeping for {backoff_sleep:.2f}s")
                time.sleep(backoff_sleep)
                # Reset backoff after applying it
                cls._domain_backoff_until[domain] = 0
                current_time = time.time()

            # Apply normal rate limiting
            time_since_last = current_time - last_time
            if time_since_last < interval:
                sleep_time = interval - time_since_last
                #logger.debug(f"Rate limiting: sleeping for {sleep_time:.4f}s for domain {domain}")
                # CRITICAL: Sleep *within* the domain lock to ensure serialization
                time.sleep(sleep_time)

            # Update last request time *after* potential sleep, still within the lock
            cls._last_request_time[domain] = time.time()

            # Check if session has been running for too long (over 50 minutes)
            # This helps avoid the 1-hour cutoff issue by rotating sessions
            session_duration = time.time() - cls._session_start_time.get(domain, 0)
            if session_duration > 3000:  # 50 minutes in seconds
                logger.warning(f"Session for {domain} has been running for {session_duration/60:.1f} minutes. Applying session cooldown.")
                # Apply a session cooldown of 2-5 minutes
                cooldown = random.uniform(120, 300)
                cls._domain_backoff_until[domain] = time.time() + cooldown
                # Reset session start time
                cls._session_start_time[domain] = time.time() + cooldown

    @classmethod
    def get_request_interval(cls, domain: str) -> Optional[float]:
        """Gets the configured request interval for a domain."""
        with cls._get_domain_lock(domain):
            return cls._request_interval.get(domain)

    @classmethod
    def _apply_backoff_strategy(cls, domain: str, success: bool = True):
        """Applies backoff strategy based on success/failure of requests.

        Args:
            domain: The domain to apply backoff for
            success: Whether the request was successful
        """
        with cls._get_domain_lock(domain):
            if success:
                # Reset failure count on success
                cls._domain_failures[domain] = 0
            else:
                # Increment failure count
                failure_count = cls._domain_failures.get(domain, 0) + 1
                cls._domain_failures[domain] = failure_count

                # Apply exponential backoff based on consecutive failures
                if failure_count > 0:
                    # Base backoff: 5 seconds * 2^(failure_count-1) with some randomness
                    backoff_seconds = 5 * (2 ** (min(failure_count - 1, 6))) * random.uniform(0.75, 1.25)

                    # Cap at 10 minutes
                    backoff_seconds = min(backoff_seconds, 600)

                    logger.warning(f"Applying backoff for {domain} after {failure_count} consecutive failures: {backoff_seconds:.2f}s")
                    cls._domain_backoff_until[domain] = time.time() + backoff_seconds

    @classmethod
    def fetch_url(cls, url: str, max_retries: int = 3) -> Dict[str, Any]:
        """Fetches a URL with retries, handles errors, respects rate limits, handles Gzip and BOM.

        Args:
            url: The URL to fetch
            max_retries: Maximum number of retries for transient errors

        Returns:
            Dictionary with fetch results
        """
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

        # Apply rate limiting and any active backoff
        cls._apply_rate_limit(domain)

        # Initialize retry counter
        retry_count = 0
        last_error = None

        # Retry loop
        while retry_count <= max_retries:
            try:
                # Select a random user agent for each attempt to avoid fingerprinting
                user_agent = random.choice(cls.USER_AGENTS)

                # Add some randomness to the request headers
                headers = {
                    'User-Agent': user_agent,
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Cache-Control': 'max-age=0'
                }

                # Add a small random delay before each request (even the first one)
                # This makes the crawler behavior more human-like
                if retry_count > 0:
                    jitter = random.uniform(0.1, 0.5)
                    time.sleep(jitter)

                response = requests.get(
                    url,
                    timeout=cls.TIMEOUT,
                    headers=headers,
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

                # Success! Mark this domain as successful and return the result
                cls._apply_backoff_strategy(domain, success=True)

                return {
                    "success": True,
                    "status_code": response.status_code,
                    "content_type": content_type,
                    "content": content,
                    "content_bytes": content_bytes if len(content_bytes) <= 5000 else b'[content_bytes truncated]', # Avoid huge logs
                    "final_url": response.url,
                    "requested_url": url
                }

            except requests.exceptions.Timeout as e:
                retry_count += 1
                last_error = e
                logger.warning(f"Request timed out for {url} (attempt {retry_count}/{max_retries})")
                # Timeouts are often transient, so we'll retry
                if retry_count <= max_retries:
                    # Exponential backoff for retries
                    backoff_time = (2 ** (retry_count - 1)) * random.uniform(1, 2)
                    logger.info(f"Retrying after {backoff_time:.2f}s")
                    time.sleep(backoff_time)
                    continue

            except requests.exceptions.ConnectionError as e:
                retry_count += 1
                last_error = e
                logger.warning(f"Connection error for {url}: {e} (attempt {retry_count}/{max_retries})")
                # Connection errors are often transient, so we'll retry
                if retry_count <= max_retries:
                    # Exponential backoff for retries
                    backoff_time = (2 ** (retry_count - 1)) * random.uniform(1, 2)
                    logger.info(f"Retrying after {backoff_time:.2f}s")
                    time.sleep(backoff_time)
                    continue

            except requests.exceptions.HTTPError as e:
                retry_count += 1
                last_error = e
                status_code = e.response.status_code if hasattr(e, 'response') and hasattr(e.response, 'status_code') else 'unknown'
                logger.warning(f"HTTP error {status_code} for {url} (attempt {retry_count}/{max_retries})")

                # For certain status codes, retrying won't help
                if status_code in (403, 429, 503):
                    # These status codes indicate rate limiting or blocking
                    # Apply a longer backoff and mark domain for backoff strategy
                    cls._apply_backoff_strategy(domain, success=False)

                    # For these specific codes, we'll retry with a longer backoff
                    if retry_count <= max_retries:
                        # Use a longer backoff for these specific errors
                        backoff_time = (2 ** (retry_count + 1)) * random.uniform(2, 4)
                        logger.info(f"Rate limiting detected. Retrying after {backoff_time:.2f}s")
                        time.sleep(backoff_time)
                        continue
                elif retry_count <= max_retries and status_code >= 500:
                    # Server errors (5xx) are often transient, so we'll retry
                    backoff_time = (2 ** (retry_count - 1)) * random.uniform(1, 2)
                    logger.info(f"Retrying after {backoff_time:.2f}s")
                    time.sleep(backoff_time)
                    continue

                # For other HTTP errors, we'll just return the error
                content_bytes_error = None
                try:
                    content_bytes_error = e.response.content
                except: pass

                # Mark domain for backoff strategy, but don't apply backoff for 404 errors
                if status_code != 404:
                    cls._apply_backoff_strategy(domain, success=False)
                else:
                    logger.info(f"404 error for {url} - not applying backoff strategy")
                return {"success": False, "status_code": status_code, "error": f"HTTP {status_code}", "content_bytes": content_bytes_error, "requested_url": url}

            except requests.exceptions.RequestException as e:
                retry_count += 1
                last_error = e
                logger.error(f"Request failed for {url}: {e} (attempt {retry_count}/{max_retries})")
                # Some request exceptions are transient, so we'll retry
                if retry_count <= max_retries:
                    # Exponential backoff for retries
                    backoff_time = (2 ** (retry_count - 1)) * random.uniform(1, 2)
                    logger.info(f"Retrying after {backoff_time:.2f}s")
                    time.sleep(backoff_time)
                    continue

            except Exception as e:
                retry_count += 1
                last_error = e
                logger.error(f"Unexpected error fetching {url}: {e} (attempt {retry_count}/{max_retries})", exc_info=True)
                # For unexpected errors, we'll retry a few times
                if retry_count <= max_retries:
                    # Exponential backoff for retries
                    backoff_time = (2 ** (retry_count - 1)) * random.uniform(1, 2)
                    logger.info(f"Retrying after {backoff_time:.2f}s")
                    time.sleep(backoff_time)
                    continue

        # If we've exhausted all retries, mark domain for backoff strategy
        cls._apply_backoff_strategy(domain, success=False)

        # Determine the error message based on the last error
        error_type = type(last_error).__name__ if last_error else "Unknown error"
        error_msg = str(last_error) if last_error else "Maximum retries exceeded"

        logger.error(f"All {max_retries} retries failed for {url}: {error_type} - {error_msg}")
        return {"success": False, "error": f"{error_type}: {error_msg}", "requested_url": url}