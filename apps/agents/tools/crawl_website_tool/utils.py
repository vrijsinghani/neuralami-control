import os
import re
from typing import List
from django.conf import settings
from apps.crawl_website.models import CrawlResult
from django.contrib.auth.models import User
from datetime import datetime

def sanitize_url(url: str) -> str:
    """Sanitize the URL to create a valid folder name."""
    url = re.sub(r'^https?://(www\.)?', '', url)
    return re.sub(r'[^a-zA-Z0-9]', '_', url)

def save_crawl_result(user_id: int, website_url: str, content: str, links_visited: List[str], total_links: int, links_to_visit: List[str]) -> str:
    """Save the crawl result to a file in the user's directory."""
    sanitized_url = sanitize_url(website_url)
    
    # Original path structure: MEDIA_ROOT/user_id/Crawled Websites/
    user_dir = os.path.join(settings.MEDIA_ROOT, str(user_id), 'Crawled Websites')
    result_dir = os.path.join(user_dir, sanitized_url)
    os.makedirs(result_dir, exist_ok=True)

    # Original file naming
    file_path = os.path.join(result_dir, f'{sanitized_url}--content.txt')
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(f"Website URL: {website_url}\n\n")
        f.write(f"Crawl Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"Links Visited ({len(links_visited)}):\n")
        f.write('\n'.join(links_visited))
        f.write(f"\n\nTotal Links: {total_links}\n\n")
        f.write("Content:\n")
        f.write(content)

    return file_path

def create_crawl_result(user: User, website_url: str, result: dict, save_file: bool = False) -> CrawlResult:
    """Create a CrawlResult record with optional file saving."""
    file_path = None
    if save_file:
        file_path = save_crawl_result(
            user.id,
            website_url,
            result["content"],
            result["links_visited"],
            result["total_links"],
            result["links_to_visit"]
        )

    crawl_result = CrawlResult.objects.create(
        user=user,
        website_url=website_url,
        content=result["content"],
        links_visited=result["links_visited"],
        total_links=result["total_links"],
        links_to_visit=result["links_to_visit"],
        result_file_path=file_path
    )
    
    return crawl_result 