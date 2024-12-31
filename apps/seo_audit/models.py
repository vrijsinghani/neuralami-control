from django.db import models
from django.utils import timezone
from apps.seo_manager.models import Client

class SEOAuditResult(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled')
    ]

    client = models.ForeignKey(Client, null=True, blank=True, on_delete=models.CASCADE, related_name='seo_audits')
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    website = models.URLField()
    max_pages = models.IntegerField(default=100)
    check_external_links = models.BooleanField(default=False)
    crawl_delay = models.FloatField(default=1.0)
    results = models.JSONField(null=True, blank=True)
    error = models.TextField(null=True, blank=True)
    progress = models.JSONField(default=dict, help_text="Stores progress information during the audit")
    task_id = models.CharField(max_length=100, null=True, blank=True, help_text="Celery task ID for tracking")

    class Meta:
        ordering = ['-start_time']
        get_latest_by = 'start_time'

    def __str__(self):
        client_name = self.client.name if self.client else 'No Client'
        return f"SEO Audit - {client_name} - {self.start_time.strftime('%Y-%m-%d %H:%M')}"

    def mark_completed(self, results):
        self.status = 'completed'
        self.end_time = timezone.now()
        self.results = results
        self.save()

    def mark_failed(self, error):
        self.status = 'failed'
        self.end_time = timezone.now()
        self.error = str(error)
        self.save()

    def update_progress(self, progress_data):
        self.progress = progress_data
        self.save(update_fields=['progress'])

    @property
    def duration(self):
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return None

class SEOAuditIssue(models.Model):
    SEVERITY_CHOICES = [
        ('critical', 'Critical'),
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
        ('info', 'Info')
    ]

    ISSUE_TYPES = [
        ('broken_link', 'Broken Link'),
        ('meta_missing', 'Missing Meta Tags'),
        ('duplicate_content', 'Duplicate Content'),
        ('ssl_issue', 'SSL Issue'),
        ('mobile_unfriendly', 'Mobile Unfriendly'),
        ('slow_loading', 'Slow Loading'),
        ('missing_alt', 'Missing Alt Text'),
        ('other', 'Other')
    ]

    audit = models.ForeignKey(SEOAuditResult, on_delete=models.CASCADE, related_name='issues')
    issue_type = models.CharField(max_length=50, choices=ISSUE_TYPES)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    url = models.URLField()
    details = models.JSONField()
    discovered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-severity', '-discovered_at']

    def __str__(self):
        return f"{self.get_issue_type_display()} - {self.get_severity_display()} - {self.url}" 