from django.db import models
from django.contrib.auth.models import User
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class CrawlResult(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    website_url = models.URLField()
    links_visited = models.JSONField(default=dict)
    total_links = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def create_with_content(cls, user, website_url, content, links_visited=None, total_links=0):
        """Create a CrawlResult with metadata only."""
        try:
            # Create CrawlResult object with metadata only
            crawl_result = cls.objects.create(
                user=user,
                website_url=website_url,
                links_visited=links_visited or {},
                total_links=total_links
            )

            return crawl_result

        except Exception as e:
            logger.error(f"Error creating CrawlResult: {str(e)}", exc_info=True)
            raise

    def __str__(self):
        return f"Crawl of {self.website_url} by {self.user.username}"

    class Meta:
        ordering = ['-created_at']
