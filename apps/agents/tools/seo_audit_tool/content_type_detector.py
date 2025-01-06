"""Content type detection for SEO audit tool."""
from typing import Dict, Any
from urllib.parse import urlparse

def determine_content_type(page_data: Dict[str, Any]) -> str:
    """
    Determine the content type of a page based on various signals.
    
    Args:
        page_data: Dictionary containing page information including URL, schema, meta tags, etc.
        
    Returns:
        str: Detected content type (e.g., "business_homepage", "blog", "article", etc.)
    """
    url = page_data.get("url", "")
    parsed_url = urlparse(url)
    path = parsed_url.path.lower()
    
    # Check if it's homepage
    if path in ['', '/']:
        return "business_homepage"
    
    # Check URL patterns
    url_indicators = {
        "blog": ['/blog/', '/posts/', '/articles/'],
        "news": ['/news/', '/press/', '/updates/'],
        "article": ['/article/', '/story/'],
        "product": ['/product/', '/item/', '/goods/'],
        "category": ['/category/', '/collection/', '/catalog/'],
        "contact": ['/contact/', '/reach-us/', '/location/'],
        "about": ['/about/', '/about-us/', '/company/']
    }
    
    # Check URL patterns
    for content_type, patterns in url_indicators.items():
        if any(pattern in path for pattern in patterns):
            return content_type
            
    # Check page structure and content
    html_structure = {
        "has_blog_schema": bool(page_data.get("schema_type") == "BlogPosting"),
        "has_article_schema": bool(page_data.get("schema_type") == "Article"),
        "has_news_schema": bool(page_data.get("schema_type") == "NewsArticle"),
        "has_product_schema": bool(page_data.get("schema_type") == "Product"),
    }
    
    # Check for schema.org markup
    if html_structure["has_blog_schema"]:
        return "blog"
    elif html_structure["has_news_schema"]:
        return "news"
    elif html_structure["has_article_schema"]:
        return "article"
    elif html_structure["has_product_schema"]:
        return "product"
    
    # Check meta tags
    meta_type = page_data.get("meta_type", "").lower()
    if meta_type:
        if "blog" in meta_type:
            return "blog"
        elif "news" in meta_type:
            return "news"
        elif "article" in meta_type:
            return "article"
        elif "product" in meta_type:
            return "product"
    
    # Default to generic content page if no specific type is detected
    return "content" 