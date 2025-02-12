from django.db import models
from django.conf import settings

# Create your models here.

class APIEndpoint(models.Model):
    name = models.CharField(max_length=100, help_text="Name/description of the endpoint")
    url = models.URLField(help_text="Full URL of the endpoint")
    method = models.CharField(
        max_length=10,
        choices=[
            ('GET', 'GET'),
            ('POST', 'POST'),
            ('PUT', 'PUT'),
            ('DELETE', 'DELETE'),
            ('PATCH', 'PATCH')
        ],
        default='GET'
    )
    auth_token = models.CharField(
        max_length=500, 
        blank=True, 
        help_text="Bearer token for authentication"
    )
    default_body = models.TextField(
        blank=True, 
        help_text="Default JSON body for the request"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='api_endpoints'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = "API Endpoint"
        verbose_name_plural = "API Endpoints"

    def __str__(self):
        return f"{self.name} ({self.method} {self.url})"
