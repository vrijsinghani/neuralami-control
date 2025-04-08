"""
FastAPI service for web scraping using Playwright.
"""
import asyncio
import base64
import logging
import os
from typing import Dict, List, Any, Optional, Union

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, HttpUrl
import uvicorn
from playwright.async_api import async_playwright

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Playwright Scraper API",
    description="API for web scraping using Playwright",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API key authentication (simple implementation)
API_KEY = os.environ.get("API_KEY", "")

def verify_api_key(request: Request):
    """Verify API key if configured."""
    if not API_KEY:
        return True

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing API key")

    try:
        scheme, token = auth_header.split()
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid authentication scheme")
        if token != API_KEY:
            raise HTTPException(status_code=401, detail="Invalid API key")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid authorization header format")

    return True

# Request models
class ScrapeRequest(BaseModel):
    url: HttpUrl
    formats: List[str] = Field(default=["html"], description="Formats to return (text, html, raw_html, links, metadata, screenshot)")
    timeout: int = Field(default=30000, description="Timeout in milliseconds")
    waitFor: Optional[Union[int, str]] = Field(default=None, description="Wait for element or time in milliseconds")
    selector: Optional[str] = Field(default=None, description="CSS selector to extract content from")
    headers: Optional[Dict[str, str]] = Field(default=None, description="Custom headers to send with the request")
    mobile: bool = Field(default=False, description="Whether to use mobile user agent")
    stealth: bool = Field(default=False, description="Whether to use stealth mode")
    cache: bool = Field(default=True, description="Whether to use cached results")

    class Config:
        extra = "allow"  # Allow additional fields

class CrawlRequest(BaseModel):
    url: HttpUrl
    formats: List[str] = Field(default=["html"], description="Formats to return (text, html, raw_html, links, metadata, screenshot)")
    maxPages: int = Field(default=10, description="Maximum number of pages to crawl")
    maxDepth: int = Field(default=3, description="Maximum depth of links to follow")
    includePatterns: Optional[List[str]] = Field(default=None, description="URL patterns to include (regex)")
    excludePatterns: Optional[List[str]] = Field(default=None, description="URL patterns to exclude (regex)")
    stayWithinDomain: bool = Field(default=True, description="Whether to stay within the same domain")
    timeout: int = Field(default=30000, description="Timeout in milliseconds")
    waitFor: Optional[Union[int, str]] = Field(default=None, description="Wait for element or time in milliseconds")
    selector: Optional[str] = Field(default=None, description="CSS selector to extract content from")
    headers: Optional[Dict[str, str]] = Field(default=None, description="Custom headers to send with the request")
    mobile: bool = Field(default=False, description="Whether to use mobile user agent")
    stealth: bool = Field(default=False, description="Whether to use stealth mode")
    cache: bool = Field(default=True, description="Whether to use cached results")
    delayBetweenPages: float = Field(default=1.0, description="Delay between page requests in seconds")

    class Config:
        extra = "allow"  # Allow additional fields

# Response models
class ScrapeResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class CrawlResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Dict[str, Any]]] = None  # URL -> content mapping
    meta: Optional[Dict[str, Any]] = None  # Metadata about the crawl
    error: Optional[str] = None

# Simple in-memory cache
cache_store = {}

@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Playwright Scraper API is running"}

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}

@app.post("/api/scrape", response_model=ScrapeResponse)
async def scrape(request: ScrapeRequest, _: bool = Depends(verify_api_key)):
    """
    Scrape a URL using Playwright and return the content in the requested formats.
    """

@app.post("/api/crawl", response_model=CrawlResponse)
async def crawl(request: CrawlRequest, _: bool = Depends(verify_api_key)):
    """
    Crawl a website starting from the given URL, following links up to the specified depth and maximum pages.
    Returns a dictionary mapping URLs to their content in the requested formats.
    """
    logger.info(f"Crawl request for URL: {request.url}")

    # Initialize result
    result = {
        "success": True,
        "data": {},
        "meta": {
            "startUrl": str(request.url),
            "maxPages": request.maxPages,
            "maxDepth": request.maxDepth,
            "crawledPages": 0,
            "startTime": None,
            "endTime": None,
            "elapsedTime": None
        },
        "error": None
    }

    # Track visited URLs and the queue
    visited_urls = set()
    url_queue = []
    url_depths = {}

    # Add the start URL to the queue
    start_url = str(request.url)
    url_queue.append(start_url)
    url_depths[start_url] = 0

    # Import required modules
    import re
    import time
    from urllib.parse import urlparse, urljoin

    # Start timing
    start_time = time.time()
    result["meta"]["startTime"] = start_time
    url = str(request.url)
    logger.info(f"Scraping URL: {url}")

    # Check cache if enabled
    cache_key = f"{url}:{','.join(request.formats)}:{request.mobile}:{request.stealth}"
    if request.cache and cache_key in cache_store:
        logger.info(f"Returning cached result for {url}")
        return cache_store[cache_key]

    try:
        async with async_playwright() as p:
            # Choose browser (chromium is most compatible)
            browser_type = p.chromium

            # Launch browser with appropriate options
            browser_args = []
            if request.stealth:
                browser_args.extend([
                    '--disable-blink-features=AutomationControlled',
                    '--disable-features=IsolateOrigins,site-per-process',
                ])

            browser = await browser_type.launch(headless=True, args=browser_args)

            try:
                # Create context with appropriate options
                context_options = {}

                if request.mobile:
                    context_options["viewport"] = {"width": 375, "height": 812}
                    context_options["user_agent"] = "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1"

                if request.headers:
                    context_options["extra_http_headers"] = request.headers

                context = await browser.new_context(**context_options)

                # Create page and navigate
                page = await context.new_page()

                # Set timeout
                page.set_default_timeout(request.timeout)

                # Navigate to URL
                response = await page.goto(url, wait_until="networkidle")

                # Wait for selector or time if specified
                if request.waitFor:
                    if isinstance(request.waitFor, int):
                        await asyncio.sleep(request.waitFor / 1000)  # Convert to seconds
                    else:
                        await page.wait_for_selector(request.waitFor, state="visible")

                # Process requested formats
                result = {"success": True, "data": {}}

                # Apply selector if specified
                content_handle = page
                if request.selector:
                    try:
                        content_handle = await page.query_selector(request.selector)
                        if not content_handle:
                            logger.warning(f"Selector '{request.selector}' not found")
                            content_handle = page
                    except Exception as e:
                        logger.error(f"Error applying selector: {str(e)}")
                        content_handle = page

                # Extract requested formats
                for fmt in request.formats:
                    try:
                        if fmt == "text":
                            if content_handle == page:
                                # Get the text content of the page (not the HTML content)
                                result["data"]["text"] = await page.evaluate('() => document.body.innerText')
                            else:
                                result["data"]["text"] = await content_handle.evaluate('node => node.innerText')

                        elif fmt == "html":
                            if content_handle == page:
                                result["data"]["html"] = await page.content()
                            else:
                                result["data"]["html"] = await content_handle.evaluate('node => node.outerHTML')

                        elif fmt == "raw_html":
                            if response:
                                result["data"]["raw_html"] = await response.text()
                            else:
                                result["data"]["raw_html"] = await page.content()

                        elif fmt == "links":
                            if content_handle == page:
                                result["data"]["links"] = await page.evaluate('''() => {
                                    return Array.from(document.querySelectorAll('a[href]'))
                                        .map(a => ({
                                            text: a.innerText.trim(),
                                            href: a.href,
                                            title: a.title || null
                                        }))
                                        .filter(link => link.href && link.href.startsWith('http'));
                                }''')
                            else:
                                result["data"]["links"] = await content_handle.evaluate('''node => {
                                    return Array.from(node.querySelectorAll('a[href]'))
                                        .map(a => ({
                                            text: a.innerText.trim(),
                                            href: a.href,
                                            title: a.title || null
                                        }))
                                        .filter(link => link.href && link.href.startsWith('http'));
                                }''')

                        elif fmt == "metadata":
                            try:
                                # Initialize metadata dictionary
                                metadata = {}

                                # Basic metadata
                                metadata["title"] = await page.title()
                                metadata["url"] = page.url

                                # Get canonical link
                                canonical_link = await page.query_selector('link[rel="canonical"]')
                                if canonical_link:
                                    metadata["canonical"] = await canonical_link.get_attribute('href')

                                # Get language
                                html_elem = await page.query_selector('html')
                                if html_elem:
                                    lang = await html_elem.get_attribute('lang')
                                    if lang:
                                        metadata["language"] = lang

                                # Get all meta tags
                                meta_elements = await page.query_selector_all('meta')

                                # Extract all meta tags
                                for meta in meta_elements:
                                    attrs = await page.evaluate('''
                                    (element) => {
                                        const attributes = {};
                                        for (const attr of element.attributes) {
                                            attributes[attr.name] = attr.value;
                                        }
                                        return attributes;
                                    }
                                    ''', meta)

                                    if 'name' in attrs and 'content' in attrs:
                                        # Standard meta tag with name
                                        metadata[attrs['name']] = attrs['content']

                                    elif 'property' in attrs and 'content' in attrs:
                                        # Open Graph or other property-based meta tag
                                        metadata[attrs['property']] = attrs['content']

                                    elif 'charset' in attrs:
                                        # Charset meta tag
                                        metadata['charset'] = attrs['charset']

                                    elif 'http-equiv' in attrs and 'content' in attrs:
                                        # HTTP-equiv meta tag
                                        metadata[f"http_equiv_{attrs['http-equiv']}"] = attrs['content']

                                # Store the metadata
                                result["data"]["metadata"] = metadata

                            except Exception as e:
                                logger.error(f"Error extracting metadata: {str(e)}")
                                # Provide a minimal fallback
                                result["data"]["metadata"] = {
                                    "title": await page.title(),
                                    "url": page.url,
                                    "error": str(e)
                                }

                        elif fmt == "screenshot":
                            screenshot_bytes = await page.screenshot()
                            result["data"]["screenshot"] = base64.b64encode(screenshot_bytes).decode('utf-8')

                    except Exception as e:
                        logger.error(f"Error extracting format '{fmt}': {str(e)}")
                        result["data"][fmt] = None

                # Cache result if caching is enabled
                if request.cache:
                    cache_store[cache_key] = result

                return result

            finally:
                await browser.close()

    except Exception as e:
        logger.error(f"Error scraping URL {url}: {str(e)}")
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    # Run the FastAPI app with uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
