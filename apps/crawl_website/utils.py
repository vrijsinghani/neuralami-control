import re
from urllib.parse import urlparse

def sanitize_url_for_filename(url):
    """Convert URL to a safe filename component."""
    # Parse the URL to extract domain
    parsed = urlparse(url)
    domain = parsed.netloc
    
    # Remove www prefix if present
    if domain.startswith('www.'):
        domain = domain[4:]
        
    # Remove non-alphanumeric characters and replace with underscores
    domain = re.sub(r'[^a-zA-Z0-9]', '_', domain)
    
    # Limit length to prevent very long filenames
    if len(domain) > 50:
        domain = domain[:50]
        
    return domain 