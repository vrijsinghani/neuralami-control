"""SEO check implementations for the SEO Audit Tool."""
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse, urljoin
import logging
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime
import re

logger = logging.getLogger(__name__)

class SEOChecker:
    """Base class for SEO checks."""
    
    @staticmethod
    def is_404_page(page_data: Dict[str, Any]) -> bool:
        """Helper function to detect 404 pages including custom error pages."""
        # Check status code first
        if page_data.get('status_code') == 404:
            return True
                
        # Check common 404 indicators in title and content
        title = page_data.get('title', '').lower()
        content = page_data.get('text_content', '').lower()
        url = page_data.get('url', '').lower()
        
        error_indicators = [
            '404', 'not found', 'page not found', 'error 404',
            'page does not exist', 'page no longer exists',
            'page couldn\'t be found', 'page could not be found',
            'nothing found', 'entry not found', 'article not found',
            'product not found', 'no results found',
            'error page', 'page missing', 'content not found'
        ]
        
        # Check title for error indicators
        if any(indicator in title for indicator in error_indicators):
            return True
                
        # Check first 1000 chars of content for error indicators
        # (focusing on the start where error messages typically appear)
        content_start = content[:1000]
        if any(indicator in content_start for indicator in error_indicators):
            return True
                
        # Check URL patterns that often indicate 404 pages
        url_indicators = ['/404', 'error', 'not-found', 'notfound', 'page-not-found']
        if any(indicator in url for indicator in url_indicators):
            return True
                
        return False
    
    @staticmethod
    def check_meta_tags(page_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check meta tags including title and description."""
        issues = []
        
        # Title tag checks
        title = page_data.get("title", "").strip()
        if not title:
            issues.append({
                "type": "title",
                "issue": "Missing title tag",
                "value": None,
                "severity": "high"
            })
        elif len(title) < 10:
            issues.append({
                "type": "title",
                "issue": f"Title tag too short ({len(title)} chars)",
                "value": title,
                "severity": "medium"
            })
        elif len(title) > 60:
            issues.append({
                "type": "title",
                "issue": f"Title tag too long ({len(title)} chars)",
                "value": title,
                "severity": "medium"
            })
        
        # Meta description checks
        meta_desc = page_data.get("meta_description", "").strip()
        if not meta_desc:
            issues.append({
                "type": "meta_description",
                "issue": "Missing meta description",
                "value": None,
                "severity": "medium"
            })
        elif len(meta_desc) < 50:
            issues.append({
                "type": "meta_description",
                "issue": f"Meta description too short ({len(meta_desc)} chars)",
                "value": meta_desc,
                "severity": "medium"
            })
        elif len(meta_desc) > 160:
            issues.append({
                "type": "meta_description",
                "issue": f"Meta description too long ({len(meta_desc)} chars)",
                "value": meta_desc,
                "severity": "medium"
            })
        
        return issues

    @staticmethod
    def check_headings(page_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check heading structure."""
        issues = []
        
        # H1 tag checks
        h1_tags = page_data.get("h1_tags", [])
        if not h1_tags:
            issues.append({
                "type": "h1",
                "issue": "Missing H1 tag",
                "value": None,
                "severity": "high"
            })
        elif len(h1_tags) > 1:
            issues.append({
                "type": "h1",
                "issue": f"Multiple H1 tags ({len(h1_tags)})",
                "value": h1_tags,
                "severity": "medium"
            })
        
        return issues

    @staticmethod
    def check_images(page_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check image optimization."""
        issues = []
        images = page_data.get("images", [])
        
        for img in images:
            img_issues = []
            
            # Alt text checks
            if not img.get("alt"):
                img_issues.append({
                    "type": "missing_alt",
                    "issue": "Missing alt text",
                    "value": img.get("src"),
                    "severity": "high"
                })
            elif len(img.get("alt", "")) < 3:
                img_issues.append({
                    "type": "short_alt",
                    "issue": "Alt text too short",
                    "value": img.get("alt"),
                    "severity": "medium"
                })
            
            # Dimension checks
            width = img.get("width")
            height = img.get("height")
            if not (width and height):
                img_issues.append({
                    "type": "missing_dimensions",
                    "issue": "Missing width/height attributes",
                    "value": img.get("src"),
                    "severity": "medium"
                })
            
            # Filename checks
            filename = img.get("src", "").split("/")[-1]
            if filename.lower().startswith(("img", "image", "pic", "dsc")):
                img_issues.append({
                    "type": "generic_filename",
                    "issue": "Generic image filename",
                    "value": filename,
                    "severity": "low"
                })
            
            # Size checks
            size = img.get("size", 0)
            if size > 500000:  # 500KB
                img_issues.append({
                    "type": "large_size",
                    "issue": f"Image size too large ({size/1000:.0f}KB)",
                    "value": img.get("src"),
                    "severity": "high"
                })
            
            # Lazy loading check
            if not img.get("loading") == "lazy":
                img_issues.append({
                    "type": "no_lazy_loading",
                    "issue": "Image missing lazy loading",
                    "value": img.get("src"),
                    "severity": "medium"
                })
            
            # Responsive image checks
            if not img.get("srcset"):
                img_issues.append({
                    "type": "no_srcset",
                    "issue": "Image missing responsive srcset",
                    "value": img.get("src"),
                    "severity": "medium"
                })
            
            if img_issues:
                issues.append({
                    "url": img.get("src"),
                    "issues": img_issues
                })
        
        return issues

    @staticmethod
    def check_links(page_data: Dict[str, Any], base_domain: str) -> List[str]:
        """Extract and check internal links."""
        internal_links = []
        page_links = page_data.get("links", [])
        
        for link in page_links:
            if urlparse(link).netloc == base_domain:
                internal_links.append(link)
        
        return internal_links

    @staticmethod
    def check_content(page_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check content quality and structure."""
        issues = []
        text_content = page_data.get("text_content", "")
        word_count = len(text_content.split())
        
        # Content length check
        if word_count < 300:
            issues.append({
                "type": "thin_content",
                "issue": f"Thin content ({word_count} words)",
                "value": word_count,
                "severity": "medium"
            })
        
        return issues

    @staticmethod
    def check_canonical_tags(page_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check canonical tag implementation and validation."""
        issues = []
        url = page_data.get("url", "")
        canonical_url = page_data.get("canonical_url", "")
        page_content = page_data.get("text_content", "")
        
        # Check if canonical tag exists
        if not canonical_url:
            issues.append({
                "type": "canonical_missing",
                "issue": "Missing canonical tag",
                "url": url,
                "value": None,
                "severity": "high"
            })
            return issues

        # Validate canonical URL format
        if not canonical_url.startswith(('http://', 'https://')):
            issues.append({
                "type": "canonical_invalid_format",
                "issue": "Invalid canonical URL format",
                "url": url,
                "value": canonical_url,
                "severity": "high"
            })

        # Check for self-referential canonical
        if canonical_url != url:
            # If the page is pointing to a different URL, check if it might be a duplicate
            if page_content:
                issues.append({
                    "type": "canonical_different",
                    "issue": "Canonical URL points to a different page",
                    "url": url,
                    "value": canonical_url,
                    "severity": "medium"
                })

        # Check for relative canonical URLs
        if canonical_url.startswith('/'):
            issues.append({
                "type": "canonical_relative",
                "issue": "Canonical URL is relative",
                "url": url,
                "value": canonical_url,
                "severity": "medium"
            })

        # Check for multiple canonical tags
        canonical_count = page_data.get("canonical_count", 0)
        if canonical_count > 1:
            issues.append({
                "type": "canonical_multiple",
                "issue": f"Multiple canonical tags found ({canonical_count})",
                "url": url,
                "value": str(canonical_count),
                "severity": "high"
            })

        # Check for canonical on non-canonical pages
        if page_data.get("is_pagination", False) and canonical_url == url:
            issues.append({
                "type": "canonical_on_pagination",
                "issue": "Self-referential canonical on paginated page",
                "url": url,
                "value": canonical_url,
                "severity": "medium"
            })

        # Check for canonical chain (if available)
        canonical_chain = page_data.get("canonical_chain", [])
        if len(canonical_chain) > 1:
            issues.append({
                "type": "canonical_chain",
                "issue": f"Canonical chain detected (length: {len(canonical_chain)})",
                "url": url,
                "value": " -> ".join(canonical_chain),
                "severity": "high"
            })
        
        return issues

    @staticmethod
    def get_page_metrics(page_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate page metrics for analysis."""
        images = page_data.get("images", [])
        return {
            "url": page_data["url"],
            "title_length": len(page_data.get("title", "")),
            "meta_description_length": len(page_data.get("meta_description", "")),
            "h1_count": len(page_data.get("h1_tags", [])),
            "outbound_links": len(page_data.get("links", [])),
            "content_length": len(page_data.get("text_content", "")),
            "image_count": len(images),
            "images_without_alt": sum(1 for img in images if not img.get("alt")),
            "total_image_size": sum(img.get("size", 0) for img in images),
            "timestamp": page_data.get("crawl_timestamp"),
            "has_canonical": bool(page_data.get("canonical_url")),
            "canonical_url": page_data.get("canonical_url", ""),
            "canonical_count": page_data.get("canonical_count", 0)
        } 

    @staticmethod
    async def validate_sitemap(base_url: str) -> Dict[str, Any]:
        """Validate XML sitemap structure and content."""
        sitemap_issues = []
        sitemap_data = {
            "sitemap_found": False,
            "sitemap_type": None,  # "index" or "urlset"
            "total_urls": 0,
            "valid_urls": 0,
            "issues": [],
            "last_modified_dates": 0,
            "change_frequencies": 0,
            "priorities": 0,
            "sitemap_locations": []
        }

        async def check_sitemap_url(sitemap_url: str) -> Optional[Dict[str, Any]]:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(sitemap_url, allow_redirects=True) as response:
                        if response.status != 200:
                            sitemap_issues.append({
                                "type": "sitemap_http_error",
                                "issue": f"Sitemap HTTP error {response.status}",
                                "url": sitemap_url,
                                "severity": "high"
                            })
                            return None

                        content = await response.text()
                        soup = BeautifulSoup(content, 'xml')
                        
                        # Check if it's a sitemap index
                        sitemapindex = soup.find('sitemapindex')
                        if sitemapindex:
                            sitemap_data["sitemap_type"] = "index"
                            sitemaps = sitemapindex.find_all('sitemap')
                            for sitemap in sitemaps:
                                loc = sitemap.find('loc')
                                if loc:
                                    sitemap_data["sitemap_locations"].append(loc.text)
                                    sub_result = await check_sitemap_url(loc.text)
                                    if sub_result:
                                        for key in ["total_urls", "valid_urls", "last_modified_dates", "change_frequencies", "priorities"]:
                                            sitemap_data[key] += sub_result[key]
                            return sitemap_data

                        # Check if it's a regular sitemap
                        urlset = soup.find('urlset')
                        if urlset:
                            sitemap_data["sitemap_type"] = "urlset"
                            urls = urlset.find_all('url')
                            result = {
                                "total_urls": len(urls),
                                "valid_urls": 0,
                                "last_modified_dates": 0,
                                "change_frequencies": 0,
                                "priorities": 0
                            }

                            for url in urls:
                                loc = url.find('loc')
                                if not loc or not loc.text:
                                    sitemap_issues.append({
                                        "type": "missing_url",
                                        "issue": "URL entry missing location",
                                        "url": sitemap_url,
                                        "severity": "high"
                                    })
                                    continue

                                url_str = loc.text.strip()
                                if not url_str.startswith(('http://', 'https://')):
                                    sitemap_issues.append({
                                        "type": "invalid_url",
                                        "issue": "Invalid URL format",
                                        "url": url_str,
                                        "severity": "high"
                                    })
                                    continue

                                result["valid_urls"] += 1

                                # Check optional elements
                                if url.find('lastmod'):
                                    result["last_modified_dates"] += 1
                                    # Validate lastmod format
                                    lastmod = url.find('lastmod').text
                                    if not re.match(r'^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}(\+\d{2}:\d{2}|Z)?)?$', lastmod):
                                        sitemap_issues.append({
                                            "type": "invalid_lastmod",
                                            "issue": "Invalid lastmod date format",
                                            "url": url_str,
                                            "value": lastmod,
                                            "severity": "medium"
                                        })

                                if url.find('changefreq'):
                                    result["change_frequencies"] += 1
                                    # Validate changefreq value
                                    changefreq = url.find('changefreq').text
                                    if changefreq not in ['always', 'hourly', 'daily', 'weekly', 'monthly', 'yearly', 'never']:
                                        sitemap_issues.append({
                                            "type": "invalid_changefreq",
                                            "issue": "Invalid changefreq value",
                                            "url": url_str,
                                            "value": changefreq,
                                            "severity": "low"
                                        })

                                if url.find('priority'):
                                    result["priorities"] += 1
                                    # Validate priority value
                                    priority = url.find('priority').text
                                    try:
                                        priority_float = float(priority)
                                        if not 0.0 <= priority_float <= 1.0:
                                            sitemap_issues.append({
                                                "type": "invalid_priority",
                                                "issue": "Priority value out of range (0.0-1.0)",
                                                "url": url_str,
                                                "value": priority,
                                                "severity": "low"
                                            })
                                    except ValueError:
                                        sitemap_issues.append({
                                            "type": "invalid_priority",
                                            "issue": "Invalid priority value format",
                                            "url": url_str,
                                            "value": priority,
                                            "severity": "low"
                                        })

                            return result

                        sitemap_issues.append({
                            "type": "invalid_sitemap",
                            "issue": "Invalid sitemap format (missing sitemapindex or urlset)",
                            "url": sitemap_url,
                            "severity": "high"
                        })
                        return None

            except Exception as e:
                sitemap_issues.append({
                    "type": "sitemap_error",
                    "issue": f"Error processing sitemap: {str(e)}",
                    "url": sitemap_url,
                    "severity": "high"
                })
                return None

        # Check common sitemap locations
        sitemap_urls = [
            f"{base_url}/sitemap_index.xml",
            f"{base_url}/sitemap.xml",
            f"{base_url}/sitemap",
            f"{base_url}/sitemap_news.xml",
            f"{base_url}/sitemap_products.xml",
            f"{base_url}/post-sitemap.xml"
        ]

        for sitemap_url in sitemap_urls:
            result = await check_sitemap_url(sitemap_url)
            if result:
                sitemap_data["sitemap_found"] = True
                break

        # Check robots.txt for Sitemap directive
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{base_url}/robots.txt") as response:
                    if response.status == 200:
                        robots_content = await response.text()
                        sitemap_matches = re.findall(r'Sitemap:\s*(.+)', robots_content, re.IGNORECASE)
                        for sitemap_url in sitemap_matches:
                            sitemap_url = sitemap_url.strip()
                            if sitemap_url not in sitemap_urls:
                                result = await check_sitemap_url(sitemap_url)
                                if result:
                                    sitemap_data["sitemap_found"] = True
                                    break
        except Exception as e:
            logger.error(f"Error checking robots.txt for sitemap: {e}")

        sitemap_data["issues"] = sitemap_issues
        return sitemap_data 