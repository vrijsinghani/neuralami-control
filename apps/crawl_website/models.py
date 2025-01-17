from django.db import models
from django.contrib.auth.models import User
import os
from django.conf import settings
from urllib.parse import urlparse
import re

class CrawlResult(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    website_url = models.URLField()
    links_visited = models.JSONField(default=dict)
    total_links = models.IntegerField(default=0)
    file_path = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def create_with_content(cls, user, website_url, content, links_visited, total_links):
        """Create a CrawlResult and save content to file."""
        # Sanitize URL for filename
        parsed_url = urlparse(website_url)
        sanitized_domain = re.sub(r'[^\w\-]', '_', parsed_url.netloc)
        
        # Create directory structure
        relative_path = os.path.join(
            str(user.id),
            'Crawled Websites'
        )
        full_dir_path = os.path.join(settings.MEDIA_ROOT, relative_path)
        os.makedirs(full_dir_path, exist_ok=True)

        # Create file
        filename = f"{sanitized_domain}.txt"
        full_file_path = os.path.join(full_dir_path, filename)
        
        # Save content to file
        with open(full_file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Create and return the model instance
        return cls.objects.create(
            user=user,
            website_url=website_url,
            links_visited=links_visited,
            total_links=total_links,
            file_path=os.path.join(relative_path, filename)
        )

    def get_content(self):
        """Read and return the file content."""
        if self.file_path:
            full_path = os.path.join(settings.MEDIA_ROOT, self.file_path)
            if os.path.exists(full_path):
                with open(full_path, 'r', encoding='utf-8') as f:
                    return f.read()
        return ""

    def get_file_url(self):
        """Get the URL for the saved file."""
        return os.path.join(settings.MEDIA_URL, self.file_path)

    def __str__(self):
        return f"Crawl of {self.website_url} by {self.user.username}"

    class Meta:
        ordering = ['-created_at']
