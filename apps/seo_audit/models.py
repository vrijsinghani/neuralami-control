from django.db import models
from django.utils import timezone
from apps.seo_manager.models import Client
from apps.organizations.models.mixins import OrganizationModelMixin

class SEOAuditResult(OrganizationModelMixin, models.Model):
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
        # Meta Issues
        ('title', 'Title Tag Issues'),
        ('meta_description', 'Meta Description Issues'),
        ('h1', 'H1 Tag Issues'),
        ('404', '404 Page Issues'),

        # Link Issues
        ('broken_link', 'Broken Link'),

        # Image Issues
        ('missing_alt', 'Missing Alt Text'),
        ('short_alt', 'Short Alt Text'),
        ('missing_dimensions', 'Missing Image Dimensions'),
        ('generic_filename', 'Generic Image Filename'),
        ('large_size', 'Large Image Size'),
        ('no_lazy_loading', 'No Lazy Loading'),
        ('no_srcset', 'Missing Srcset'),

        # Content Issues
        ('thin_content', 'Thin Content'),
        ('duplicate_content', 'Duplicate Content'),

        # Canonical Issues
        ('canonical_missing', 'Missing Canonical'),
        ('canonical_invalid_format', 'Invalid Canonical Format'),
        ('canonical_different', 'Different Canonical URL'),
        ('canonical_relative', 'Relative Canonical URL'),
        ('canonical_multiple', 'Multiple Canonical Tags'),
        ('canonical_on_pagination', 'Canonical on Pagination'),
        ('canonical_chain', 'Canonical Chain'),

        # Social Media Issues
        ('og_title_missing', 'Missing OG Title'),
        ('og_description_missing', 'Missing OG Description'),
        ('og_image_missing', 'Missing OG Image'),
        ('og_image_invalid', 'Invalid OG Image'),
        ('twitter_card_missing', 'Missing Twitter Card'),
        ('twitter_card_invalid', 'Invalid Twitter Card'),
        ('twitter_title_missing', 'Missing Twitter Title'),
        ('twitter_description_missing', 'Missing Twitter Description'),
        ('twitter_image_missing', 'Missing Twitter Image'),
        ('twitter_image_invalid', 'Invalid Twitter Image'),

        # Technical Issues
        ('sitemap_http_error', 'Sitemap HTTP Error'),
        ('missing_url', 'Missing URL in Sitemap'),
        ('invalid_url', 'Invalid URL Format'),
        ('invalid_lastmod', 'Invalid Lastmod Date'),
        ('invalid_changefreq', 'Invalid Change Frequency'),
        ('invalid_priority', 'Invalid Priority'),
        ('invalid_sitemap', 'Invalid Sitemap Format'),
        ('sitemap_error', 'Sitemap Error'),
        ('ssl_error', 'SSL Certificate Error'),

        # Other
        ('other', 'Other Issue'),

        # Core Web Vitals & Performance
        ('lcp_poor', 'Poor Largest Contentful Paint'),
        ('cls_poor', 'Poor Cumulative Layout Shift'),
        ('inp_poor', 'Poor Interaction to Next Paint'),
        ('fid_poor', 'Poor First Input Delay'),

        # HTML Structure
        ('semantic_structure', 'Invalid Semantic HTML Structure'),
        ('viewport_missing', 'Missing Viewport Meta Tag'),
        ('viewport_invalid', 'Invalid Viewport Configuration'),

        # Duplicate/Redirect Issues
        ('duplicate_titles', 'Duplicate Title Tags'),
        ('redirect_chain', 'Redirect Chain Detected'),
        ('redirect_loop', 'Redirect Loop Detected'),

        # Image Optimization
        ('modern_image_format', 'Not Using Modern Image Format'),
        ('responsive_images', 'Missing Responsive Image Setup'),

        # Indexing & Robots
        ('robots_misconfiguration', 'Robots.txt Misconfiguration'),
        ('noindex_detected', 'Noindex Tag Detected'),
        ('indexing_blocked', 'Indexing Blocked by X-Robots-Tag'),

        # E-E-A-T Signals
        ('author_missing', 'Missing Author Information'),
        ('expertise_signals', 'Missing Expertise Signals'),
        ('factual_accuracy', 'Potential Factual Accuracy Issues'),

        # Structured Data
        ('structured_data_missing', 'Missing Structured Data'),
        ('structured_data_invalid', 'Invalid Structured Data'),

        # Language
        ('language_missing', 'Missing Language Declaration'),
        ('language_mismatch', 'Language Mismatch'),

        # Performance & Core Web Vitals
        ('performance_poor', 'Poor Performance Score'),
        ('performance_render-blocking-resources', 'Render-Blocking Resources'),
        ('performance_unoptimized-images', 'Unoptimized Images'),
        ('performance_unused-css', 'Unused CSS'),
        ('performance_unused-javascript', 'Unused JavaScript'),
        ('performance_server-response-time', 'Slow Server Response'),
        ('pagespeed_error', 'PageSpeed Analysis Error'),
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

class SEORemediationPlan(models.Model):
    audit = models.ForeignKey(SEOAuditResult, on_delete=models.CASCADE, related_name='remediation_plans')
    url = models.URLField()
    created_at = models.DateTimeField(auto_now_add=True)
    llm_provider = models.CharField(max_length=50)
    llm_model = models.CharField(max_length=100)
    plan_content = models.JSONField(help_text="Structured remediation plan content")

    class Meta:
        ordering = ['-created_at']