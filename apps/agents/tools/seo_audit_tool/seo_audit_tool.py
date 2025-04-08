import json
import os
from typing import Dict, List, Any, Optional, Type, Set, Union
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

from apps.agents.tools.web_crawler_tool.web_crawler_tool import WebCrawlerTool, UnifiedWebCrawler, CrawlMode
from apps.agents.tools.sitemap_retriever_tool.sitemap_retriever_tool import SitemapRetrieverTool
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
    crawl_mode: str = Field(
        default="auto",
        title="Crawl Mode",
        description="Crawl mode: auto, sitemap, or discovery"
    )

class SEOAuditTool(BaseTool):
    name: str = "SEO Audit Tool"
    description: str = "A tool that performs comprehensive SEO audit on a website, checking for issues like broken links, duplicate content, meta tag issues, images, and more."
    args_schema: Type[BaseModel] = SEOAuditToolSchema
    tags: Set[str] = {"seo", "audit", "website", "content"}
    api_key: str = Field(default=os.environ.get('BROWSERLESS_API_KEY'))
    web_crawler_tool: WebCrawlerTool = Field(default_factory=WebCrawlerTool)
    sitemap_retriever_tool: SitemapRetrieverTool = Field(default_factory=SitemapRetrieverTool)
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
        crawl_mode: str = "auto",
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
                progress_callback=progress_callback,
                crawl_mode=crawl_mode
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
        progress_callback = None,
        crawl_mode: str = "auto"
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
            try:
                internal_links = self.checker.check_links(page_data, base_domain)
                # All links returned from check_links should be strings now
                for link in internal_links:
                    all_links.add((page_data["url"], link))
            except Exception as e:
                logger.error(f"Error checking links for {page_data.get('url', 'unknown URL')}: {str(e)}")

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

        # Keep track of the maximum pages analyzed
        max_pages_analyzed = 0

        # Modify crawler call to use page callback
        def wrapped_progress_callback(current=None, total=None, url=None):
            if progress_callback:
                nonlocal max_pages_analyzed
                # Handle both formats of progress callback
                # 1. When called with (data) from WebCrawlerTool._run
                # 2. When called with (current, total, url) from SitemapStrategy.crawl

                if isinstance(current, dict) and total is None and url is None:
                    # Format 1: Called with a data dictionary
                    data = current
                    # Get pages_analyzed from data, but ensure it's never less than our max
                    pages_analyzed = max(data.get('pages_analyzed', 0), max_pages_analyzed)
                    # Update our max if this value is higher
                    max_pages_analyzed = pages_analyzed

                    # Calculate percent_complete, ensuring it doesn't exceed 70% for this phase
                    percent_complete = min(70, int(data.get('percent_complete', 0) * 0.7))

                    update_data = {
                        'percent_complete': percent_complete,  # First 70% for crawling
                        'pages_analyzed': pages_analyzed,
                        'issues_found': total_issues,  # Now using the correct total_issues
                        'status': last_progress_data.get('status', f"Analyzing: {data.get('status', '')}")
                    }
                else:
                    # Format 2: Called with (current, total, url)
                    # Ensure current is never less than our max
                    pages_analyzed = max(current, max_pages_analyzed)
                    # Update our max if this value is higher
                    max_pages_analyzed = pages_analyzed

                    # Use the total from sitemap if available, otherwise use the passed total
                    # This ensures we show the correct denominator in the progress message
                    actual_total = total if total and total > 1 else max_pages

                    # Calculate percent_complete, ensuring it doesn't exceed 70% for this phase
                    percent_complete = min(70, int((pages_analyzed / actual_total) * 70) if actual_total else 0)

                    update_data = {
                        'percent_complete': percent_complete,  # First 70% for crawling
                        'pages_analyzed': pages_analyzed,
                        'issues_found': total_issues,
                        'status': f"Crawling URL {pages_analyzed}/{actual_total}: {url}"
                    }

                    # Add current URL info
                    if url:
                        update_data['current_url'] = url
                    if total:
                        update_data['total_urls'] = total

                # Add recent issues if available
                if 'recent_issues' in last_progress_data:
                    update_data['recent_issues'] = last_progress_data['recent_issues']
                    last_progress_data.clear()  # Clear after sending

                progress_callback(update_data)

        # Create a wrapper for the page callback that processes web crawler results
        def process_crawler_result(result):
            # Process each page in the results
            processed_pages = []
            for page_result in result.get('results', []):
                if 'error' in page_result:
                    logger.warning(f"Error crawling page: {page_result.get('url')}: {page_result.get('error')}")
                    continue

                # Extract page data from the crawler result
                page_data = {
                    "url": page_result.get('url', ''),
                    "title": self._extract_title(page_result),
                    "meta_description": self._extract_meta_description(page_result),
                    "h1_tags": self._extract_h1_tags(page_result),
                    "links": page_result.get('links', []),
                    "text_content": page_result.get('text', ''),
                    "html": page_result.get('html', ''),
                    "crawl_timestamp": datetime.now().isoformat(),
                    "status_code": page_result.get('status_code', 200),
                    "metadata": page_result.get('metadata', {}),
                }

                # Extract additional metadata
                metadata = page_result.get('metadata', {})
                if metadata:
                    page_data.update({
                        "canonical_url": metadata.get('canonical', ''),
                        "noindex": metadata.get('robots', '').lower().find('noindex') >= 0,
                        "meta_description": metadata.get('meta_description', ''),
                        "og_title": metadata.get('og_title', ''),
                        "og_description": metadata.get('og_description', ''),
                        "og_image": metadata.get('og_image', ''),
                        "twitter_card": metadata.get('twitter_card', ''),
                        "twitter_title": metadata.get('twitter_title', ''),
                        "twitter_description": metadata.get('twitter_description', ''),
                        "twitter_image": metadata.get('twitter_image', ''),
                    })

                # Process the page data through the callback
                page_callback(page_data)
                processed_pages.append(page_data)

                # Collect links for broken link checking
                for link in page_data.get('links', []):
                    # Format 1: Dictionary with 'url' key (from some crawlers)
                    if isinstance(link, dict) and 'url' in link:
                        link_url = link['url']
                        if link_url and isinstance(link_url, str):
                            all_links.add((page_data['url'], link_url))
                    # Format 2: Dictionary with 'href' key (from Playwright crawler)
                    elif isinstance(link, dict) and 'href' in link:
                        link_url = link['href']
                        if link_url and isinstance(link_url, str):
                            all_links.add((page_data['url'], link_url))
                    # Format 3: Simple string URL (from older crawlers)
                    elif isinstance(link, str):
                        all_links.add((page_data['url'], link))
                    # Unknown format
                    else:
                        logger.warning(f"Unexpected link type in process_crawler_result: {type(link)} - {link}")

            return processed_pages

        # Record start time
        start_time = datetime.now().isoformat()

        # First, get the sitemap to determine the actual number of URLs to crawl
        if crawl_mode == "auto" or crawl_mode == "sitemap":
            try:
                sitemap_result = await asyncio.to_thread(
                    self.sitemap_retriever_tool._run,
                    url=website,
                    user_id=1,  # Default user ID
                    max_pages=max_pages,  # Maximum number of pages to retrieve
                    requests_per_second=1.0  # Default RPS
                )

                # If we found URLs in the sitemap, use that count as max_pages
                if isinstance(sitemap_result, dict) and sitemap_result.get("success") and sitemap_result.get("urls"):
                    actual_max_pages = len(sitemap_result.get("urls", []))
                    logger.info(f"Found {actual_max_pages} URLs in sitemap. Using this as max_pages.")
                    # Only update max_pages if we found URLs and it's less than the original max_pages
                    if actual_max_pages > 0 and actual_max_pages <= max_pages:
                        max_pages = actual_max_pages
            except Exception as e:
                logger.warning(f"Error getting sitemap: {e}. Using original max_pages={max_pages}.")

        # Use the web crawler tool to crawl the website
        crawler_results = await asyncio.to_thread(
            self.web_crawler_tool._run,
            start_url=website,
            max_pages=max_pages,
            max_depth=3,  # Reasonable depth for SEO audit
            output_format="html,text,links,metadata",  # Get all the data we need
            stay_within_domain=True,
            delay_seconds=crawl_delay,
            mode=crawl_mode,
            respect_robots=True,
            progress_callback=wrapped_progress_callback
        )

        # Record end time
        end_time = datetime.now().isoformat()

        # Add timing information to crawler results
        crawler_results["start_time"] = start_time
        crawler_results["end_time"] = end_time
        crawler_results["crawl_time_seconds"] = (datetime.fromisoformat(end_time) -
                                              datetime.fromisoformat(start_time)).total_seconds()
        # Process the crawler results
        pages = process_crawler_result(crawler_results)
        total_pages = len(pages)
        logger.info(f"Crawler completed. Found {total_pages} pages")

        # Check broken links (70-85%)
        if progress_callback:
            # Use the max_pages_analyzed value to ensure consistency
            progress_callback({
                'percent_complete': 70,
                'pages_analyzed': max(max_pages_analyzed, total_pages),
                'issues_found': total_issues,
                'status': 'Checking broken links...'
            })

        logger.info("Checking for broken links...")
        logger.info(f"Number of links to check: {len(all_links)}")
        logger.info(f"Sample of links to check: {list(all_links)[:5]}")
        await self._check_broken_links(all_links, audit_results)
        total_issues += len(audit_results["broken_links"])
        logger.info(f"Found {len(audit_results['broken_links'])} broken links")
        logger.info(f"Broken links: {audit_results['broken_links']}")

        # Check duplicate content (85-95%)
        if progress_callback:
            # Use the max_pages_analyzed value to ensure consistency
            progress_callback({
                'percent_complete': 75,
                'pages_analyzed': max(max_pages_analyzed, total_pages),
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
            # Use the max_pages_analyzed value to ensure consistency
            progress_callback({
                'percent_complete': 80,
                'pages_analyzed': max(max_pages_analyzed, total_pages),
                'issues_found': total_issues,
                'status': 'Checking SSL, robots.txt and sitemap...'
            })

        logger.info("Checking SSL...")
        await self._check_ssl(website, audit_results)

        logger.info("Checking robots.txt and sitemap...")
        sitemap_issues = await self._check_robots_sitemap(website, audit_results)
        total_issues += sitemap_issues

        if progress_callback:
            # Use the max_pages_analyzed value to ensure consistency
            progress_callback({
                'percent_complete': 85,
                'pages_analyzed': max(max_pages_analyzed, total_pages),
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
            # Use the max_pages_analyzed value to ensure consistency
            progress_callback({
                'percent_complete': 100,
                'pages_analyzed': max(max_pages_analyzed, total_pages),
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

    # Helper methods for extracting data from crawler results
    def _extract_title(self, page_result):
        """Extract title from page result"""
        # Try to get from metadata first
        metadata = page_result.get('metadata', {})
        if metadata and metadata.get('title'):
            return metadata.get('title')

        # Try to extract from HTML
        html = page_result.get('html', '')
        if html:
            match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        # Fallback to URL
        url = page_result.get('url', '')
        if url:
            return url.split('/')[-1].replace('-', ' ').replace('_', ' ').title()

        return ''

    def _extract_meta_description(self, page_result):
        """Extract meta description from page result"""
        # Try to get from metadata first
        metadata = page_result.get('metadata', {})
        if metadata and metadata.get('meta_description'):
            return metadata.get('meta_description')

        # Try to extract from HTML
        html = page_result.get('html', '')
        if html:
            match = re.search(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\'>]+)["\']', html, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return ''

    def _extract_h1_tags(self, page_result):
        """Extract H1 tags from page result"""
        h1_tags = []

        # Try to extract from HTML
        html = page_result.get('html', '')
        if html:
            matches = re.findall(r'<h1[^>]*>([^<]+)</h1>', html, re.IGNORECASE)
            if matches:
                h1_tags = [match.strip() for match in matches]

        return h1_tags

    async def _check_robots_sitemap(self, website: str, audit_results: Dict[str, Any]):
        """Check for robots.txt and sitemap.xml using the sitemap retriever tool."""
        # Ensure URL has a protocol
        if not website.startswith(('http://', 'https://')):
            website = f"https://{website}"

        # Use the sitemap retriever tool to get sitemap information
        sitemap_result = await asyncio.to_thread(
            self.sitemap_retriever_tool._run,
            url=website,
            user_id=1,  # Default user ID
            max_pages=10,  # Just need sitemap info, not full crawl
            requests_per_second=1.0
        )

        # Process robots.txt information
        robots_info = sitemap_result.get('robots_txt_info', {})
        robots_present = robots_info.get('present', False) or bool(sitemap_result.get('robots_txt_content', ''))
        audit_results["robots_txt"] = {
            "present": robots_present,
            "content": robots_info.get('content', '') or sitemap_result.get('robots_txt_content', ''),
            "sitemap_directives": robots_info.get('sitemap_urls', []) or sitemap_result.get('sitemap_urls', [])
        }

        # Process sitemap information
        sitemap_urls = sitemap_result.get('sitemap_urls', [])
        sitemap_issues = []

        # Check if sitemap exists - look at both sitemap_urls and the actual URLs found
        sitemap_exists = bool(sitemap_urls) or bool(sitemap_result.get('urls', []))

        if not sitemap_exists:
            sitemap_issues.append({
                "type": "sitemap_missing",
                "issue": "No sitemap found",
                "url": website,
                "severity": "high"
            })

        # Check sitemap content
        if sitemap_result.get('urls', []):
            # Check for lastmod, changefreq, priority
            urls_with_lastmod = sum(1 for url in sitemap_result.get('urls', []) if url.get('lastmod'))
            urls_with_changefreq = sum(1 for url in sitemap_result.get('urls', []) if url.get('changefreq'))
            urls_with_priority = sum(1 for url in sitemap_result.get('urls', []) if url.get('priority'))

            total_urls = len(sitemap_result.get('urls', []))

            # Add issues for missing attributes
            if urls_with_lastmod < total_urls * 0.8:  # 80% should have lastmod
                sitemap_issues.append({
                    "type": "sitemap_missing_lastmod",
                    "issue": f"Only {urls_with_lastmod}/{total_urls} URLs have lastmod attribute",
                    "url": website,
                    "severity": "medium"
                })

            # Add sitemap validation results to audit results
            audit_results["sitemap"] = {
                "present": sitemap_exists,
                "urls": sitemap_urls,
                "total_urls": total_urls,
                "urls_with_lastmod": urls_with_lastmod,
                "urls_with_changefreq": urls_with_changefreq,
                "urls_with_priority": urls_with_priority,
                "issues": sitemap_issues
            }
        else:
            audit_results["sitemap"] = {
                "present": sitemap_exists,
                "urls": sitemap_urls,
                "total_urls": 0,
                "issues": sitemap_issues
            }

        # Return the number of sitemap issues
        return len(sitemap_issues)

    async def _check_broken_links(self, links: Set[tuple], audit_results: Dict[str, Any]):
        """Check for broken internal links using HEAD requests with caching."""
        # Add explicit logging to confirm this method is being called
        #logger.info(f"_check_broken_links called with {len(links)} links")

        # Create a semaphore to limit concurrent requests
        semaphore = asyncio.Semaphore(5)  # Allow 5 concurrent requests

        async def check_link(source_url: str, target_url: str):
            """Check if a link is broken using our robust _check_link method."""
            # Add explicit logging to confirm this function is being called
            #logger.info(f"check_link called for: {target_url} from {source_url}")

            async with semaphore:
                # Use the more robust _check_link method
                #logger.info(f"Calling _check_link for: {target_url}")
                result = await self._check_link(source_url, target_url)
                #logger.info(f"_check_link result for {target_url}: {result}")

                # If link is broken, add to audit results
                if result.get('is_broken', False):
                    logger.info(f"Link is broken: {target_url}, adding to broken_links")
                    audit_results["broken_links"].append({
                        "source_url": source_url,
                        "target_url": target_url,
                        "status_code": result.get('status_code'),
                        "error": result.get('error'),
                        "timestamp": datetime.now().isoformat()
                    })
                else:
                    #logger.info(f"Link is NOT broken: {target_url}")
                    pass

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
        """Check if a link is broken using a robust, unified approach.

        This is a robust approach to check if a link is broken that works well for all types of links,
        including social media sites that often block automated requests.

        The approach uses multiple strategies:
        1. DNS resolution check to verify the domain exists
        2. Multiple HTTP request methods (HEAD, GET) with different headers
        3. Streaming to minimize data transfer
        4. Comprehensive error handling

        Returns a dictionary with the link status information.
        """

        # Generate cache key
        cache_key = f"link_status:{target_url}"
        cached_result = cache.get(cache_key)

        if cached_result is not None:
            #logger.info(f"Using cached result for: {target_url}")
            return cached_result

        # Parse the URL to get the domain
        parsed_url = urlparse(target_url)
        domain = parsed_url.netloc.lower()

        # Check if this is a social media URL (for logging purposes)
        social_media_domains = ['facebook.com', 'twitter.com', 'x.com', 'instagram.com', 'linkedin.com', 'tiktok.com', 'pinterest.com']
        is_social_media = any(sm_domain in domain for sm_domain in social_media_domains)

        # Use a unified approach for all links
        def check_link_robust():
            import requests
            import socket
            from requests.exceptions import RequestException
            import warnings
            from urllib3.exceptions import InsecureRequestWarning

            # Suppress SSL warnings
            warnings.simplefilter('ignore', InsecureRequestWarning)

            # First, try a simple DNS resolution to check if the domain exists
            # This avoids making HTTP requests to non-existent domains
            try:
                socket.gethostbyname(domain)
            except socket.gaierror:
                return {
                    'is_broken': True,
                    'status_code': None,
                    'error': f"DNS resolution failed for {domain}",
                    'checked_at': datetime.now().isoformat(),
                    'is_social_media': is_social_media
                }

            # Use a browser-like User-Agent to avoid being blocked
            browser_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
                'Connection': 'close',
            }

            # Minimal headers for fallback
            minimal_headers = {
                'User-Agent': 'Mozilla/5.0 (compatible; SEOAuditBot/1.0)',
                'Accept': '*/*',
            }

            # Try multiple approaches with proper error handling
            try:
                # Strategy 1: Try HEAD first with browser-like headers
                try:
                    response = requests.head(
                        target_url,
                        headers=browser_headers,
                        timeout=5,
                        allow_redirects=True,
                        verify=False
                    )

                    # If HEAD request is successful, return result
                    if response.status_code < 400:
                        return {
                            'is_broken': False,
                            'status_code': response.status_code,
                            'error': None,
                            'checked_at': datetime.now().isoformat(),
                            'is_social_media': is_social_media
                        }
                except Exception:
                    # If HEAD fails for any reason, continue to next strategy
                    pass

                # Strategy 2: Try GET with browser-like headers and streaming
                try:
                    response = requests.get(
                        target_url,
                        headers=browser_headers,
                        timeout=10,
                        allow_redirects=True,
                        verify=False,
                        stream=True
                    )

                    # Read just a small amount of data to confirm the connection works
                    try:
                        next(response.iter_content(1024))
                    except StopIteration:
                        # Empty response is fine
                        pass

                    # Close the connection to free resources
                    response.close()

                    # If GET request is successful, return result
                    if response.status_code < 400:
                        return {
                            'is_broken': False,
                            'status_code': response.status_code,
                            'error': None,
                            'checked_at': datetime.now().isoformat(),
                            'is_social_media': is_social_media
                        }
                except Exception:
                    # If GET fails for any reason, continue to next strategy
                    pass

                # Strategy 3: Try HEAD with minimal headers
                try:
                    response = requests.head(
                        target_url,
                        headers=minimal_headers,
                        timeout=5,
                        allow_redirects=True,
                        verify=False
                    )

                    # If HEAD request is successful, return result
                    if response.status_code < 400:
                        return {
                            'is_broken': False,
                            'status_code': response.status_code,
                            'error': None,
                            'checked_at': datetime.now().isoformat(),
                            'is_social_media': is_social_media
                        }
                except Exception:
                    # If HEAD fails for any reason, continue to next strategy
                    pass

                # Strategy 4: Try GET with minimal headers and streaming
                try:
                    response = requests.get(
                        target_url,
                        headers=minimal_headers,
                        timeout=15,
                        allow_redirects=True,
                        verify=False,
                        stream=True
                    )

                    # Read just a small amount of data to confirm the connection works
                    try:
                        next(response.iter_content(1024))
                    except StopIteration:
                        # Empty response is fine
                        pass

                    # Close the connection to free resources
                    response.close()

                    # If GET request is successful, return result
                    if response.status_code < 400:
                        return {
                            'is_broken': False,
                            'status_code': response.status_code,
                            'error': None,
                            'checked_at': datetime.now().isoformat(),
                            'is_social_media': is_social_media
                        }
                    else:
                        # If we've tried all strategies and still got an error,
                        # the link is probably broken
                        # But for social media sites, we'll assume they're valid but blocking us
                        if is_social_media:
                            return {
                                'is_broken': False,  # Not broken, just blocking us
                                'status_code': response.status_code,
                                'error': f"Site exists but may be blocking automated access: HTTP {response.status_code}",
                                'checked_at': datetime.now().isoformat(),
                                'is_social_media': True
                            }
                        else:
                            return {
                                'is_broken': True,
                                'status_code': response.status_code,
                                'error': f"HTTP {response.status_code}",
                                'checked_at': datetime.now().isoformat(),
                                'is_social_media': is_social_media
                            }
                except Exception as e:
                    # If all strategies fail, the link is probably broken
                    # But for social media sites, we'll assume they're valid but blocking us
                    if is_social_media:
                        return {
                            'is_broken': False,  # Not broken, just blocking us
                            'status_code': None,
                            'error': f"Site exists but may be blocking automated access: {str(e)}",
                            'checked_at': datetime.now().isoformat(),
                            'is_social_media': True
                        }
                    else:
                        return {
                            'is_broken': True,
                            'status_code': None,
                            'error': str(e),
                            'checked_at': datetime.now().isoformat(),
                            'is_social_media': is_social_media
                        }

            except Exception as e:
                # If we get here, something unexpected happened
                # For social media sites, we'll assume they're valid but blocking us
                if is_social_media:
                    return {
                        'is_broken': False,  # Not broken, just blocking us
                        'status_code': None,
                        'error': f"Site exists but may be blocking automated access: {str(e)}",
                        'checked_at': datetime.now().isoformat(),
                        'is_social_media': True
                    }
                else:
                    return {
                        'is_broken': True,
                        'status_code': None,
                        'error': str(e),
                        'checked_at': datetime.now().isoformat(),
                        'is_social_media': is_social_media
                    }

        # Run the link check in a thread
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, check_link_robust)

        # Cache the result
        cache.set(cache_key, result, timeout=86400)  # Cache for 24 hours
        return result

    async def _check_content_similarity(self, page1: Dict[str, Any], page2: Dict[str, Any]) -> float:
        """Check content similarity between two pages."""
        from difflib import SequenceMatcher

        # Get text content
        text1 = page1.get('text_content', '')
        text2 = page2.get('text_content', '')

        # Use SequenceMatcher for similarity ratio
        return SequenceMatcher(None, text1, text2).ratio()
