from django.db import models
from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from urllib.parse import urlparse
import re
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class CrawlResult(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    website_url = models.URLField()
    links_visited = models.JSONField(default=dict)
    total_links = models.IntegerField(default=0)
    file_path = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def create_with_content(cls, user, website_url, content, links_visited=None, total_links=0):
        """Create a CrawlResult with content saved to storage."""
        try:
            # Create timestamp-based directory structure
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            domain = re.sub(r'[^\w\-]', '_', urlparse(website_url).netloc)
            relative_path = os.path.join(
                str(user.id),
                'crawled_websites',
                f"{domain}_{timestamp}",
                'content.txt'
            )

            logger.debug(f"About to save content file at: {relative_path}")
            
            # Convert content to bytes with explicit encoding
            if isinstance(content, list):
                formatted_content = '\n'.join(content)
            else:
                formatted_content = str(content)
            
            content_bytes = formatted_content.encode('utf-8')
            logger.debug(f"Content length: {len(content_bytes)}")

            # Save content using ContentFile with bytes
            default_storage.save(relative_path, ContentFile(content_bytes))

            # Create CrawlResult object
            crawl_result = cls.objects.create(
                user=user,
                website_url=website_url,
                file_path=relative_path,
                links_visited=links_visited or {},
                total_links=total_links
            )

            return crawl_result

        except Exception as e:
            logger.error(f"Error creating CrawlResult: {str(e)}", exc_info=True)
            raise

    def get_content(self):
        """
        Read and return the file content from cloud storage.
        
        Returns:
            str: The file content or empty string if file not found
        """
        try:
            if self.file_path:
                with default_storage.open(self.file_path, 'r') as f:
                    return f.read()
            return ""
            
        except Exception as e:
            logger.error(f"Error reading content for CrawlResult {self.id}: {str(e)}")
            return ""

    def get_file_url(self):
        """
        Get the URL for the saved file.
        
        Returns:
            str: The URL to access the file or None if not found
        """
        try:
            if self.file_path:
                return default_storage.url(self.file_path)
            return None
            
        except Exception as e:
            logger.error(f"Error getting URL for CrawlResult {self.id}: {str(e)}")
            return None

    def delete(self, *args, **kwargs):
        """
        Override delete to remove the file from storage when deleting the model.
        """
        try:
            # Delete the file from storage if it exists
            if self.file_path and default_storage.exists(self.file_path):
                default_storage.delete(self.file_path)
                logger.info(f"Deleted file from storage: {self.file_path}")
                
        except Exception as e:
            logger.error(f"Error deleting file for CrawlResult {self.id}: {str(e)}")
            
        # Call the parent class delete method
        super().delete(*args, **kwargs)

    def __str__(self):
        return f"Crawl of {self.website_url} by {self.user.username}"

    class Meta:
        ordering = ['-created_at']
