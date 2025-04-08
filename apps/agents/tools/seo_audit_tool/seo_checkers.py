"""SEO check implementations for the SEO Audit Tool."""
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse, urljoin
import logging
import aiohttp
import re
from bs4 import BeautifulSoup
from datetime import datetime
from .content_type_detector import determine_content_type
from apps.agents.tools.content_expertise_tool.content_expertise_tool import ContentExpertiseTool
from apps.agents.tools.business_credibility_tool.business_credibility_tool import BusinessCredibilityTool
import json

logger = logging.getLogger(__name__)

class SEOChecker:
    """Base class for SEO checks."""

    @staticmethod
    def create_issue(
        issue_type: str,
        issue: str,
        url: str,
        value: Any = None,
        severity: str = "medium",
        details: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Create a standardized issue object.

        Args:
            issue_type: The type of issue (must match one of the ISSUE_TYPES in SEOAuditIssue model)
            issue: A human-readable description of the issue
            url: The URL where the issue was found
            value: The specific value that caused the issue (optional)
            severity: The severity level (critical, high, medium, low, info)
            details: Additional structured details about the issue

        Returns:
            A standardized issue dictionary
        """
        if not details:
            details = {}

        # Ensure severity is one of the allowed values
        allowed_severities = {'critical', 'high', 'medium', 'low', 'info'}
        if severity not in allowed_severities:
            severity = 'medium'

        # Create the standardized issue object
        issue_obj = {
            "type": issue_type,
            "issue": issue,
            "url": url,
            "severity": severity,
            "value": value,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }

        return issue_obj

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
        url = page_data.get("url", "")
        metadata = page_data.get("metadata", {})

        # Title tag checks
        title = page_data.get("title", "").strip() or metadata.get("title", "").strip()
        if not title:
            issues.append(SEOChecker.create_issue(
                issue_type="title",
                issue="Missing title tag",
                url=url,
                value=None,
                severity="critical"
            ))
        elif len(title) < 10:
            issues.append(SEOChecker.create_issue(
                issue_type="title",
                issue=f"Title tag too short ({len(title)} chars)",
                url=url,
                value=title,
                severity="high",
                details={"length": len(title)}
            ))
        elif len(title) > 60:
            issues.append(SEOChecker.create_issue(
                issue_type="title",
                issue=f"Title tag too long ({len(title)} chars)",
                url=url,
                value=title,
                severity="medium",
                details={"length": len(title)}
            ))

        # Meta description checks
        meta_desc = page_data.get("meta_description", "").strip() or metadata.get("meta_description", "").strip()
        if not meta_desc:
            issues.append(SEOChecker.create_issue(
                issue_type="meta_description",
                issue="Missing meta description",
                url=url,
                value=None,
                severity="high"
            ))
        elif len(meta_desc) < 50:
            issues.append(SEOChecker.create_issue(
                issue_type="meta_description",
                issue=f"Meta description too short ({len(meta_desc)} chars)",
                url=url,
                value=meta_desc,
                severity="medium",
                details={"length": len(meta_desc)}
            ))
        elif len(meta_desc) > 160:
            issues.append(SEOChecker.create_issue(
                issue_type="meta_description",
                issue=f"Meta description too long ({len(meta_desc)} chars)",
                url=url,
                value=meta_desc,
                severity="low",
                details={"length": len(meta_desc)}
            ))

        # Viewport checks
        if not page_data.get("viewport"):
            issues.append(SEOChecker.create_issue(
                issue_type="viewport_missing",
                issue="Missing viewport meta tag",
                url=url,
                value=None,
                severity="high"
            ))

        # Check for enhanced metadata
        enhanced_metadata_issues = SEOChecker.check_enhanced_metadata(page_data)
        issues.extend(enhanced_metadata_issues)

        return issues

    @staticmethod
    def check_enhanced_metadata(page_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check enhanced metadata including Open Graph, Twitter Cards, and structured data."""
        issues = []
        url = page_data.get("url", "")
        metadata = page_data.get("metadata", {})
        html = page_data.get("html", "")

        # Viewport checks
        viewport = metadata.get("viewport", "")

        # If viewport not found in metadata, try to find it in HTML
        if not viewport and html:
            viewport_pattern = re.compile(r'<meta[^>]*name=["\']viewport["\'][^>]*content=["\']([^"\'>]*)["\'][^>]*>', re.IGNORECASE)
            viewport_match = viewport_pattern.search(html)
            if viewport_match:
                viewport = viewport_match.group(1)

        if not viewport:
            issues.append(SEOChecker.create_issue(
                issue_type="viewport_missing",
                issue="Missing viewport meta tag",
                url=url,
                value=None,
                severity="high",
                details={"impact": "Poor mobile experience"}
            ))
        elif "width=device-width" not in viewport.lower():
            issues.append(SEOChecker.create_issue(
                issue_type="viewport_invalid",
                issue="Viewport missing width=device-width",
                url=url,
                value=viewport,
                severity="high",
                details={"viewport": viewport, "impact": "Poor mobile experience"}
            ))
        elif "initial-scale=1" not in viewport.lower():
            issues.append(SEOChecker.create_issue(
                issue_type="viewport_invalid",
                issue="Viewport missing initial-scale=1",
                url=url,
                value=viewport,
                severity="medium",
                details={"viewport": viewport, "impact": "Inconsistent mobile rendering"}
            ))

        # Canonical URL checks
        canonical_url = page_data.get("canonical_url", "") or metadata.get("canonical", "")

        # If canonical not found in metadata, try to find it in HTML
        if not canonical_url and html:
            canonical_pattern = re.compile(r'<link[^>]*rel=["\']canonical["\'][^>]*href=["\']([^"\'>]*)["\'][^>]*>', re.IGNORECASE)
            canonical_match = canonical_pattern.search(html)
            if canonical_match:
                canonical_url = canonical_match.group(1)

        if not canonical_url and not metadata.get("robots", "").lower().find("noindex") >= 0:
            issues.append(SEOChecker.create_issue(
                issue_type="canonical_missing",
                issue="Missing canonical URL",
                url=url,
                value=None,
                severity="medium",
                details={"impact": "Potential duplicate content issues"}
            ))
        elif canonical_url and canonical_url != url and not url.rstrip('/') == canonical_url.rstrip('/'):
            issues.append(SEOChecker.create_issue(
                issue_type="canonical_different",
                issue="Canonical URL differs from current URL",
                url=url,
                value=canonical_url,
                severity="low",
                details={"canonical": canonical_url, "impact": "This page may not be the primary version"}
            ))

        # Open Graph checks
        og_title = metadata.get("og_title", "") or metadata.get("og:title", "")
        og_description = metadata.get("og_description", "") or metadata.get("og:description", "")
        og_image = metadata.get("og_image", "") or metadata.get("og:image", "")
        og_type = metadata.get("og_type", "") or metadata.get("og:type", "")

        # If Open Graph tags not found in metadata, try to find them in HTML
        if not (og_title and og_description and og_image and og_type) and html:
            # Check for og:title
            if not og_title:
                og_title_pattern = re.compile(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\'>]*)["\'][^>]*>', re.IGNORECASE)
                og_title_match = og_title_pattern.search(html)
                if og_title_match:
                    og_title = og_title_match.group(1)

            # Check for og:description
            if not og_description:
                og_desc_pattern = re.compile(r'<meta[^>]*property=["\']og:description["\'][^>]*content=["\']([^"\'>]*)["\'][^>]*>', re.IGNORECASE)
                og_desc_match = og_desc_pattern.search(html)
                if og_desc_match:
                    og_description = og_desc_match.group(1)

            # Check for og:image
            if not og_image:
                og_image_pattern = re.compile(r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\'>]*)["\'][^>]*>', re.IGNORECASE)
                og_image_match = og_image_pattern.search(html)
                if og_image_match:
                    og_image = og_image_match.group(1)

            # Check for og:type
            if not og_type:
                og_type_pattern = re.compile(r'<meta[^>]*property=["\']og:type["\'][^>]*content=["\']([^"\'>]*)["\'][^>]*>', re.IGNORECASE)
                og_type_match = og_type_pattern.search(html)
                if og_type_match:
                    og_type = og_type_match.group(1)

        if not og_title:
            issues.append(SEOChecker.create_issue(
                issue_type="og_title_missing",
                issue="Missing Open Graph title",
                url=url,
                value=None,
                severity="medium",
                details={"impact": "Poor social media sharing experience"}
            ))

        if not og_description:
            issues.append(SEOChecker.create_issue(
                issue_type="og_description_missing",
                issue="Missing Open Graph description",
                url=url,
                value=None,
                severity="medium",
                details={"impact": "Poor social media sharing experience"}
            ))

        if not og_image:
            issues.append(SEOChecker.create_issue(
                issue_type="og_image_missing",
                issue="Missing Open Graph image",
                url=url,
                value=None,
                severity="medium",
                details={"impact": "Poor social media sharing experience"}
            ))

        if not og_type:
            issues.append(SEOChecker.create_issue(
                issue_type="og_type_missing",
                issue="Missing Open Graph type",
                url=url,
                value=None,
                severity="low",
                details={"impact": "Ambiguous content type for social media"}
            ))

        # Twitter Card checks
        twitter_card = metadata.get("twitter_card", "") or metadata.get("twitter:card", "")
        twitter_title = metadata.get("twitter_title", "") or metadata.get("twitter:title", "")
        twitter_description = metadata.get("twitter_description", "") or metadata.get("twitter:description", "")
        twitter_image = metadata.get("twitter_image", "") or metadata.get("twitter:image", "")

        # If Twitter Card tags not found in metadata, try to find them in HTML
        if not (twitter_card and twitter_title and twitter_description and twitter_image) and html:
            # Check for twitter:card
            if not twitter_card:
                # Try with name attribute
                twitter_card_pattern1 = re.compile(r'<meta[^>]*name=["\']twitter:card["\'][^>]*content=["\']([^"\'>]*)["\'][^>]*>', re.IGNORECASE)
                twitter_card_match1 = twitter_card_pattern1.search(html)
                if twitter_card_match1:
                    twitter_card = twitter_card_match1.group(1)
                else:
                    # Try with property attribute
                    twitter_card_pattern2 = re.compile(r'<meta[^>]*property=["\']twitter:card["\'][^>]*content=["\']([^"\'>]*)["\'][^>]*>', re.IGNORECASE)
                    twitter_card_match2 = twitter_card_pattern2.search(html)
                    if twitter_card_match2:
                        twitter_card = twitter_card_match2.group(1)

            # Check for twitter:title
            if not twitter_title:
                # Try with name attribute
                twitter_title_pattern1 = re.compile(r'<meta[^>]*name=["\']twitter:title["\'][^>]*content=["\']([^"\'>]*)["\'][^>]*>', re.IGNORECASE)
                twitter_title_match1 = twitter_title_pattern1.search(html)
                if twitter_title_match1:
                    twitter_title = twitter_title_match1.group(1)
                else:
                    # Try with property attribute
                    twitter_title_pattern2 = re.compile(r'<meta[^>]*property=["\']twitter:title["\'][^>]*content=["\']([^"\'>]*)["\'][^>]*>', re.IGNORECASE)
                    twitter_title_match2 = twitter_title_pattern2.search(html)
                    if twitter_title_match2:
                        twitter_title = twitter_title_match2.group(1)

            # Check for twitter:description
            if not twitter_description:
                # Try with name attribute
                twitter_desc_pattern1 = re.compile(r'<meta[^>]*name=["\']twitter:description["\'][^>]*content=["\']([^"\'>]*)["\'][^>]*>', re.IGNORECASE)
                twitter_desc_match1 = twitter_desc_pattern1.search(html)
                if twitter_desc_match1:
                    twitter_description = twitter_desc_match1.group(1)
                else:
                    # Try with property attribute
                    twitter_desc_pattern2 = re.compile(r'<meta[^>]*property=["\']twitter:description["\'][^>]*content=["\']([^"\'>]*)["\'][^>]*>', re.IGNORECASE)
                    twitter_desc_match2 = twitter_desc_pattern2.search(html)
                    if twitter_desc_match2:
                        twitter_description = twitter_desc_match2.group(1)

            # Check for twitter:image
            if not twitter_image:
                # Try with name attribute
                twitter_image_pattern1 = re.compile(r'<meta[^>]*name=["\']twitter:image["\'][^>]*content=["\']([^"\'>]*)["\'][^>]*>', re.IGNORECASE)
                twitter_image_match1 = twitter_image_pattern1.search(html)
                if twitter_image_match1:
                    twitter_image = twitter_image_match1.group(1)
                else:
                    # Try with property attribute
                    twitter_image_pattern2 = re.compile(r'<meta[^>]*property=["\']twitter:image["\'][^>]*content=["\']([^"\'>]*)["\'][^>]*>', re.IGNORECASE)
                    twitter_image_match2 = twitter_image_pattern2.search(html)
                    if twitter_image_match2:
                        twitter_image = twitter_image_match2.group(1)

        if not twitter_card:
            issues.append(SEOChecker.create_issue(
                issue_type="twitter_card_missing",
                issue="Missing Twitter Card type",
                url=url,
                value=None,
                severity="medium",
                details={"impact": "Poor Twitter sharing experience"}
            ))

        if not twitter_title:
            issues.append(SEOChecker.create_issue(
                issue_type="twitter_title_missing",
                issue="Missing Twitter Card title",
                url=url,
                value=None,
                severity="medium",
                details={"impact": "Poor Twitter sharing experience"}
            ))

        if not twitter_description:
            issues.append(SEOChecker.create_issue(
                issue_type="twitter_description_missing",
                issue="Missing Twitter Card description",
                url=url,
                value=None,
                severity="medium",
                details={"impact": "Poor Twitter sharing experience"}
            ))

        if not twitter_image:
            issues.append(SEOChecker.create_issue(
                issue_type="twitter_image_missing",
                issue="Missing Twitter Card image",
                url=url,
                value=None,
                severity="medium",
                details={"impact": "Poor Twitter sharing experience"}
            ))

        # Check for structured data (JSON-LD)
        if html and "application/ld+json" not in html:
            issues.append(SEOChecker.create_issue(
                issue_type="structured_data_missing",
                issue="Missing structured data (JSON-LD)",
                url=url,
                value=None,
                severity="medium",
                details={"impact": "Missing rich snippets in search results"}
            ))

        # Language tag checks
        language = metadata.get("language", "")
        if not language:
            issues.append(SEOChecker.create_issue(
                issue_type="language_missing",
                issue="Missing language declaration",
                url=url,
                value=None,
                severity="low",
                details={"impact": "Search engines may misidentify the page language"}
            ))

        return issues

    @staticmethod
    def check_headings(page_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check heading structure."""
        issues = []
        url = page_data.get("url", "")

        # H1 tag checks
        h1_tags = page_data.get("h1_tags", [])
        if not h1_tags:
            issues.append(SEOChecker.create_issue(
                issue_type="h1",
                issue="Missing H1 tag",
                url=url,
                value=None,
                severity="high"
            ))
        elif len(h1_tags) > 1:
            issues.append(SEOChecker.create_issue(
                issue_type="h1",
                issue=f"Multiple H1 tags ({len(h1_tags)})",
                url=url,
                value=h1_tags,
                severity="medium",
                details={"count": len(h1_tags), "h1_contents": h1_tags}
            ))

        return issues

    @staticmethod
    def check_images(page_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check image optimization."""
        issues = []
        page_url = page_data.get("url", "")
        images = page_data.get("images", [])

        for img in images:
            img_url = img.get("src", "")

            # Alt text checks
            if not img.get("alt"):
                issues.append(SEOChecker.create_issue(
                    issue_type="missing_alt",
                    issue="Missing alt text",
                    url=page_url,
                    value=img_url,
                    severity="medium",
                    details={"image_url": img_url}
                ))
            elif len(img.get("alt", "")) < 3:
                issues.append(SEOChecker.create_issue(
                    issue_type="short_alt",
                    issue="Alt text too short",
                    url=page_url,
                    value=img.get("alt"),
                    severity="medium",
                    details={"image_url": img_url, "alt_length": len(img.get("alt", ""))}
                ))

            # Dimension checks
            width = img.get("width")
            height = img.get("height")
            if not (width and height):
                issues.append(SEOChecker.create_issue(
                    issue_type="missing_dimensions",
                    issue="Missing width/height attributes",
                    url=page_url,
                    value=img_url,
                    severity="medium",
                    details={"image_url": img_url, "width": width, "height": height}
                ))

            # Filename checks
            filename = img_url.split("/")[-1]
            if filename.lower().startswith(("img", "image", "pic", "dsc")):
                issues.append(SEOChecker.create_issue(
                    issue_type="generic_filename",
                    issue="Generic image filename",
                    url=page_url,
                    value=filename,
                    severity="low",
                    details={"image_url": img_url}
                ))

            # Size checks
            size = img.get("size", 0)
            if size > 500000:  # 500KB
                issues.append(SEOChecker.create_issue(
                    issue_type="large_size",
                    issue=f"Image size too large ({size/1000:.0f}KB)",
                    url=page_url,
                    value=img_url,
                    severity="high",
                    details={"image_url": img_url, "size_kb": size/1000}
                ))

            # Lazy loading check
            if not img.get("loading") == "lazy":
                issues.append(SEOChecker.create_issue(
                    issue_type="no_lazy_loading",
                    issue="Image missing lazy loading",
                    url=page_url,
                    value=img_url,
                    severity="high",
                    details={"image_url": img_url}
                ))

            # Responsive image checks
            if not img.get("srcset"):
                issues.append(SEOChecker.create_issue(
                    issue_type="no_srcset",
                    issue="Image missing responsive srcset",
                    url=page_url,
                    value=img_url,
                    severity="medium",
                    details={"image_url": img_url}
                ))

        return issues

    @staticmethod
    def check_links(page_data: Dict[str, Any], base_domain: str) -> List[str]:
        """Extract and check internal links."""
        internal_links = []
        page_links = page_data.get("links", [])

        for link in page_links:
            # Format 1: Dictionary with 'url' key (from some crawlers)
            if isinstance(link, dict) and 'url' in link:
                link_url = link.get('url', '')
                if link_url and urlparse(link_url).netloc == base_domain:
                    internal_links.append(link_url)
            # Format 2: Dictionary with 'href' key (from Playwright crawler)
            elif isinstance(link, dict) and 'href' in link:
                link_url = link.get('href', '')
                if link_url and urlparse(link_url).netloc == base_domain:
                    internal_links.append(link_url)
            # Format 3: Simple string URL (from older crawlers)
            elif isinstance(link, str):
                if urlparse(link).netloc == base_domain:
                    internal_links.append(link)
            # Log unexpected link types
            else:
                logging.warning(f"Unexpected link type: {type(link)} - {link}")

        return internal_links

    @staticmethod
    def check_content(page_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check content quality and structure."""
        issues = []
        url = page_data.get("url", "")
        text_content = page_data.get("text_content", "")
        word_count = len(text_content.split())

        # Content length check
        if word_count < 300:
            issues.append(SEOChecker.create_issue(
                issue_type="thin_content",
                issue=f"Thin content ({word_count} words)",
                url=url,
                value=word_count,
                severity="medium",
                details={"word_count": word_count}
            ))

        # Check for keyword density and readability if content exists
        if text_content:
            # Add readability score check
            sentences = len(re.split(r'[.!?]+', text_content))
            if sentences > 0:
                avg_words_per_sentence = word_count / sentences
                if avg_words_per_sentence > 25:
                    issues.append(SEOChecker.create_issue(
                        issue_type="readability",
                        issue=f"Sentences too long (avg {avg_words_per_sentence:.1f} words)",
                        url=url,
                        value=avg_words_per_sentence,
                        severity="medium",
                        details={
                            "avg_words_per_sentence": avg_words_per_sentence,
                            "total_sentences": sentences,
                            "total_words": word_count
                        }
                    ))

            # Check for long paragraphs
            paragraphs = [p.strip() for p in text_content.split('\n\n') if p.strip()]
            for i, para in enumerate(paragraphs):
                para_words = len(para.split())
                if para_words > 150:  # Generally, 150 words is considered a long paragraph
                    issues.append(SEOChecker.create_issue(
                        issue_type="long_paragraph",
                        issue=f"Long paragraph detected ({para_words} words)",
                        url=url,
                        value=para_words,
                        severity="low",
                        details={
                            "paragraph_index": i,
                            "word_count": para_words,
                            "paragraph_preview": para[:100] + "..." if len(para) > 100 else para
                        }
                    ))

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
            issues.append(SEOChecker.create_issue(
                issue_type="canonical_missing",
                issue="Missing canonical tag",
                url=url,
                value=None,
                severity="high",
                details={"page_type": "content" if page_content else "unknown"}
            ))
            return issues

        # Validate canonical URL format
        if not canonical_url.startswith(('http://', 'https://')):
            issues.append(SEOChecker.create_issue(
                issue_type="canonical_invalid_format",
                issue="Invalid canonical URL format",
                url=url,
                value=canonical_url,
                severity="high",
                details={"canonical_url": canonical_url}
            ))

        # Check for self-referential canonical
        if canonical_url != url:
            # If the page is pointing to a different URL, check if it might be a duplicate
            if page_content:
                issues.append(SEOChecker.create_issue(
                    issue_type="canonical_different",
                    issue="Canonical URL points to a different page",
                    url=url,
                    value=canonical_url,
                    severity="medium",
                    details={
                        "canonical_url": canonical_url,
                        "content_length": len(page_content)
                    }
                ))

        # Check for relative canonical URLs
        if canonical_url.startswith('/'):
            issues.append(SEOChecker.create_issue(
                issue_type="canonical_relative",
                issue="Canonical URL is relative",
                url=url,
                value=canonical_url,
                severity="medium",
                details={"canonical_url": canonical_url}
            ))

        # Check for multiple canonical tags
        canonical_count = page_data.get("canonical_count", 0)
        if canonical_count > 1:
            issues.append(SEOChecker.create_issue(
                issue_type="canonical_multiple",
                issue=f"Multiple canonical tags found ({canonical_count})",
                url=url,
                value=str(canonical_count),
                severity="critical",
                details={
                    "canonical_count": canonical_count,
                    "canonical_url": canonical_url
                }
            ))

        # Check for canonical on non-canonical pages
        if page_data.get("is_pagination", False) and canonical_url == url:
            issues.append(SEOChecker.create_issue(
                issue_type="canonical_on_pagination",
                issue="Self-referential canonical on paginated page",
                url=url,
                value=canonical_url,
                severity="medium",
                details={"is_pagination": True}
            ))

        # Check for canonical chain (if available)
        canonical_chain = page_data.get("canonical_chain", [])
        if len(canonical_chain) > 1:
            issues.append(SEOChecker.create_issue(
                issue_type="canonical_chain",
                issue=f"Canonical chain detected (length: {len(canonical_chain)})",
                url=url,
                value=" -> ".join(canonical_chain),
                severity="high",
                details={
                    "chain_length": len(canonical_chain),
                    "canonical_chain": canonical_chain
                }
            ))

        return issues

    @staticmethod
    def get_page_metrics(page_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate page metrics for analysis."""
        images = page_data.get("images", [])
        metadata = page_data.get("metadata", {})

        # Get title from either direct page data or metadata
        title = page_data.get("title", "") or metadata.get("title", "")
        meta_description = page_data.get("meta_description", "") or metadata.get("meta_description", "")
        canonical_url = page_data.get("canonical_url", "") or metadata.get("canonical", "")

        # Get social media metrics
        has_og_tags = bool(metadata.get("og_title") or metadata.get("og_description") or metadata.get("og_image"))
        has_twitter_tags = bool(metadata.get("twitter_card") or metadata.get("twitter_title") or metadata.get("twitter_description"))

        # Check for structured data
        has_structured_data = "application/ld+json" in page_data.get("html", "") if page_data.get("html") else False

        return {
            "url": page_data["url"],
            "title_length": len(title),
            "meta_description_length": len(meta_description),
            "h1_count": len(page_data.get("h1_tags", [])),
            "outbound_links": len(page_data.get("links", [])),
            "content_length": len(page_data.get("text_content", "")),
            "image_count": len(images),
            "images_without_alt": sum(1 for img in images if not img.get("alt")),
            "total_image_size": sum(img.get("size", 0) for img in images),
            "timestamp": page_data.get("crawl_timestamp"),
            "has_canonical": bool(canonical_url),
            "canonical_url": canonical_url,
            "canonical_count": page_data.get("canonical_count", 0),
            # Enhanced metadata metrics
            "has_viewport": bool(metadata.get("viewport")),
            "has_og_tags": has_og_tags,
            "has_twitter_tags": has_twitter_tags,
            "has_structured_data": has_structured_data,
            "has_language_tag": bool(metadata.get("language")),
            "robots_directive": metadata.get("robots", ""),
            "is_noindex": "noindex" in metadata.get("robots", "").lower() if metadata.get("robots") else False
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
                # Add a standard User-Agent header
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
                }
                async with aiohttp.ClientSession(headers=headers) as session:
                    async with session.get(sitemap_url, allow_redirects=True, timeout=15) as response:
                        if response.status != 200:
                            sitemap_issues.append(SEOChecker.create_issue(
                                issue_type="sitemap_http_error",
                                issue=f"Sitemap HTTP error {response.status}",
                                url=sitemap_url,
                                value=str(response.status),
                                severity="medium"
                            ))
                            return None

                        content = await response.text()
                        # Explicitly use lxml-xml parser if available
                        try:
                            soup = BeautifulSoup(content, 'lxml-xml')
                        except ImportError:
                            soup = BeautifulSoup(content, 'xml') # Fallback to default xml

                        # --- Add Logging ---
                        root_element = soup.find() # Get the first element tag
                        logger.debug(f"Sitemap Check: URL={sitemap_url}, Root element found: {root_element.name if root_element else 'None'}")
                        # --- End Logging ---

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
                                    sitemap_issues.append(SEOChecker.create_issue(
                                        issue_type="missing_url",
                                        issue="URL entry missing location",
                                        url=sitemap_url,
                                        value="",
                                        severity="high",
                                        details={"sitemap_type": sitemap_data["sitemap_type"]}
                                    ))
                                    continue

                                url_str = loc.text.strip()
                                if not url_str.startswith(('http://', 'https://')):
                                    sitemap_issues.append(SEOChecker.create_issue(
                                        issue_type="invalid_url",
                                        issue="Invalid URL format",
                                        url=url_str,
                                        value=url_str,
                                        severity="high",
                                        details={"sitemap_url": sitemap_url}
                                    ))
                                    continue

                                result["valid_urls"] += 1

                                # Check optional elements
                                if url.find('lastmod'):
                                    result["last_modified_dates"] += 1
                                    # Validate lastmod format
                                    lastmod = url.find('lastmod').text
                                    if not re.match(r'^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}(\+\d{2}:\d{2}|Z)?)?$', lastmod):
                                        sitemap_issues.append(SEOChecker.create_issue(
                                            issue_type="invalid_lastmod",
                                            issue="Invalid lastmod date format",
                                            url=url_str,
                                            value=lastmod,
                                            severity="medium",
                                            details={"sitemap_url": sitemap_url}
                                        ))

                                if url.find('changefreq'):
                                    result["change_frequencies"] += 1
                                    # Validate changefreq value
                                    changefreq = url.find('changefreq').text
                                    if changefreq not in ['always', 'hourly', 'daily', 'weekly', 'monthly', 'yearly', 'never']:
                                        sitemap_issues.append(SEOChecker.create_issue(
                                            issue_type="invalid_changefreq",
                                            issue="Invalid changefreq value",
                                            url=url_str,
                                            value=changefreq,
                                            severity="low",
                                            details={"sitemap_url": sitemap_url, "allowed_values": ['always', 'hourly', 'daily', 'weekly', 'monthly', 'yearly', 'never']}
                                        ))

                                if url.find('priority'):
                                    result["priorities"] += 1
                                    # Validate priority value
                                    priority = url.find('priority').text
                                    try:
                                        priority_float = float(priority)
                                        if not 0.0 <= priority_float <= 1.0:
                                            sitemap_issues.append(SEOChecker.create_issue(
                                                issue_type="invalid_priority",
                                                issue="Priority value out of range (0.0-1.0)",
                                                url=url_str,
                                                value=priority,
                                                severity="low",
                                                details={"sitemap_url": sitemap_url, "allowed_range": "0.0-1.0"}
                                            ))
                                    except ValueError:
                                        sitemap_issues.append(SEOChecker.create_issue(
                                            issue_type="invalid_priority",
                                            issue="Invalid priority value format",
                                            url=url_str,
                                            value=priority,
                                            severity="low",
                                            details={"sitemap_url": sitemap_url}
                                        ))

                            return result

            except Exception as e:
                sitemap_issues.append(SEOChecker.create_issue(
                    issue_type="sitemap_error",
                    issue=f"Error processing sitemap: {str(e)}",
                    url=sitemap_url,
                    value=str(e),
                    severity="high",
                    details={"error_type": type(e).__name__}
                ))
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
            # Add a standard User-Agent header for robots.txt check too
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
            }
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(f"{base_url}/robots.txt", timeout=10) as response:
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

    @staticmethod
    def check_social_media_tags(page_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check social media meta tags including OpenGraph and Twitter Cards."""
        issues = []
        url = page_data.get("url", "")

        # OpenGraph checks
        og_title = page_data.get("og_title", "")
        og_description = page_data.get("og_description", "")
        og_image = page_data.get("og_image", "")

        if not og_title:
            issues.append({
                "type": "og_title_missing",
                "issue": "Missing OpenGraph title tag",
                "url": url,
                "value": None,
                "severity": "medium"
            })

        if not og_description:
            issues.append({
                "type": "og_description_missing",
                "issue": "Missing OpenGraph description tag",
                "url": url,
                "value": None,
                "severity": "medium"
            })

        if not og_image:
            issues.append({
                "type": "og_image_missing",
                "issue": "Missing OpenGraph image tag",
                "url": url,
                "value": None,
                "severity": "medium"
            })
        elif not og_image.startswith(('http://', 'https://')):
            issues.append({
                "type": "og_image_invalid",
                "issue": "Invalid OpenGraph image URL format",
                "url": url,
                "value": og_image,
                "severity": "medium"
            })

        return issues

    @staticmethod
    def check_semantic_structure(page_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check HTML5 semantic structure."""
        issues = []
        url = page_data.get("url", "")
        page_type = page_data.get("page_type", "content")

        # Define semantic elements and their requirements based on page type
        semantic_elements = {
            'header': {
                'purpose': 'Main header/banner area',
                'required_for': ['content', 'landing', 'blog', 'article', 'product'],
                'optional_for': ['search', 'category', 'error']
            },
            'main': {
                'purpose': 'Primary content area',
                'required_for': ['*'],  # Required for all pages
                'optional_for': []
            },
            'nav': {
                'purpose': 'Navigation menu',
                'required_for': ['content', 'landing', 'blog', 'article', 'product'],
                'optional_for': ['search', 'category', 'error']
            },
            'footer': {
                'purpose': 'Footer area',
                'required_for': ['content', 'landing', 'blog', 'article', 'product'],
                'optional_for': ['search', 'category', 'error']
            },
            'article': {
                'purpose': 'Self-contained content',
                'required_for': ['blog', 'article', 'news'],
                'optional_for': ['content', 'product']
            },
            'section': {
                'purpose': 'Thematic grouping of content',
                'required_for': [],
                'optional_for': ['*']  # Optional for all pages
            },
            'aside': {
                'purpose': 'Sidebar/complementary content',
                'required_for': [],
                'optional_for': ['*']  # Optional for all pages
            }
        }

        # Check for required semantic elements based on page type
        for element, config in semantic_elements.items():
            is_required = (
                '*' in config['required_for'] or
                page_type in config['required_for']
            )
            is_optional = (
                '*' in config['optional_for'] or
                page_type in config['optional_for']
            )

            if not page_data.get(f"has_{element}"):
                if is_required:
                    issues.append(SEOChecker.create_issue(
                        issue_type="semantic_structure",
                        issue=f"Missing required {element} semantic element",
                        url=url,
                        value=element,
                        severity="high" if element == 'main' else "medium",
                        details={
                            "element_type": element,
                            "element_purpose": config['purpose'],
                            "page_type": page_type,
                            "is_required": True,
                            "requirement_reason": "Required for this page type"
                        }
                    ))
                elif is_optional:
                    issues.append(SEOChecker.create_issue(
                        issue_type="semantic_structure",
                        issue=f"Missing recommended {element} semantic element",
                        url=url,
                        value=element,
                        severity="low",
                        details={
                            "element_type": element,
                            "element_purpose": config['purpose'],
                            "page_type": page_type,
                            "is_required": False,
                            "requirement_reason": "Recommended for better structure"
                        }
                    ))

        # Check for proper nesting of semantic elements
        if page_data.get("semantic_nesting_issues"):
            for issue in page_data["semantic_nesting_issues"]:
                issues.append(SEOChecker.create_issue(
                    issue_type="semantic_nesting",
                    issue=f"Improper nesting of semantic elements: {issue['elements']}",
                    url=url,
                    value=issue['elements'],
                    severity="medium",
                    details={
                        "parent_element": issue.get("parent"),
                        "child_element": issue.get("child"),
                        "recommended_structure": issue.get("recommendation"),
                        "page_type": page_type
                    }
                ))

        # Check for empty semantic elements
        if page_data.get("empty_semantic_elements"):
            for element in page_data["empty_semantic_elements"]:
                # Only report empty elements if they're required or used
                if element in semantic_elements:
                    issues.append(SEOChecker.create_issue(
                        issue_type="empty_semantic_element",
                        issue=f"Empty {element} semantic element",
                        url=url,
                        value=element,
                        severity="low",
                        details={
                            "element_type": element,
                            "element_purpose": semantic_elements[element]['purpose'],
                            "page_type": page_type,
                            "is_required": (
                                '*' in semantic_elements[element]['required_for'] or
                                page_type in semantic_elements[element]['required_for']
                            )
                        }
                    ))

        return issues

    @staticmethod
    def check_redirect_chains(page_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check for redirect chains and loops."""
        issues = []
        url = page_data.get("url", "")
        redirects = page_data.get("redirect_chain", [])

        # Check for long redirect chains
        if len(redirects) > 2:  # More than 2 redirects in chain
            issues.append(SEOChecker.create_issue(
                issue_type="redirect_chain",
                issue=f"Long redirect chain detected ({len(redirects)} redirects)",
                url=url,
                value=redirects,
                severity="high",
                details={
                    "chain_length": len(redirects),
                    "redirect_chain": redirects,
                    "final_url": redirects[-1] if redirects else url,
                    "hops": len(redirects) - 1
                }
            ))

        # Check for redirect loops
        if len(redirects) != len(set(redirects)):
            issues.append(SEOChecker.create_issue(
                issue_type="redirect_loop",
                issue="Redirect loop detected",
                url=url,
                value=redirects,
                severity="critical",
                details={
                    "chain_length": len(redirects),
                    "redirect_chain": redirects,
                    "unique_urls": len(set(redirects))
                }
            ))

        # Check for meta refresh redirects
        if page_data.get("meta_refresh"):
            issues.append(SEOChecker.create_issue(
                issue_type="meta_refresh",
                issue="Meta refresh redirect detected",
                url=url,
                value=page_data.get("meta_refresh_url"),
                severity="medium",
                details={
                    "refresh_delay": page_data.get("meta_refresh_delay", 0),
                    "target_url": page_data.get("meta_refresh_url"),
                    "is_immediate": page_data.get("meta_refresh_delay", 0) == 0
                }
            ))

        return issues

    @staticmethod
    def check_robots_indexing(page_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check robots.txt and indexing directives."""
        issues = []
        url = page_data.get("url", "")

        # Check noindex directives
        if page_data.get("noindex"):
            issues.append(SEOChecker.create_issue(
                issue_type="noindex_detected",
                issue="Page has noindex directive",
                url=url,
                value=page_data.get("noindex_source", "meta"),
                severity="critical",
                details={
                    "source": page_data.get("noindex_source", "meta"),
                    "directive_type": "noindex",
                    "is_intentional": page_data.get("noindex_intentional", False)
                }
            ))

        # Check X-Robots-Tag header
        if page_data.get("x_robots_tag"):
            x_robots = page_data["x_robots_tag"]
            if "noindex" in x_robots or "none" in x_robots:
                issues.append(SEOChecker.create_issue(
                    issue_type="indexing_blocked",
                    issue="Indexing blocked by X-Robots-Tag header",
                    url=url,
                    value=x_robots,
                    severity="critical",
                    details={
                        "header_value": x_robots,
                        "directives": [d.strip() for d in x_robots.split(",")]
                    }
                ))

        # Check robots.txt blocking
        if page_data.get("robots_blocked"):
            issues.append(SEOChecker.create_issue(
                issue_type="robots_misconfiguration",
                issue="Page blocked by robots.txt",
                url=url,
                value=page_data.get("robots_directive", ""),
                severity="high",
                details={
                    "directive": page_data.get("robots_directive", ""),
                    "user_agent": page_data.get("robots_user_agent", "*")
                }
            ))

        return issues

    @staticmethod
    def check_eeat_signals(page_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check for E-E-A-T signals."""
        issues = []
        url = page_data.get("url", "")
        content_type = determine_content_type(page_data)
        logger.debug(f"Content type: {content_type}")
        # For local business homepage and general pages
        if content_type in ["business_homepage", "content", "about", "contact"]:
            try:
                # Use business credibility tool directly
                credibility_tool = BusinessCredibilityTool()
                result = credibility_tool._run(
                    text_content=page_data.get("text_content", ""),
                    html_content=page_data.get("html", "")
                )

                analysis = json.loads(result)
                logger.debug(f"Business credibility analysis: {analysis}")
                if "error" in analysis:
                    logger.error(f"Error in business credibility analysis: {analysis['message']}")
                    return []

                # Convert tool results into issues
                credibility_signals = analysis.get("credibility_signals", {})
                signal_details = analysis.get("signal_details", {})

                # Map missing signals to issues
                signal_to_issue = {
                    "business_info": ("business_info_missing", "Missing basic business information", "high"),
                    "years_in_business": ("years_missing", "Years in business not specified", "medium"),
                    "customer_reviews": ("reviews_missing", "No customer reviews/testimonials found", "medium"),
                    "services_list": ("services_missing", "Services/products not clearly listed", "medium"),
                    "certifications": ("certifications_missing", "No professional certifications found", "medium")
                }

                for signal, (issue_type, message, severity) in signal_to_issue.items():
                    if not credibility_signals.get(signal, False):
                        issues.append(SEOChecker.create_issue(
                            issue_type=issue_type,
                            issue=message,
                            url=url,
                            severity=severity,
                            details=signal_details.get(signal, {})
                        ))

            except Exception as e:
                logger.error(f"Error checking business credibility: {str(e)}")
                return []

        # For informational content, use content expertise tool
        elif content_type in ["blog", "article", "news"]:
            try:
                expertise_tool = ContentExpertiseTool()
                result = expertise_tool._run(
                    text_content=page_data.get("text_content", ""),
                    html_content=page_data.get("html", ""),
                    content_type=content_type,
                    url=url
                )

                analysis = json.loads(result)

                if "error" in analysis:
                    logger.error(f"Error in content expertise analysis: {analysis['message']}")
                    return []

                # Convert tool results into issues
                expertise_signals = analysis.get("expertise_signals", {})
                signal_details = analysis.get("signal_details", {})

                # Map missing signals to issues
                signal_to_issue = {
                    "has_author": ("author_missing", "Missing author information", "high"),
                    "has_author_bio": ("author_bio_missing", "Author bio missing", "medium"),
                    "has_credentials": ("author_credentials_missing", "Author credentials not specified", "medium"),
                    "has_citations": ("citations_missing", "No citations or references found", "medium"),
                    "has_freshness": ("freshness_missing", "No last updated date found", "low"),
                    "has_fact_checking": ("fact_checking_missing", "No fact-checking elements found", "medium"),
                    "has_structure": ("poor_structure", "Content structure needs improvement", "medium"),
                    "has_depth": ("shallow_coverage", "Topic coverage may be insufficient", "medium"),
                    "has_schema": ("schema_missing", "Missing appropriate Article schema markup", "medium")
                }

                for signal, (issue_type, message, severity) in signal_to_issue.items():
                    if not expertise_signals.get(signal, False):
                        issues.append(SEOChecker.create_issue(
                            issue_type=issue_type,
                            issue=message,
                            url=url,
                            severity=severity,
                            details=signal_details.get(signal, {})
                        ))

            except Exception as e:
                logger.error(f"Error checking content expertise: {str(e)}")
                return []

        return issues

    @staticmethod
    async def check_pagespeed_metrics(page_data: Dict[str, Any], pagespeed_tool) -> List[Dict[str, Any]]:
        """Check PageSpeed metrics for a page."""
        issues = []
        url = page_data.get("url", "")

        try:
            # Get PageSpeed data
            result = pagespeed_tool._run(
                url=url,
                strategy="mobile",
                categories=["performance", "accessibility", "best-practices", "seo"]
            )

            # Wait for the task to complete if it's pending
            if isinstance(result, dict) and result.get('status') == 'pending':
                task_id = result.get('task_id')
                if task_id:
                    from celery.result import AsyncResult
                    task_result = AsyncResult(task_id)
                    # Wait for the task to complete (this will block until the task is done)
                    result = task_result.get()

            # Process performance score
            performance_score = result.get('performance_score')
            if performance_score is not None and performance_score < 0.5:
                issues.append(SEOChecker.create_issue(
                    issue_type="performance_poor",
                    issue="Low performance score",
                    url=url,
                    value=str(performance_score * 100),
                    severity="high" if performance_score < 0.3 else "medium",
                    details={"score": performance_score}
                ))

            # Process Core Web Vitals
            lab_data = result.get('core_web_vitals', {}).get('lab_data', {})

            # Check LCP
            lcp = lab_data.get('lcp', {})
            if lcp and lcp.get('value') and lcp.get('value') > 2500:
                issues.append(SEOChecker.create_issue(
                    issue_type="lcp_poor",
                    issue="High Largest Contentful Paint (LCP)",
                    url=url,
                    value=f"{lcp.get('display_value')}",
                    severity="high" if lcp.get('value') > 4000 else "medium",
                    details={"metric": "LCP", "value": lcp.get('value')}
                ))

            # Check CLS
            cls = lab_data.get('cls', {})
            if cls and cls.get('value') and cls.get('value') > 0.1:
                issues.append(SEOChecker.create_issue(
                    issue_type="cls_poor",
                    issue="High Cumulative Layout Shift (CLS)",
                    url=url,
                    value=f"{cls.get('display_value')}",
                    severity="high" if cls.get('value') > 0.25 else "medium",
                    details={"metric": "CLS", "value": cls.get('value')}
                ))

            # Check TBT (Total Blocking Time)
            tbt = lab_data.get('tbt', {})
            if tbt and tbt.get('value') and tbt.get('value') > 300:
                issues.append(SEOChecker.create_issue(
                    issue_type="performance_poor",
                    issue="High Total Blocking Time (TBT)",
                    url=url,
                    value=f"{tbt.get('display_value')}",
                    severity="high" if tbt.get('value') > 600 else "medium",
                    details={"metric": "TBT", "value": tbt.get('value')}
                ))

            # Process opportunities
            opportunities = result.get('opportunities', {})
            for opp_id, opp_data in opportunities.items():
                if opp_data.get('score', 1) < 0.9:  # Only report significant opportunities
                    # Map opportunity types to valid issue types
                    issue_type = "performance_poor"
                    if "render-blocking" in opp_id:
                        issue_type = "performance_render-blocking-resources"
                    elif "unoptimized-images" in opp_id:
                        issue_type = "performance_unoptimized-images"
                    elif "unused-css" in opp_id:
                        issue_type = "performance_unused-css"
                    elif "unused-javascript" in opp_id:
                        issue_type = "performance_unused-javascript"
                    elif "server-response-time" in opp_id:
                        issue_type = "performance_server-response-time"

                    issues.append(SEOChecker.create_issue(
                        issue_type=issue_type,
                        issue=opp_data.get('title', 'Performance opportunity'),
                        url=url,
                        value=opp_data.get('display_value'),
                        severity="medium",
                        details={
                            "description": opp_data.get('description'),
                            "score": opp_data.get('score'),
                            "opportunity_id": opp_id
                        }
                    ))

            # Store the complete result in page_data
            page_data['pagespeed_data'] = result

        except Exception as e:
            logger.error(f"Error checking PageSpeed metrics for {url}: {str(e)}")
            issues.append(SEOChecker.create_issue(
                issue_type="pagespeed_error",
                issue="Error checking PageSpeed metrics",
                url=url,
                value=str(e),
                severity="high"
            ))
            # Store error in page_data
            page_data['pagespeed_data'] = {
                'status': 'error',
                'error': str(e)
            }

        return issues