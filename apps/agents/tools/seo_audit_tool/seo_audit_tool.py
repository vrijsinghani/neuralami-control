import json
import os
from typing import Dict, List, Any, Optional, Type, Set
from datetime import datetime
import logging
import asyncio
import aiohttp
import ssl
from collections import defaultdict
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from pydantic import BaseModel, Field
from apps.agents.tools.base_tool import BaseTool
import dotenv
from django.core.cache import cache
import re

from apps.agents.tools.crawl_website_tool.crawl_website_tool import CrawlWebsiteTool
from apps.agents.tools.seo_crawler_tool.seo_crawler_tool import SEOCrawlerTool
from apps.common.utils import normalize_url
from apps.agents.utils import URLDeduplicator
from .seo_checkers import SEOChecker
from apps.agents.tools.pagespeed_tool.pagespeed_tool import PageSpeedTool

dotenv.load_dotenv()
logger = logging.getLogger(__name__)

class SEOAuditToolSchema(BaseModel):
    """Input for SEOAuditTool."""
    website: str = Field(
        ..., 
        title="Website", 
        description="Full URL of the website to perform SEO audit on",
        json_schema_extra={"example": "https://example.com"}
    )
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
    description: str = "A tool that performs comprehensive SEO audit on a website, checking for issues like broken links, duplicate content, meta tag issues, images, and more."
    args_schema: Type[BaseModel] = SEOAuditToolSchema
    tags: Set[str] = {"seo", "audit", "website", "content"}
    api_key: str = Field(default=os.environ.get('BROWSERLESS_API_KEY'))
    crawl_tool: CrawlWebsiteTool = Field(default_factory=CrawlWebsiteTool)
    seo_crawler: SEOCrawlerTool = Field(default_factory=SEOCrawlerTool)
    url_deduplicator: URLDeduplicator = Field(default_factory=URLDeduplicator)
    checker: SEOChecker = Field(default_factory=SEOChecker)
    pagespeed_tool: PageSpeedTool = Field(default_factory=PageSpeedTool)

    model_config = {"arbitrary_types_allowed": True}
    
    def __init__(self, **data):
        super().__init__(**data)
        if not self.api_key:
            logger.error("BROWSERLESS_API_KEY is not set in the environment variables.")
        self._session = None
        self._link_cache = {}
        self._semaphore = None
        self._checked_urls = set()

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
            if 'summary' not in result:
                result['summary'] = {}
            result['summary'].update({
                'audit_start_time': start_time.isoformat(),
                'audit_end_time': end_time.isoformat(),
                'start_time': start_time.isoformat(),  # For compatibility
                'end_time': end_time.isoformat(),      # For compatibility
                'total_audit_time_seconds': (end_time - start_time).total_seconds()
            })
            logger.info(f"SEO audit completed for: {website}")
            return json.loads(json.dumps(result, default=str))
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

        total_issues = 0  # Initialize total_issues at the module level
        audit_results = {
            "broken_links": [],
            "duplicate_content": [],
            "meta_tag_issues": [],
            "image_issues": [],
            "content_issues": [],
            "ssl_issues": {},
            "sitemap_present": False,
            "robots_txt_present": False,
            "page_analysis": []
        }

        last_progress_data = {}
        all_links = set()
        base_domain = urlparse(website).netloc

        def page_callback(page_data):
            nonlocal total_issues, last_progress_data
            
            # Check meta tags
            meta_issues = self.checker.check_meta_tags(page_data)
            if meta_issues:
                audit_results["meta_tag_issues"].extend(meta_issues)
                total_issues += len(meta_issues)
            
            # Check headings
            heading_issues = self.checker.check_headings(page_data)
            if heading_issues:
                audit_results["heading_issues"] = audit_results.get("heading_issues", [])
                audit_results["heading_issues"].extend(heading_issues)
                total_issues += len(heading_issues)
            
            # Check images
            image_issues = self.checker.check_images(page_data)
            if image_issues:
                audit_results["image_issues"] = audit_results.get("image_issues", [])
                audit_results["image_issues"].extend(image_issues)
                total_issues += len(image_issues)
            
            # Check content
            content_issues = self.checker.check_content(page_data)
            if content_issues:
                audit_results["content_issues"] = audit_results.get("content_issues", [])
                audit_results["content_issues"].extend(content_issues)
                total_issues += len(content_issues)

            # Check social media tags
            social_media_issues = self.checker.check_social_media_tags(page_data)
            if social_media_issues:
                audit_results["social_media_issues"] = audit_results.get("social_media_issues", [])
                audit_results["social_media_issues"].extend(social_media_issues)
                total_issues += len(social_media_issues)

            # Check canonical tags
            canonical_issues = self.checker.check_canonical_tags(page_data)
            if canonical_issues:
                audit_results["canonical_issues"] = audit_results.get("canonical_issues", [])
                audit_results["canonical_issues"].extend(canonical_issues)
                total_issues += len(canonical_issues)

            # Add semantic structure checks
            semantic_issues = self.checker.check_semantic_structure(page_data)
            if semantic_issues:
                audit_results["semantic_issues"] = audit_results.get("semantic_issues", [])
                audit_results["semantic_issues"].extend(semantic_issues)
                total_issues += len(semantic_issues)

            # Add robots indexing checks
            robots_issues = self.checker.check_robots_indexing(page_data)
            if robots_issues:
                audit_results["robots_issues"] = audit_results.get("robots_issues", [])
                audit_results["robots_issues"].extend(robots_issues)
                total_issues += len(robots_issues)

            # Add E-E-A-T signal checks
            eeat_issues = self.checker.check_eeat_signals(page_data)
            if eeat_issues:
                audit_results["eeat_issues"] = audit_results.get("eeat_issues", [])
                audit_results["eeat_issues"].extend(eeat_issues)
                total_issues += len(eeat_issues)

            # Add redirect chain checks
            redirect_issues = self.checker.check_redirect_chains(page_data)
            if redirect_issues:
                audit_results["redirect_issues"] = audit_results.get("redirect_issues", [])
                audit_results["redirect_issues"].extend(redirect_issues)
                total_issues += len(redirect_issues)
            
            # Collect internal links
            internal_links = self.checker.check_links(page_data, base_domain)
            for link in internal_links:
                all_links.add((page_data["url"], link))
            
            # Update progress data with all issues
            all_issues = []
            for issue_type, issues in audit_results.items():
                if issue_type.endswith('_issues'):
                    for issue in issues:
                        all_issues.append({
                            'severity': issue.get('severity', 'medium'),
                            'issue_type': issue.get('type'),
                            'url': issue.get('url'),
                            'details': issue.get('issue'),
                            'value': issue.get('value'),
                            'additional_details': issue.get('details', {})
                        })
            
            if all_issues:
                last_progress_data['recent_issues'] = all_issues
                last_progress_data['status'] = f"Found {len(all_issues)} issues on {page_data['url']}"
            
            # Add page metrics
            audit_results["page_analysis"].append(
                self.checker.get_page_metrics(page_data)
            )

        # Modify crawler call to use page callback
        def wrapped_progress_callback(data):
            if progress_callback:
                update_data = {
                    'percent_complete': int(data.get('percent_complete', 0) * 0.7),  # First 70% for crawling
                    'pages_analyzed': data.get('pages_analyzed', 0),
                    'issues_found': total_issues,  # Now using the correct total_issues
                    'status': last_progress_data.get('status', f"Analyzing: {data.get('status', '')}")
                }
                if 'recent_issues' in last_progress_data:
                    update_data['recent_issues'] = last_progress_data['recent_issues']
                    last_progress_data.clear()  # Clear after sending
                progress_callback(update_data)

        # Create a wrapper for the page callback that ensures it's called for each page
        def wrapped_page_callback(page):
            page_data = {
                "url": page.url,
                "title": page.title,
                "meta_description": page.meta_description,
                "h1_tags": page.h1_tags,
                "links": page.links,
                "text_content": page.text_content,
                "crawl_timestamp": page.crawl_timestamp,
                "status_code": page.status_code,
                "canonical_url": getattr(page, 'canonical_url', None),
                "canonical_count": len(page.canonical_tags) if hasattr(page, 'canonical_tags') else 0,
                "is_pagination": bool(page.pagination_info) if hasattr(page, 'pagination_info') else False,
                "canonical_chain": page.canonical_chain if hasattr(page, 'canonical_chain') else [],
                # Add semantic structure data
                "has_semantic_markup": getattr(page, 'has_semantic_markup', False),
                "has_header": getattr(page, 'has_header', False),
                "has_nav": getattr(page, 'has_nav', False),
                "has_main": getattr(page, 'has_main', False),
                "has_footer": getattr(page, 'has_footer', False),
                "semantic_nesting_issues": getattr(page, 'semantic_nesting_issues', []),
                "empty_semantic_elements": getattr(page, 'empty_semantic_elements', []),
                "page_type": getattr(page, 'page_type', 'content'),
                # Add robots indexing data
                "noindex": getattr(page, 'noindex', False),
                "noindex_source": getattr(page, 'noindex_source', None),
                "noindex_intentional": getattr(page, 'noindex_intentional', False),
                "x_robots_tag": getattr(page, 'x_robots_tag', None),
                "robots_blocked": getattr(page, 'robots_blocked', False),
                "robots_directive": getattr(page, 'robots_directive', None),
                "robots_user_agent": getattr(page, 'robots_user_agent', '*'),
                # Add E-E-A-T data
                "has_author": getattr(page, 'has_author', False),
                "author_info": getattr(page, 'author_info', None),
                "has_expertise": getattr(page, 'has_expertise', False),
                "expertise_indicators": getattr(page, 'expertise_indicators', []),
                "has_factual_accuracy": getattr(page, 'has_factual_accuracy', False),
                "factual_accuracy_indicators": getattr(page, 'factual_accuracy_indicators', []),
                "content_type": getattr(page, 'content_type', None),
                # Add redirect chain data
                "redirect_chain": getattr(page, 'redirect_chain', []),
                "meta_refresh": getattr(page, 'meta_refresh', False),
                "meta_refresh_url": getattr(page, 'meta_refresh_url', None),
                "meta_refresh_delay": getattr(page, 'meta_refresh_delay', None)
            }
            page_callback(page_data)
            return page

        crawler_results = await asyncio.to_thread(
            self.seo_crawler._run,
            website_url=website,
            max_pages=max_pages,
            respect_robots_txt=True,
            crawl_delay=crawl_delay,
            page_callback=wrapped_page_callback,
            progress_callback=wrapped_progress_callback
        )
        pages = crawler_results.get('pages', [])
        total_pages = len(pages)
        logger.info(f"Crawler completed. Found {total_pages} pages")

        # Check broken links (70-85%)
        if progress_callback:
            progress_callback({
                'percent_complete': 70,
                'pages_analyzed': total_pages,
                'issues_found': total_issues,
                'status': 'Checking broken links...'
            })

        logger.info("Checking for broken links...")
        await self._check_broken_links(all_links, audit_results)
        total_issues += len(audit_results["broken_links"])
        logger.info(f"Found {len(audit_results['broken_links'])} broken links")

        # Check duplicate content (85-95%)
        if progress_callback:
            progress_callback({
                'percent_complete': 75,
                'pages_analyzed': total_pages,
                'issues_found': total_issues,
                'status': 'Checking for duplicate content...'
            })

        logger.info("Checking for duplicate content...")
        # Filter out 404 pages before duplicate content check
        valid_pages = [page for page in pages if not self.checker.is_404_page(page)]
        logger.info(f"Found {len(pages) - len(valid_pages)} potential 404 pages out of {len(pages)} total pages")

        # Add 404 pages as issues
        for page in pages:
            if self.checker.is_404_page(page):
                audit_results["meta_tag_issues"].append({
                    "url": page["url"],
                    "issues": [{
                        "type": "404",
                        "issue": "Page returns 404 status or appears to be a 404 page",
                        "value": None,
                        "severity": "high"
                    }]
                })
                total_issues += 1

        # Check duplicate content
        content_map = defaultdict(list)
        for page in valid_pages:
            content = page.get('text_content', '').strip()
            if content:
                content_hash = hash(content)
                content_map[content_hash].append(page['url'])
        
        for urls in content_map.values():
            if len(urls) > 1:
                audit_results["duplicate_content"].append({
                    "urls": urls,
                    "similarity": 100,
                    "timestamp": datetime.now().isoformat()
                })
                total_issues += 1

        logger.info(f"Found {len(audit_results['duplicate_content'])} duplicate content issues")

        if progress_callback:
            progress_callback({
                'percent_complete': 80,
                'pages_analyzed': total_pages,
                'issues_found': total_issues,
                'status': 'Checking SSL, robots.txt and sitemap...'
            })

        logger.info("Checking SSL...")
        await self._check_ssl(website, audit_results)
        
        logger.info("Checking robots.txt and sitemap...")
        sitemap_issues = await self._check_robots_sitemap(website, audit_results)
        total_issues += sitemap_issues

        if progress_callback:
            progress_callback({
                'percent_complete': 85,
                'pages_analyzed': total_pages,
                'issues_found': total_issues,
                'status': 'Checking PageSpeed metrics...'
            })

        logger.info("Checking PageSpeed metrics for main URL...")
        pagespeed_issues = await self.checker.check_pagespeed_metrics(
            {"url": website}, 
            self.pagespeed_tool
        )

        if pagespeed_issues:
            if "performance_issues" not in audit_results:
                audit_results["performance_issues"] = []
            audit_results["performance_issues"].extend(pagespeed_issues)
            total_issues += len(pagespeed_issues)

        logger.info(f"Found {len(pagespeed_issues)} PageSpeed issues")

        if progress_callback:
            progress_callback({
                'percent_complete': 100,
                'pages_analyzed': total_pages,
                'issues_found': total_issues,
                'status': 'Completed',
                'recent_issues': [{
                    'severity': issue.get('severity', 'high'),
                    'issue_type': issue.get('type', 'sitemap_issue'),
                    'url': issue.get('url', ''),
                    'details': issue.get('issue', ''),
                    'value': issue.get('value', '')
                } for issue in audit_results.get("sitemap", {}).get("issues", [])]
            })

        # Add PageSpeed analysis for the main URL

        # Add summary stats
        audit_results["summary"] = {
            "total_pages": total_pages,
            "total_links": len(all_links),
            "total_issues": total_issues,
            "start_time": crawler_results["start_time"],
            "end_time": crawler_results["end_time"],
            "crawl_time_seconds": crawler_results["crawl_time_seconds"],
            "duration": (datetime.fromisoformat(crawler_results["end_time"]) - 
                        datetime.fromisoformat(crawler_results["start_time"])).total_seconds()
        }

        # Flatten all issues into a single list
        all_issues = []

        # Add all issues from each category
        for issue in audit_results.get('meta_tag_issues', []):
            all_issues.append(issue)
        for issue in audit_results.get('content_issues', []):
            all_issues.append(issue)
        for issue in audit_results.get('image_issues', []):
            all_issues.append(issue)
        for issue in audit_results.get('broken_links', []):
            all_issues.append(issue)
        for issue in audit_results.get('duplicate_content', []):
            all_issues.append(issue)
        for issue in audit_results.get('canonical_issues', []):
            all_issues.append(issue)
        for issue in audit_results.get('social_media_issues', []):
            all_issues.append(issue)
        for issue in audit_results.get('sitemap', {}).get('issues', []):
            all_issues.append(issue)
        for issue in audit_results.get('performance_issues', []):
            all_issues.append(issue)
        for issue in audit_results.get('semantic_issues', []):
            all_issues.append(issue)
        for issue in audit_results.get('robots_issues', []):
            all_issues.append(issue)
        for issue in audit_results.get('eeat_issues', []):
            all_issues.append(issue)
        for issue in audit_results.get('redirect_issues', []):
            all_issues.append(issue)

        # Add SSL issues
        ssl_results = audit_results.get('ssl_issues', {})
        if ssl_results and ssl_results.get('errors'):
            all_issues.extend(ssl_results['errors'])

        # Replace individual issue lists with a single flattened list
        audit_results['issues'] = all_issues

        logger.info("SEO audit completed successfully")

        return audit_results

    async def _check_ssl(self, website: str, audit_results: Dict[str, Any]):
        """Check SSL certificate validity and configuration."""
        # Ensure we have a proper URL
        if not website.startswith(('http://', 'https://')):
            website = f'https://{website}'
        
        parsed_url = urlparse(website)
        hostname = parsed_url.netloc
        
        ssl_results = {
            "valid_certificate": False,
            "supports_https": False,
            "errors": [],
            "certificate_info": {}
        }
        
        try:
            # Create SSL context with strict verification
            context = ssl.create_default_context()
            context.check_hostname = True
            context.verify_mode = ssl.CERT_REQUIRED
            
            async with aiohttp.TCPConnector(ssl=context) as connector:
                async with aiohttp.ClientSession(connector=connector) as session:
                    try:
                        async with session.get(f"https://{hostname}", timeout=10) as response:
                            ssl_results["supports_https"] = True
                            ssl_results["valid_certificate"] = True
                            
                            # Get certificate info if available
                            if response.connection and response.connection.transport:
                                ssl_object = response.connection.transport.get_extra_info('ssl_object')
                                if ssl_object:
                                    cert = ssl_object.getpeercert()
                                    if cert:
                                        ssl_results["certificate_info"] = {
                                            "subject": dict(x[0] for x in cert.get('subject', [])),
                                            "issuer": dict(x[0] for x in cert.get('issuer', [])),
                                            "version": cert.get('version'),
                                            "expires": cert.get('notAfter'),
                                            "valid_from": cert.get('notBefore')
                                        }
                    
                    except aiohttp.ClientConnectorCertificateError as e:
                        ssl_results["errors"].append(self.checker.create_issue(
                            issue_type="ssl_error",
                            issue="SSL Certificate Error",
                            url=website,
                            value=str(e),
                            severity="critical",
                            details={"error_type": "certificate_error"}
                        ))
                        ssl_results["valid_certificate"] = False
                    
                    except aiohttp.ClientConnectorSSLError as e:
                        ssl_results["errors"].append(self.checker.create_issue(
                            issue_type="ssl_error",
                            issue="SSL Connection Error",
                            url=website,
                            value=str(e),
                            severity="critical",
                            details={"error_type": "ssl_connection_error"}
                        ))
                        ssl_results["valid_certificate"] = False
                    
                    except aiohttp.ClientError as e:
                        ssl_results["errors"].append(self.checker.create_issue(
                            issue_type="ssl_error",
                            issue="Connection Error",
                            url=website,
                            value=str(e),
                            severity="high",
                            details={"error_type": "connection_error"}
                        ))
                        ssl_results["valid_certificate"] = False
            
            # Try HTTP fallback to check if HTTPS is supported
            if not ssl_results["supports_https"]:
                try:
                    async with aiohttp.TCPConnector(ssl=False) as connector:
                        async with aiohttp.ClientSession(connector=connector) as session:
                            async with session.get(f"http://{hostname}", timeout=10) as response:
                                if response.status == 200:
                                    ssl_results["errors"].append(self.checker.create_issue(
                                        issue_type="ssl_error",
                                        issue="Site accessible over HTTP but not HTTPS",
                                        url=website,
                                        value=None,
                                        severity="critical",
                                        details={"supports_http": True, "supports_https": False}
                                    ))
                except Exception:
                    ssl_results["errors"].append(self.checker.create_issue(
                        issue_type="ssl_error",
                        issue="Site not accessible over HTTP or HTTPS",
                        url=website,
                        value=None,
                        severity="critical",
                        details={"supports_http": False, "supports_https": False}
                    ))
        
        except Exception as e:
            ssl_results["errors"].append(self.checker.create_issue(
                issue_type="ssl_error",
                issue="Unexpected error during SSL check",
                url=website,
                value=str(e),
                severity="high",
                details={"error_type": type(e).__name__}
            ))
            ssl_results["valid_certificate"] = False
        
        audit_results["ssl_issues"] = ssl_results

    async def _check_robots_sitemap(self, website: str, audit_results: Dict[str, Any]):
        """Check for robots.txt and sitemap.xml with detailed validation."""
        base_url = f"https://{urlparse(website).netloc}"
        
        # Check robots.txt
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{base_url}/robots.txt") as response:
                    audit_results["robots_txt"] = {
                        "present": response.status == 200,
                        "status_code": response.status
                    }
                    if response.status == 200:
                        content = await response.text()
                        audit_results["robots_txt"]["content"] = content
                        # Check for sitemap directive
                        sitemap_matches = re.findall(r'Sitemap:\s*(.+)', content, re.IGNORECASE)
                        audit_results["robots_txt"]["sitemap_directives"] = sitemap_matches
        except Exception as e:
            audit_results["robots_txt"] = {
                "present": False,
                "error": str(e)
            }
        
        # Perform detailed sitemap validation
        logger.info("Performing detailed sitemap validation...")
        sitemap_validation = await self.checker.validate_sitemap(base_url)
        
        # Add sitemap validation results to audit results
        audit_results["sitemap"] = {
            "present": sitemap_validation["sitemap_found"],
            "type": sitemap_validation["sitemap_type"],
            "total_urls": sitemap_validation["total_urls"],
            "valid_urls": sitemap_validation["valid_urls"],
            "urls_with_lastmod": sitemap_validation["last_modified_dates"],
            "urls_with_changefreq": sitemap_validation["change_frequencies"],
            "urls_with_priority": sitemap_validation["priorities"],
            "sitemap_locations": sitemap_validation["sitemap_locations"],
            "issues": sitemap_validation["issues"]
        }
        
        # Add sitemap issues to total issues count
        return len(sitemap_validation["issues"])

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
        # Calculate total issues
        total_issues = (
            len(audit_results.get("broken_links", [])) +
            len(audit_results.get("duplicate_content", [])) +
            len(audit_results.get("meta_tag_issues", [])) +
            len(audit_results.get("image_issues", [])) +
            len(audit_results.get("content_issues", [])) +
            len(audit_results.get("performance_issues", [])) +
            len(audit_results.get("mobile_issues", [])) +
            len(audit_results.get("social_media_issues", [])) +
            len(audit_results.get("canonical_issues", [])) +
            len(audit_results.get("sitemap", {}).get("issues", [])) +  # Include sitemap issues
            len([issue for issue in audit_results.get("ssl_issues", {}).get("errors", [])])  # Include SSL issues
        )
        
        report = {
            "summary": {
                "total_pages": audit_results["summary"]["total_pages"],
                "total_issues": total_issues,
                "timestamp": datetime.now().isoformat(),
                "canonical_stats": audit_results["summary"].get("canonical_stats", {}),
                "social_media_stats": {
                    "pages_with_og_tags": sum(1 for page in audit_results.get("social_media_issues", []) 
                        if not any(issue["type"].startswith("og_") for issue in page.get("issues", []))),
                    "pages_with_twitter_cards": sum(1 for page in audit_results.get("social_media_issues", [])
                        if not any(issue["type"].startswith("twitter_") for issue in page.get("issues", [])))
                }
            },
            "issues": {
                # Core issues
                "broken_links": audit_results.get("broken_links", []),
                "duplicate_content": audit_results.get("duplicate_content", []),
                "meta_tag_issues": audit_results.get("meta_tag_issues", []),
                
                # Content and structure issues
                "content_issues": audit_results.get("content_issues", []),
                "heading_issues": audit_results.get("heading_issues", []),
                "canonical_issues": audit_results.get("canonical_issues", []),
                
                # Media issues
                "image_issues": audit_results.get("image_issues", []),
                
                # Performance issues
                "performance_issues": audit_results.get("performance_issues", []),
                "page_speed_issues": audit_results.get("page_speed_issues", []),
                
                # Mobile issues
                "mobile_issues": audit_results.get("mobile_issues", []),
                "viewport_issues": audit_results.get("viewport_issues", []),
                
                # Social media issues
                "social_media_issues": audit_results.get("social_media_issues", []),
                "opengraph_issues": [
                    issue for page in audit_results.get("social_media_issues", [])
                    for issue in page.get("issues", []) if issue["type"].startswith("og_")
                ],
                "twitter_card_issues": [
                    issue for page in audit_results.get("social_media_issues", [])
                    for issue in page.get("issues", []) if issue["type"].startswith("twitter_")
                ],
                
                # Technical issues
                "sitemap_issues": audit_results.get("sitemap", {}).get("issues", []),
                "ssl_issues": [{"type": "ssl_error", "issue": error} for error in audit_results.get("ssl_issues", {}).get("errors", [])]
            },
            "technical": {
                # SSL and security
                "ssl": audit_results.get("ssl_issues", {}),
                "security_headers": audit_results.get("security_headers", {}),
                
                # Core technical aspects
                "sitemap": audit_results.get("sitemap", {}),  # Include full sitemap data
                "robots_txt": audit_results.get("robots_txt", {}),  # Include full robots.txt data
                "structured_data": audit_results.get("structured_data_validation", {}),
                "hreflang": audit_results.get("hreflang_validation", {}),
                
                # Mobile technical aspects
                "mobile_friendly": audit_results.get("mobile_friendly", False),
                "mobile_usability": audit_results.get("mobile_usability", {})
            },
            "crawl_stats": {
                "total_pages": audit_results["summary"]["total_pages"],
                "total_links": audit_results["summary"]["total_links"],
                "crawl_time": audit_results["summary"].get("crawl_time_seconds", 0),
                "average_page_load": audit_results["summary"].get("average_page_load", 0)
            },
            "page_analysis": audit_results.get("page_analysis", {})
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
