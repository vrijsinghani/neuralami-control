import json
import os
from typing import Dict, List, Any, Optional, Type, Set
from datetime import datetime, timedelta
import logging
import asyncio
import aiohttp
import ssl
from collections import defaultdict
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin, urlunparse
from pydantic import BaseModel, Field
from crewai_tools import BaseTool
import dotenv
from django.core.cache import cache
from apps.agents.tools.browser_tool.browser_tool import BrowserTool
from apps.agents.tools.async_crawl_website_tool.async_crawl_website_tool import AsyncCrawlWebsiteTool
from apps.agents.tools.seo_crawler_tool.seo_crawler_tool import SEOCrawlerTool
from apps.common.utils import normalize_url
from apps.agents.utils import URLDeduplicator

dotenv.load_dotenv()

logger = logging.getLogger(__name__)

class SEOAuditToolSchema(BaseModel):
    """Input for SEOAuditTool."""
    website: str = Field(..., title="Website", description="Full URL of the website to perform SEO audit on (e.g., https://example.com)")
    max_pages: int = Field(
        default=100,
        title="Max Pages",
        description="Maximum number of pages to audit"
    )
    check_external_links: bool = Field(
        default=False,
        title="Check External Links",
        description="Whether to check external links for broken links"
    )
    crawl_delay: float = Field(
        default=1.0,
        title="Crawl Delay",
        description="Delay between crawling pages in seconds"
    )

class SEOAuditTool(BaseTool):
    name: str = "SEO Audit Tool"
    description: str = "A tool that performs comprehensive SEO audit on a website, checking for issues like broken links, duplicate content, meta tag issues, and more."
    args_schema: Type[BaseModel] = SEOAuditToolSchema
    tags: Set[str] = {"seo", "audit", "website", "content"}
    api_key: str = Field(default=os.environ.get('BROWSERLESS_API_KEY'))
    browser_tool: BrowserTool = Field(default_factory=BrowserTool)
    crawl_tool: AsyncCrawlWebsiteTool = Field(default_factory=AsyncCrawlWebsiteTool)
    seo_crawler: SEOCrawlerTool = Field(default_factory=SEOCrawlerTool)
    url_deduplicator: URLDeduplicator = Field(default_factory=URLDeduplicator)

    model_config = {"arbitrary_types_allowed": True}
    
    def __init__(self, **data):
        super().__init__(**data)
        if not self.api_key:
            logger.error("BROWSERLESS_API_KEY is not set in the environment variables.")
        self._session = None
        self._link_cache = {}  # Global cache for link check results
        self._semaphore = None  # Rate limiting semaphore
        self._checked_urls = set()  # Global set of normalized URLs that have been checked

    def _run(
        self,
        website: str,
        max_pages: int = 100,
        check_external_links: bool = False,
        crawl_delay: float = 1.0,
        progress_callback = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Run SEO audit."""
        logger.info(f"Starting SEO audit for: {website}")
        start_time = datetime.now()
        
        # Create event loop and run async audit
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(self._async_audit(
                website=website,
                max_pages=max_pages,
                check_external_links=check_external_links,
                crawl_delay=crawl_delay,
                progress_callback=progress_callback
            ))
            end_time = datetime.now()
            result["summary"]["audit_start_time"] = start_time.isoformat()
            result["summary"]["audit_end_time"] = end_time.isoformat()
            result["summary"]["total_audit_time_seconds"] = (end_time - start_time).total_seconds()
            logger.info(f"SEO audit completed for: {website}")
            return json.loads(json.dumps(result, default=str))  # Ensure JSON serialization
        except Exception as e:
            logger.error(f"Error running SEO audit: {str(e)}")
            raise
        finally:
            loop.close()

    async def _async_audit(
        self,
        website: str,
        max_pages: int = 100,
        check_external_links: bool = False,
        crawl_delay: float = 1.0,
        progress_callback = None
    ) -> Dict[str, Any]:
        """Run SEO audit asynchronously."""
        logger.info("Starting crawler...")
        
        if progress_callback:
            progress_callback({
                'percent_complete': 0,
                'pages_analyzed': 0,
                'issues_found': 0,
                'status': 'Starting crawler...'
            })

        # First, use SEOCrawlerTool to gather detailed page data
        crawler_results = await asyncio.to_thread(
            self.seo_crawler._run,
            website_url=website,
            max_pages=max_pages,
            respect_robots_txt=True,
            crawl_delay=crawl_delay,
            progress_callback=lambda data: progress_callback({
                'percent_complete': int(data.get('percent_complete', 0) * 0.5),  # First 50% for crawling
                'pages_analyzed': data.get('pages_analyzed', 0),
                'issues_found': 0,
                'status': f"Crawling: {data.get('status', '')}"
            }) if progress_callback else None
        )
        pages = crawler_results.get('pages', [])
        total_pages = len(pages)
        logger.info(f"Crawler completed. Found {total_pages} pages")

        if progress_callback:
            progress_callback({
                'percent_complete': 50,
                'pages_analyzed': total_pages,
                'issues_found': 0,
                'status': 'Starting SEO analysis...'
            })

        # Initialize audit results
        audit_results = {
            "broken_links": [],
            "duplicate_content": [],
            "meta_tag_issues": [],
            "ssl_issues": {},
            "sitemap_present": False,
            "robots_txt_present": False,
            "page_analysis": []
        }

        total_links = 0
        all_links = set()
        base_domain = urlparse(website).netloc
        total_issues = 0

        # Process pages for SEO analysis (50-70%)
        for i, page in enumerate(pages):
            page_analysis = await self._analyze_page_seo(page)
            audit_results["page_analysis"].append(page_analysis)
            
            # Collect links
            page_links = page.get("links", [])
            total_links += len(page_links)
            for link in page_links:
                if urlparse(link).netloc == base_domain:
                    all_links.add((page["url"], link))

            # Check meta tags
            meta_issues = []
            
            # Title tag checks
            title = page.get("title", "").strip()
            if not title:
                meta_issues.append({
                    "type": "title",
                    "issue": "Missing title tag",
                    "value": None
                })
            elif len(title) < 10:
                meta_issues.append({
                    "type": "title",
                    "issue": f"Title tag too short ({len(title)} chars)",
                    "value": title
                })
            elif len(title) > 60:
                meta_issues.append({
                    "type": "title",
                    "issue": f"Title tag too long ({len(title)} chars)",
                    "value": title
                })
            
            # Meta description checks
            meta_desc = page.get("meta_description", "").strip()
            if not meta_desc:
                meta_issues.append({
                    "type": "meta_description",
                    "issue": "Missing meta description",
                    "value": None
                })
            elif len(meta_desc) < 50:
                meta_issues.append({
                    "type": "meta_description",
                    "issue": f"Meta description too short ({len(meta_desc)} chars)",
                    "value": meta_desc
                })
            elif len(meta_desc) > 160:
                meta_issues.append({
                    "type": "meta_description",
                    "issue": f"Meta description too long ({len(meta_desc)} chars)",
                    "value": meta_desc
                })
            
            # H1 tag checks
            h1_tags = page.get("h1_tags", [])
            if not h1_tags:
                meta_issues.append({
                    "type": "h1",
                    "issue": "Missing H1 tag",
                    "value": None
                })
            elif len(h1_tags) > 1:
                meta_issues.append({
                    "type": "h1",
                    "issue": f"Multiple H1 tags ({len(h1_tags)})",
                    "value": h1_tags
                })
            
            if meta_issues:
                audit_results["meta_tag_issues"].append({
                    "url": page["url"],
                    "issues": meta_issues
                })
                total_issues += len(meta_issues)

            if progress_callback:
                percent_complete = 50 + ((i + 1) / total_pages * 20)  # 50-70% for page analysis
                progress_callback({
                    'percent_complete': int(percent_complete),
                    'pages_analyzed': i + 1,
                    'issues_found': total_issues,
                    'status': f'Analyzing page {i + 1} of {total_pages}',
                    'recent_issues': meta_issues
                })

        logger.info("Page analysis completed")

        # Check broken links (70-85%)
        if progress_callback:
            progress_callback({
                'percent_complete': 70,
                'pages_analyzed': total_pages,
                'issues_found': total_issues,
                'status': 'Checking broken links...'
            })

        logger.info("Checking for broken links...")
        total_links = len(all_links)
        links_checked = 0
        
        async def check_link_with_progress(source_url: str, target_url: str):
            nonlocal links_checked, total_issues
            result = await self._check_link(source_url, target_url)
            links_checked += 1
            if result and result.get('is_broken'):
                total_issues += 1
                if progress_callback:
                    percent_complete = 70 + (links_checked / total_links * 15)  # 70-85% for link checking
                    progress_callback({
                        'percent_complete': int(percent_complete),
                        'pages_analyzed': total_pages,
                        'issues_found': total_issues,
                        'status': f'Checking links: {links_checked}/{total_links}',
                        'recent_issues': [{
                            'severity': 'critical',
                            'issue_type': 'broken_link',
                            'url': source_url,
                            'details': f"Broken link to {target_url}: {result.get('error', 'Not accessible')}"
                        }]
                    })
            return result

        # Process links in batches
        batch_size = 10
        for i in range(0, len(all_links), batch_size):
            batch = list(all_links)[i:i + batch_size]
            tasks = [check_link_with_progress(source, target) for source, target in batch]
            await asyncio.gather(*tasks)

        # Check duplicate content (85-95%)
        if progress_callback:
            progress_callback({
                'percent_complete': 85,
                'pages_analyzed': total_pages,
                'issues_found': total_issues,
                'status': 'Checking for duplicate content...'
            })

        logger.info("Checking for duplicate content...")
        pages_compared = 0
        total_comparisons = (len(pages) * (len(pages) - 1)) // 2

        for i, page1 in enumerate(pages):
            for j, page2 in enumerate(pages[i + 1:], i + 1):
                similarity = await self._check_content_similarity(page1, page2)
                pages_compared += 1
                
                if similarity > 0.8:  # 80% similarity threshold
                    total_issues += 1
                    audit_results['duplicate_content'].append({
                        'url1': page1['url'],
                        'url2': page2['url'],
                        'similarity': int(similarity * 100)
                    })
                    
                    if progress_callback and pages_compared % 10 == 0:
                        percent_complete = 85 + (pages_compared / total_comparisons * 10)
                        progress_callback({
                            'percent_complete': int(percent_complete),
                            'pages_analyzed': total_pages,
                            'issues_found': total_issues,
                            'status': f'Checking duplicate content: {pages_compared}/{total_comparisons} comparisons'
                        })

        # Final checks (95-100%)
        if progress_callback:
            progress_callback({
                'percent_complete': 95,
                'pages_analyzed': total_pages,
                'issues_found': total_issues,
                'status': 'Performing final checks...'
            })

        logger.info("Checking SSL...")
        await self._check_ssl(website, audit_results)
        
        logger.info("Checking robots.txt and sitemap...")
        await self._check_robots_sitemap(website, audit_results)

        # Add summary stats
        audit_results["summary"] = {
            "total_pages": total_pages,
            "total_links": total_links,
            "total_meta_issues": len(audit_results["meta_tag_issues"]),
            "total_broken_links": len(audit_results["broken_links"]),
            "total_duplicate_content": len(audit_results["duplicate_content"]),
            "start_time": crawler_results["start_time"],
            "end_time": crawler_results["end_time"],
            "crawl_time_seconds": crawler_results["crawl_time_seconds"]
        }

        if progress_callback:
            progress_callback({
                'percent_complete': 100,
                'pages_analyzed': total_pages,
                'issues_found': total_issues,
                'status': 'Completed'
            })
        
        logger.info("SEO audit completed successfully")
        return audit_results

    async def _analyze_page_seo(self, page: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze SEO aspects of a single page."""
        return {
            "url": page["url"],
            "title_length": len(page.get("title", "")),
            "meta_description_length": len(page.get("meta_description", "")),
            "h1_count": len(page.get("h1_tags", [])),
            "outbound_links": len(page.get("links", [])),
            "content_length": len(page.get("text_content", "")),
            "timestamp": page.get("crawl_timestamp")
        }

    async def _check_duplicate_content(self, pages: List[Dict[str, Any]], audit_results: Dict[str, Any]):
        """Check for duplicate content across pages."""
        duplicates = []
        content_hash_map = defaultdict(list)

        for page in pages:
            url = page['url']
            content = page.get('content', '')
            
            # Use URLDeduplicator's content check
            if self.url_deduplicator.fallback_content_check(url, content):
                normalized_url = self.url_deduplicator._normalize_url(url)
                content_hash = self.url_deduplicator._hash_main_content(content)
                if normalized_url not in content_hash_map[content_hash]:
                    content_hash_map[content_hash].append(normalized_url)
        
        for urls in content_hash_map.values():
            if len(urls) > 1:  # Only report if we have actual duplicates (different URLs)
                # Sort URLs for consistent output
                sorted_urls = sorted(urls)
                audit_results["duplicate_content"].append({
                    "urls": sorted_urls,
                    "timestamp": datetime.now().isoformat()
                })

    async def _check_ssl(self, website: str, audit_results: Dict[str, Any]):
        """Check SSL certificate validity."""
        try:
            context = ssl.create_default_context()
            async with aiohttp.TCPConnector(ssl=context) as connector:
                async with aiohttp.ClientSession(connector=connector) as session:
                    async with session.get(f"https://{website}") as response:
                        audit_results["ssl_issues"] = {"valid_certificate": response.status == 200}
        except Exception:
            audit_results["ssl_issues"] = {"valid_certificate": False}

    async def _check_robots_sitemap(self, website: str, audit_results: Dict[str, Any]):
        """Check for robots.txt and sitemap.xml."""
        async with aiohttp.ClientSession() as session:
            # Check robots.txt
            try:
                async with session.get(f"https://{website}/robots.txt") as response:
                    audit_results["robots_txt_present"] = response.status == 200
            except Exception:
                audit_results["robots_txt_present"] = False
            
            # Check sitemap.xml
            try:
                async with session.get(f"https://{website}/sitemap.xml") as response:
                    audit_results["sitemap_present"] = response.status == 200
            except Exception:
                audit_results["sitemap_present"] = False

    async def _check_broken_links(self, links: Set[tuple], audit_results: Dict[str, Any]):
        """Check for broken internal links using HEAD requests with caching."""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
        }
        
        async with aiohttp.ClientSession(headers=headers) as session:
            semaphore = asyncio.Semaphore(5)  # Allow more concurrent requests since HEAD is lightweight
            
            async def check_link(source_url: str, target_url: str):
                """Check if a link is broken using HEAD request with caching."""
                async with semaphore:
                    # Generate cache key
                    cache_key = f"link_status:{target_url}"
                    cached_result = cache.get(cache_key)
                    
                    if cached_result is not None:
                        # If link was broken in cache, add to audit results
                        if cached_result.get('is_broken', False):
                            audit_results["broken_links"].append({
                                "source_url": source_url,
                                "target_url": target_url,
                                "status_code": cached_result.get('status_code'),
                                "error": cached_result.get('error'),
                                "timestamp": datetime.now().isoformat()
                            })
                        return
                    
                    max_retries = 3
                    retry_count = 0
                    
                    while retry_count < max_retries:
                        try:
                            # Try HEAD first
                            try:
                                async with session.head(target_url, allow_redirects=True, timeout=5) as response:
                                    # If HEAD request is successful (status < 400), cache and return
                                    if response.status < 400:
                                        cache.set(cache_key, {
                                            'is_broken': False,
                                            'status_code': response.status,
                                            'checked_at': datetime.now().isoformat()
                                        }, timeout=86400)
                                        return
                                        
                                    # If HEAD fails, try GET
                                    async with session.get(target_url, allow_redirects=True, timeout=5) as get_response:
                                        result = {
                                            'is_broken': get_response.status >= 400,
                                            'status_code': get_response.status,
                                            'error': f"HTTP {get_response.status}" if get_response.status >= 400 else None,
                                            'checked_at': datetime.now().isoformat()
                                        }
                                        cache.set(cache_key, result, timeout=86400)
                                        
                                        if result['is_broken']:
                                            audit_results["broken_links"].append({
                                                "source_url": source_url,
                                                "target_url": target_url,
                                                "status_code": get_response.status,
                                                "error": f"HTTP {get_response.status}",
                                                "timestamp": datetime.now().isoformat()
                                            })
                                        return
                                        
                            except aiohttp.ClientError:
                                # If HEAD fails with client error, try GET
                                async with session.get(target_url, allow_redirects=True, timeout=5) as response:
                                    result = {
                                        'is_broken': response.status >= 400,
                                        'status_code': response.status,
                                        'error': f"HTTP {response.status}" if response.status >= 400 else None,
                                        'checked_at': datetime.now().isoformat()
                                    }
                                    cache.set(cache_key, result, timeout=86400)
                                    
                                    if result['is_broken']:
                                        audit_results["broken_links"].append({
                                            "source_url": source_url,
                                            "target_url": target_url,
                                            "status_code": response.status,
                                            "error": f"HTTP {response.status}",
                                            "timestamp": datetime.now().isoformat()
                                        })
                                    return
                            
                        except asyncio.TimeoutError:
                            retry_count += 1
                            if retry_count == max_retries:
                                result = {
                                    'is_broken': True,
                                    'status_code': None,
                                    'error': f"Timeout after {max_retries} retries",
                                    'checked_at': datetime.now().isoformat()
                                }
                                cache.set(cache_key, result, timeout=86400)
                                
                                audit_results["broken_links"].append({
                                    "source_url": source_url,
                                    "target_url": target_url,
                                    "status_code": None,
                                    "error": f"Timeout after {max_retries} retries",
                                    "timestamp": datetime.now().isoformat()
                                })
                            else:
                                await asyncio.sleep(1)  # Wait before retrying
                                continue
                                
                        except Exception as e:
                            result = {
                                'is_broken': True,
                                'status_code': None,
                                'error': str(e),
                                'checked_at': datetime.now().isoformat()
                            }
                            cache.set(cache_key, result, timeout=86400)
                            
                            audit_results["broken_links"].append({
                                "source_url": source_url,
                                "target_url": target_url,
                                "status_code": None,
                                "error": str(e),
                                "timestamp": datetime.now().isoformat()
                            })
                            return
            
            # Process links in smaller batches
            batch_size = 50
            all_links = list(links)
            for i in range(0, len(all_links), batch_size):
                batch = all_links[i:i + batch_size]
                tasks = []
                for source_url, target_url in batch:
                    tasks.append(asyncio.create_task(check_link(source_url, target_url)))
                
                if tasks:
                    await asyncio.gather(*tasks)
                    # Add a small delay between batches to prevent overwhelming
                    await asyncio.sleep(1)

    def _generate_report(self, audit_results: Dict[str, Any]) -> Dict[str, Any]:
        """Format the audit results into a detailed report."""
        total_meta_issues = len(audit_results["meta_tag_issues"])
        
        report = {
            "summary": {
                "total_pages": audit_results["summary"]["total_pages"],
                "total_issues": len(audit_results["broken_links"]) + 
                              len(audit_results["duplicate_content"]) + 
                              total_meta_issues,
                "timestamp": datetime.now().isoformat()
            },
            "issues": {
                "broken_links": audit_results["broken_links"],
                "duplicate_content": audit_results["duplicate_content"],
                "meta_tag_issues": audit_results["meta_tag_issues"]
            },
            "technical": {
                "ssl": audit_results["ssl_issues"],
                "sitemap": audit_results["sitemap_present"],
                "robots_txt": audit_results["robots_txt_present"]
            },
            "crawl_stats": {
                "total_pages": audit_results["summary"]["total_pages"],
                "total_links": audit_results["summary"]["total_links"],
                "crawl_time": audit_results["summary"]["crawl_time_seconds"]
            },
            "page_analysis": audit_results["page_analysis"]
        }
        
        return report

    async def _check_link(self, source_url: str, target_url: str) -> Dict[str, Any]:
        """Check if a link is broken using HEAD/GET requests with retries."""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
        }
        
        # Generate cache key
        cache_key = f"link_status:{target_url}"
        cached_result = cache.get(cache_key)
        
        if cached_result is not None:
            return cached_result
        
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                async with aiohttp.ClientSession(headers=headers) as session:
                    # Try HEAD first
                    try:
                        async with session.head(target_url, allow_redirects=True, timeout=5) as response:
                            # If HEAD request is successful (status < 400), cache and return
                            if response.status < 400:
                                result = {
                                    'is_broken': False,
                                    'status_code': response.status,
                                    'error': None,
                                    'checked_at': datetime.now().isoformat()
                                }
                                cache.set(cache_key, result, timeout=86400)  # Cache for 24 hours
                                return result
                                
                            # If HEAD fails, try GET
                            async with session.get(target_url, allow_redirects=True, timeout=5) as get_response:
                                result = {
                                    'is_broken': get_response.status >= 400,
                                    'status_code': get_response.status,
                                    'error': f"HTTP {get_response.status}" if get_response.status >= 400 else None,
                                    'checked_at': datetime.now().isoformat()
                                }
                                cache.set(cache_key, result, timeout=86400)
                                return result
                                
                    except aiohttp.ClientError:
                        # If HEAD fails with client error, try GET
                        async with session.get(target_url, allow_redirects=True, timeout=5) as response:
                            result = {
                                'is_broken': response.status >= 400,
                                'status_code': response.status,
                                'error': f"HTTP {response.status}" if response.status >= 400 else None,
                                'checked_at': datetime.now().isoformat()
                            }
                            cache.set(cache_key, result, timeout=86400)
                            return result
                    
            except asyncio.TimeoutError:
                retry_count += 1
                if retry_count == max_retries:
                    result = {
                        'is_broken': True,
                        'status_code': None,
                        'error': f"Timeout after {max_retries} retries",
                        'checked_at': datetime.now().isoformat()
                    }
                    cache.set(cache_key, result, timeout=86400)
                    return result
                else:
                    await asyncio.sleep(1)  # Wait before retrying
                    continue
                    
            except Exception as e:
                result = {
                    'is_broken': True,
                    'status_code': None,
                    'error': str(e),
                    'checked_at': datetime.now().isoformat()
                }
                cache.set(cache_key, result, timeout=86400)
                return result

        # Should never reach here, but just in case
        return {
            'is_broken': True,
            'status_code': None,
            'error': 'Unknown error',
            'checked_at': datetime.now().isoformat()
        }

    async def _check_content_similarity(self, page1: Dict[str, Any], page2: Dict[str, Any]) -> float:
        """Check content similarity between two pages."""
        from difflib import SequenceMatcher
        
        # Get text content
        text1 = page1.get('text_content', '')
        text2 = page2.get('text_content', '')
        
        # Use SequenceMatcher for similarity ratio
        return SequenceMatcher(None, text1, text2).ratio()
