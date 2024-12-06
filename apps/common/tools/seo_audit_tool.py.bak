import logging
from typing import Dict, List, Any, Optional, Type, Set
from pydantic import BaseModel, Field, validator
from crewai_tools import BaseTool
from bs4 import BeautifulSoup
import requests
from urllib.parse import urlparse, urljoin
import aiohttp
import asyncio
from concurrent.futures import ThreadPoolExecutor
import re
from collections import defaultdict
import ssl
import json
from apps.common.browser_tool import BrowserTool
from apps.common.tools.async_crawl_website_tool import AsyncCrawlWebsiteTool

logger = logging.getLogger(__name__)

class BrokenLinkDetail(BaseModel):
    source_page: str
    broken_link: str
    status_code: Optional[int] = None

class DuplicateContentDetail(BaseModel):
    page_url: str
    issue_type: str  # 'duplicate_title', 'duplicate_description', 'duplicate_content'
    duplicate_with: Optional[str] = None

class MetaTagIssueDetail(BaseModel):
    page_url: str
    missing_meta: List[str] = []
    duplicate_meta: List[str] = []
    meta_length_issues: Dict[str, int] = {}

class SEOAuditResults(BaseModel):
    broken_links: List[BrokenLinkDetail] = []
    duplicate_content: List[DuplicateContentDetail] = []
    meta_tag_issues: List[MetaTagIssueDetail] = []
    ssl_issues: Dict[str, Any] = {}
    sitemap_present: bool = False
    robots_txt_present: bool = False
    mobile_friendly: bool = True
    page_speed_issues: Dict[str, Any] = {}
    crawl_stats: Dict[str, Any] = {}

class SEOAuditToolSchema(BaseModel):
    website_url: str = Field(..., description="Website URL to perform SEO audit on")
    max_pages: int = Field(default=100, description="Maximum number of pages to audit")
    check_external_links: bool = Field(default=False, description="Whether to check external links for broken links")

    @validator('website_url')
    def validate_url(cls, v):
        parsed = urlparse(v)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError('Invalid URL provided')
        return v

class SEOAuditTool(BaseTool):
    name: str = "SEO Audit Tool"
    description: str = "Performs comprehensive SEO audit on a website, checking for issues like broken links, duplicate content, meta tag issues, and more."
    args_schema: Type[BaseModel] = SEOAuditToolSchema
    tags: Set[str] = {"seo", "audit", "website", "optimization"}

    def __init__(self, **data):
        super().__init__(**data)
        self.browser_tool = BrowserTool()
        self.crawl_tool = AsyncCrawlWebsiteTool()
        self.session = None

    async def _arun(self, website_url: str, max_pages: int = 100, check_external_links: bool = False) -> Dict[str, Any]:
        """Asynchronously run the SEO audit."""
        logger.info(f"Starting SEO audit for: {website_url}")
        
        # Initialize results
        audit_results = SEOAuditResults()
        
        try:
            # Create aiohttp session for async requests
            async with aiohttp.ClientSession() as self.session:
                # Step 1: Crawl website
                crawl_result = await self.crawl_tool._run(website_url)
                pages = crawl_result.get('pages', [])
                
                if not pages:
                    raise ValueError("No pages found to audit")

                # Update crawl stats
                audit_results.crawl_stats = {
                    "total_pages": len(pages),
                    "total_links": crawl_result.get('total_links', 0),
                    "crawl_time": crawl_result.get('crawl_time', 0)
                }

                # Step 2: Check for basic requirements
                await self._check_basic_requirements(website_url, audit_results)
                
                # Step 3: Process pages in parallel
                tasks = []
                for page in pages[:max_pages]:
                    tasks.append(self._process_page(page, audit_results, check_external_links))
                
                await asyncio.gather(*tasks)
                
                # Step 4: Analyze duplicate content
                await self._analyze_duplicate_content(pages, audit_results)
                
                logger.info("SEO audit completed successfully")
                return audit_results.dict()

        except Exception as e:
            logger.error(f"Error during SEO audit: {e}")
            raise

    async def _check_basic_requirements(self, url: str, audit_results: SEOAuditResults):
        """Check basic SEO requirements like SSL, sitemap, and robots.txt."""
        try:
            # Check SSL
            parsed_url = urlparse(url)
            context = ssl.create_default_context()
            ssl_valid = await self._check_ssl(parsed_url.netloc)
            audit_results.ssl_issues = {"valid_certificate": ssl_valid}

            # Check sitemap
            sitemap_url = urljoin(url, '/sitemap.xml')
            async with self.session.get(sitemap_url) as response:
                audit_results.sitemap_present = response.status == 200

            # Check robots.txt
            robots_url = urljoin(url, '/robots.txt')
            async with self.session.get(robots_url) as response:
                audit_results.robots_txt_present = response.status == 200

        except Exception as e:
            logger.error(f"Error checking basic requirements: {e}")

    async def _check_ssl(self, hostname: str) -> bool:
        """Check SSL certificate validity."""
        try:
            context = ssl.create_default_context()
            async with aiohttp.TCPConnector(ssl=context) as connector:
                async with aiohttp.ClientSession(connector=connector) as session:
                    async with session.get(f"https://{hostname}") as response:
                        return True
        except Exception:
            return False

    async def _process_page(self, page: Dict[str, Any], audit_results: SEOAuditResults, check_external_links: bool):
        """Process a single page for SEO issues."""
        url = page.get('url')
        content = page.get('content')
        
        if not url or not content:
            return

        soup = BeautifulSoup(content, 'html.parser')

        # Check meta tags
        await self._check_meta_tags(url, soup, audit_results)
        
        # Check broken links
        await self._check_broken_links(url, soup, audit_results, check_external_links)

    async def _check_meta_tags(self, url: str, soup: BeautifulSoup, audit_results: SEOAuditResults):
        """Check for meta tag issues."""
        issues = MetaTagIssueDetail(page_url=url)
        
        # Check title
        title = soup.find('title')
        if not title:
            issues.missing_meta.append('title')
        elif title.string:
            length = len(title.string.strip())
            if length < 30 or length > 60:
                issues.meta_length_issues['title'] = length

        # Check meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if not meta_desc:
            issues.missing_meta.append('description')
        elif meta_desc.get('content'):
            length = len(meta_desc['content'].strip())
            if length < 120 or length > 160:
                issues.meta_length_issues['description'] = length

        # Check duplicate meta tags
        meta_tags = soup.find_all('meta')
        meta_names = [tag.get('name', '').lower() for tag in meta_tags if tag.get('name')]
        duplicates = {name for name in meta_names if meta_names.count(name) > 1}
        if duplicates:
            issues.duplicate_meta.extend(list(duplicates))

        if issues.missing_meta or issues.duplicate_meta or issues.meta_length_issues:
            audit_results.meta_tag_issues.append(issues)

    async def _check_broken_links(self, url: str, soup: BeautifulSoup, audit_results: SEOAuditResults, check_external_links: bool):
        """Check for broken links."""
        links = soup.find_all('a', href=True)
        tasks = []
        
        for link in links:
            href = link['href']
            full_url = urljoin(url, href)
            parsed = urlparse(full_url)
            
            # Skip if external link check is disabled and it's an external link
            if not check_external_links and parsed.netloc != urlparse(url).netloc:
                continue
                
            tasks.append(self._check_link(url, full_url))
        
        results = await asyncio.gather(*tasks)
        audit_results.broken_links.extend([r for r in results if r])

    async def _check_link(self, source_url: str, link_url: str) -> Optional[BrokenLinkDetail]:
        """Check if a link is broken."""
        try:
            async with self.session.head(link_url, allow_redirects=True, timeout=10) as response:
                if response.status >= 400:
                    return BrokenLinkDetail(
                        source_page=source_url,
                        broken_link=link_url,
                        status_code=response.status
                    )
        except Exception:
            return BrokenLinkDetail(
                source_page=source_url,
                broken_link=link_url,
                status_code=None
            )
        return None

    async def _analyze_duplicate_content(self, pages: List[Dict[str, Any]], audit_results: SEOAuditResults):
        """Analyze pages for duplicate content."""
        titles = defaultdict(list)
        descriptions = defaultdict(list)
        contents = defaultdict(list)
        
        for page in pages:
            url = page.get('url')
            content = page.get('content')
            if not url or not content:
                continue
                
            soup = BeautifulSoup(content, 'html.parser')
            
            # Check titles
            title = soup.find('title')
            if title and title.string:
                titles[title.string.strip()].append(url)
            
            # Check meta descriptions
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc and meta_desc.get('content'):
                descriptions[meta_desc['content'].strip()].append(url)
            
            # Check main content (simplified)
            main_content = ' '.join(soup.stripped_strings)
            content_hash = hash(main_content)
            contents[content_hash].append(url)
        
        # Add duplicate content issues
        for title, urls in titles.items():
            if len(urls) > 1:
                for url in urls:
                    audit_results.duplicate_content.append(
                        DuplicateContentDetail(
                            page_url=url,
                            issue_type='duplicate_title',
                            duplicate_with=urls[0] if urls[0] != url else urls[1]
                        )
                    )
        
        for desc, urls in descriptions.items():
            if len(urls) > 1:
                for url in urls:
                    audit_results.duplicate_content.append(
                        DuplicateContentDetail(
                            page_url=url,
                            issue_type='duplicate_description',
                            duplicate_with=urls[0] if urls[0] != url else urls[1]
                        )
                    )
        
        for content_hash, urls in contents.items():
            if len(urls) > 1:
                for url in urls:
                    audit_results.duplicate_content.append(
                        DuplicateContentDetail(
                            page_url=url,
                            issue_type='duplicate_content',
                            duplicate_with=urls[0] if urls[0] != url else urls[1]
                        )
                    )
