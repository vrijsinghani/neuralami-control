import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import logging

logger = logging.getLogger(__name__)

class URLDeduplicator:
    def __init__(self):
        # Common CMS page identifiers
        self.cms_patterns = {
            'wordpress': [
                r'(?:page_id|p|post)=\d+',
                r'\d{4}/\d{2}/\d{2}',  # Date-based permalinks
                r'(?:category|tag)/[\w-]+',
            ],
            'woocommerce': [
                r'product=\d+',
                r'product-category/[\w-]+',
            ],
        }
        
        # Patterns that indicate filter/sort URLs
        self.filter_patterns = [
            # E-commerce filters
            r'product_type=\d+',
            r'prefilter=',
            r'filter=',
            r'sort=',
            r'order=',
            r'orderby=',
            
            # Faceted navigation
            r'facet=',
            r'facets=',
            
            # Search parameters
            r'q=',
            r'query=',
            r'search=',
            
            # Pagination
            r'page=',
            r'pg=',
            r'p=',
            r'paged=',
            
            # View settings
            r'view=',
            r'layout=',
            r'display=',
            r'show=',
            
            # Session and tracking
            r'utm_',
            r'gclid=',
            r'fbclid=',
            r'sessionid=',
        ]
    
    def should_process_url(self, url: str) -> bool:
        """
        Determine if a URL should be processed based on its characteristics.
        Returns True if the URL should be processed, False otherwise.
        """
        if not url:
            return False

        # Skip URLs with fragments
        if '#' in url:
            return False

        # Skip common file extensions
        if url.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.pdf', '.doc', '.docx', 
                               '.xls', '.xlsx', '.zip', '.tar', '.gz', '.css', '.js', '.xml')):
            return False

        # Skip URLs with tracking parameters
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        if any(param.startswith('utm_') or param in ['gclid', 'fbclid', 'sessionid'] 
               for param in query_params):
            return False

        # Skip URLs with specific patterns that indicate duplicate content
        if any(re.search(pattern, url) for pattern in self.filter_patterns):
            return False

        return True

    def is_likely_duplicate(self, url1, url2):
        """
        Determine if two URLs are likely duplicates by comparing their components
        and checking for common patterns that indicate they're the same content.
        """
        # Parse URLs
        parsed1 = urlparse(url1)
        parsed2 = urlparse(url2)
        
        # Different domains means definitely not duplicates
        if parsed1.netloc != parsed2.netloc:
            return False
        
        # Normalize paths (removing trailing slashes)
        path1 = parsed1.path.rstrip('/')
        path2 = parsed2.path.rstrip('/')
        
        # Exact path match is a strong indicator
        paths_match = (path1 == path2)
        
        # Check for CMS-specific patterns
        is_cms_page1 = any(re.search(pattern, url1) for patterns in self.cms_patterns.values() for pattern in patterns)
        is_cms_page2 = any(re.search(pattern, url2) for patterns in self.cms_patterns.values() for pattern in patterns)
        
        # Parse query parameters
        query1 = parse_qs(parsed1.query)
        query2 = parse_qs(parsed2.query)
        
        # If paths match and they're not special CMS pages, just check if filter params are different
        if paths_match and not (is_cms_page1 or is_cms_page2):
            # Remove known filter/sort/tracking parameters
            filtered_query1 = {k: v for k, v in query1.items() if not any(re.match(pattern, k) for pattern in self.filter_patterns)}
            filtered_query2 = {k: v for k, v in query2.items() if not any(re.match(pattern, k) for pattern in self.filter_patterns)}
            
            # If the only difference is in filter parameters, they're likely duplicates
            return filtered_query1 == filtered_query2
            
        # If one URL is a special CMS page and paths are different, check if they point to the same content
        if (is_cms_page1 or is_cms_page2) and path1 != path2:
            # Extract IDs from specific patterns - this is simplified and would need expansion
            id1 = self._extract_cms_id(url1)
            id2 = self._extract_cms_id(url2)
            
            if id1 and id2 and id1 == id2:
                return True
        
        # Otherwise, not duplicates
        return False
    
    def _extract_cms_id(self, url):
        """
        Extract CMS ID from a URL based on common patterns.
        Returns None if no ID can be extracted.
        """
        # Check for WordPress post ID
        wp_id_match = re.search(r'[?&](?:p|page_id|post)=(\d+)', url)
        if wp_id_match:
            return f"wp:{wp_id_match.group(1)}"
        
        # Check for WooCommerce product ID
        woo_id_match = re.search(r'[?&]product=(\d+)', url)
        if woo_id_match:
            return f"woo:{woo_id_match.group(1)}"
        
        # Add more CMS pattern extractors as needed
        
        return None
    
    def canonicalize_url(self, url):
        """
        Convert a URL to its canonical form by removing tracking parameters,
        sorting query parameters, and normalizing the path.
        """
        parsed = urlparse(url)
        
        # Normalize the path (ensure trailing slash consistency)
        path = parsed.path
        if not path:
            path = '/'
        elif path != '/' and not path.endswith('/'):
            path = path + '/'
        
        # Parse and filter query parameters
        query_params = parse_qs(parsed.query)
        
        # Remove tracking and session parameters
        tracking_patterns = [r'utm_', r'gclid', r'fbclid', r'sessionid']
        filtered_params = {k: v for k, v in query_params.items() 
                           if not any(re.match(pattern, k) for pattern in tracking_patterns)}
        
        # Sort parameters and rebuild query string
        sorted_query = urlencode(sorted(filtered_params.items()), doseq=True)
        
        # Rebuild the URL
        canonical = urlunparse((
            parsed.scheme.lower(),  # Normalize scheme to lowercase
            parsed.netloc.lower(),  # Normalize domain to lowercase
            path,
            parsed.params,
            sorted_query,
            ''  # Remove fragments
        ))
        
        return canonical 