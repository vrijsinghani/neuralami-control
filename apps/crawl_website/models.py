from django.db import models
from django.contrib.auth.models import User

class CrawlResult(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    website_url = models.URLField()
    content = models.TextField()
    links_visited = models.JSONField()
    total_links = models.IntegerField()
    links_to_visit = models.JSONField()
    result_file_path = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Crawl Result for {self.website_url} by {self.user.username}"

    class Meta:
        ordering = ['-created_at']
