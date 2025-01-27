from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.contrib.auth.models import User
from datetime import datetime
import re
import os
import logging
from typing import List
from apps.crawl_website.models import CrawlResult

logger = logging.getLogger(__name__)

def sanitize_url(url: str) -> str:
    """Sanitize the URL to create a valid folder name."""
    url = re.sub(r'^https?://(www\.)?', '', url)
    return re.sub(r'[^a-zA-Z0-9]', '_', url)

def get_crawl_result_url(relative_path: str) -> str:
    """Get the URL for accessing a crawl result file."""
    try:
        if relative_path:
            # For S3/B2, this will return a proper S3/B2 URL
            return default_storage.url(relative_path)
        return None
    except Exception as e:
        logger.error(f"Error getting URL for crawl result: {str(e)}")
        return None

def ensure_crawl_directory_exists(user_id: int) -> str:
    """Ensure the crawl directory exists in cloud storage."""
    try:
        # For S3/B2, we don't need to create directory markers
        relative_path = os.path.join(str(user_id), 'crawled_websites')
        logger.debug(f"Using crawl directory path: {relative_path}")
        return relative_path
        
    except Exception as e:
        logger.error(f"Error with crawl directory path: {str(e)}")
        raise

def get_crawl_results(user_id: int) -> List[str]:
    """Get list of crawl results from cloud storage."""
    try:
        directory_path = ensure_crawl_directory_exists(user_id)
        results = []
        
        # Use S3/B2 style listing
        prefix = f"{directory_path}/"
        for obj in default_storage.bucket.objects.filter(Prefix=prefix):
            if obj.key.endswith('.txt'):  # Only include .txt files
                results.append(obj.key)
                    
        # Sort by last modified time
        results.sort(key=lambda x: default_storage.get_modified_time(x), reverse=True)
        return results
        
    except Exception as e:
        logger.error(f"Error getting crawl results: {str(e)}")
        return [] 