import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

def analyze_website_meta_tags(website_url):
    try:
        # Get sitemap URL
        sitemap_url = urljoin(website_url, 'sitemap.xml')
        
        # Fetch sitemap
        response = requests.get(sitemap_url)
        root = ET.fromstring(response.content)
        
        urls = []
        for url in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc'):
            urls.append(url.text)
        
        total_tags = 0
        issues = []
        meta_data = []
        
        # Analyze each URL
        for url in urls[:10]:  # Limit to first 10 URLs for performance
            response = requests.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Collect meta tags
            meta_tags = soup.find_all('meta')
            total_tags += len(meta_tags)
            
            page_meta = {
                'url': url,
                'title': soup.title.string if soup.title else None,
                'meta_tags': []
            }
            
            for tag in meta_tags:
                tag_data = {
                    'name': tag.get('name', tag.get('property', '')),
                    'content': tag.get('content', '')
                }
                page_meta['meta_tags'].append(tag_data)
                
                # Check for common issues
                if not tag.get('content'):
                    issues.append(f"Empty content in meta tag {tag_data['name']} on {url}")
            
            meta_data.append(page_meta)
        
        return {
            'total_tags': total_tags,
            'issues_count': len(issues),
            'issues': issues,
            'pages': meta_data
        }
        
    except Exception as e:
        raise Exception(f"Error analyzing meta tags: {str(e)}") 