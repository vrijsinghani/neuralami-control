from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

def default_list():
    return []

class Research(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    query = models.TextField()
    breadth = models.IntegerField(default=4)
    depth = models.IntegerField(default=2)
    guidance = models.TextField(null=True, blank=True, help_text="Optional guidance for content processing")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    report = models.TextField(null=True, blank=True)
    error = models.TextField(null=True, blank=True)
    
    # Store intermediate results using callable defaults
    visited_urls = models.JSONField(default=default_list)
    learnings = models.JSONField(default=default_list)
    reasoning_steps = models.JSONField(default=default_list)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Research'

    def __str__(self):
        return f"Research: {self.query[:50]}..." 