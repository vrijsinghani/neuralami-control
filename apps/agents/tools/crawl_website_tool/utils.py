from core.storage import SecureFileStorage
from django.core.files.base import ContentFile
from django.contrib.auth.models import User
from datetime import datetime
import re
import os
import logging
from typing import List
from apps.crawl_website.models import CrawlResult

logger = logging.getLogger(__name__)

# Instantiate SecureFileStorage mirroring usage in crawl_website/views.py
# Assuming private access, no specific collection as user ID is part of path
crawl_tool_storage = SecureFileStorage(private=True, collection='')

def sanitize_url(url: str) -> str:
    """Sanitize the URL to create a valid folder name."""
    url = re.sub(r'^https?://(www\.)?', '', url)
    return re.sub(r'[^a-zA-Z0-9]', '_', url)

def get_crawl_result_url(relative_path: str) -> str:
    """Get the URL for accessing a crawl result file using SecureFileStorage."""
    try:
        if relative_path:
            # Use SecureFileStorage url method
            return crawl_tool_storage.url(relative_path)
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
    """Get list of crawl results from cloud storage using SecureFileStorage."""
    try:
        directory_path = ensure_crawl_directory_exists(user_id)
        results = []
        
        # Use the underlying storage object for listing capabilities
        underlying_storage = crawl_tool_storage.storage 
        
        # Use S3/B2 style listing via the underlying storage object
        prefix = f"{directory_path}/"
        
        # Check if the underlying storage has a 'bucket' attribute (like S3/MinIO)
        if hasattr(underlying_storage, 'bucket') and hasattr(underlying_storage.bucket, 'objects'):
            for obj in underlying_storage.bucket.objects.filter(Prefix=prefix):
                # Check for .json and .csv files based on updated saving logic
                if obj.key.endswith('.json') or obj.key.endswith('.csv'): 
                    results.append(obj.key)
        else:
            # Fallback to listdir if no bucket/objects interface (e.g., local storage)
            try:
                 _dirs, files = underlying_storage.listdir(prefix)
                 for filename in files:
                      # Check for .json and .csv files
                      if filename.endswith('.json') or filename.endswith('.csv'):
                           results.append(os.path.join(prefix, filename))
            except Exception as list_err:
                 logger.error(f"Could not list directory {prefix} using listdir: {list_err}")
                 # Return empty list or raise error?
                 return []

        # Sort by last modified time using SecureFileStorage's get_modified_time
        # Handle potential errors during sorting
        def get_mtime_safe(key):
            try:
                return crawl_tool_storage.get_modified_time(key)
            except Exception as mtime_err:
                logger.error(f"Could not get modified time for {key}: {mtime_err}")
                # Return a default old datetime to sort problematic files last?
                return datetime.min.replace(tzinfo=datetime.timezone.utc) # Make timezone aware

        results.sort(key=get_mtime_safe, reverse=True)
        return results
        
    except Exception as e:
        logger.error(f"Error getting crawl results: {str(e)}")
        return [] 