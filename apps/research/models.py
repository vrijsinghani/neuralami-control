from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

class Research(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed')
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    query = models.TextField()
    breadth = models.IntegerField(default=4)
    depth = models.IntegerField(default=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    report = models.TextField(null=True, blank=True)
    error = models.TextField(null=True, blank=True)
    
    # Store intermediate results
    visited_urls = models.JSONField(default=list)
    learnings = models.JSONField(default=list)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Research'

    def __str__(self):
        return f"Research: {self.query[:50]}..." 