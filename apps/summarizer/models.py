from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class SummarizerUsage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='summarizer_usage')
    query = models.TextField()
    compressed_content = models.TextField()
    response = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    duration = models.DurationField()
    content_token_size = models.IntegerField()
    content_character_count = models.IntegerField()
    total_input_tokens = models.IntegerField()
    total_output_tokens = models.IntegerField()
    model_used = models.CharField(max_length=100) 