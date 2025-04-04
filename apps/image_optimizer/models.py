from django.db import models
from django.conf import settings
from core.storage import SecureFileStorage
from apps.organizations.models.mixins import OrganizationModelMixin

# Create storage for original and optimized images
original_images_storage = SecureFileStorage(
    private=True,
    collection='image_optimizer/original_images'
)

optimized_images_storage = SecureFileStorage(
    private=True,
    collection='image_optimizer/optimized_images'
)

def user_original_path(instance, filename):
    # Return only the filename since the collection is handled by SecureFileStorage
    return filename

def user_optimized_path(instance, filename):
    # Return only the filename since the collection is handled by SecureFileStorage
    return filename

class OptimizationJob(OrganizationModelMixin, models.Model):
    """
    Represents a batch job for optimizing multiple images.
    Uses OrganizationModelMixin with a nullable organization field for migration purposes.
    """
    # Override the organization field to make it nullable
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.CASCADE,
        related_name="%(class)ss",
        null=True,
        blank=True
    )
    
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    settings_used = models.JSONField(help_text='Optimization settings used for all images')
    total_files = models.IntegerField(default=0)
    processed_files = models.IntegerField(default=0)
    total_original_size = models.BigIntegerField(default=0, help_text='Total size in bytes')
    total_optimized_size = models.BigIntegerField(default=0, help_text='Total size in bytes')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Job {self.id} - {self.status} ({self.processed_files}/{self.total_files})"

    @property
    def progress_percentage(self):
        if self.total_files == 0:
            return 0
        return (self.processed_files / self.total_files) * 100

    @property
    def total_reduction_percentage(self):
        if self.total_original_size == 0:
            return 0
        return ((self.total_original_size - self.total_optimized_size) / self.total_original_size) * 100

class OptimizedImage(OrganizationModelMixin, models.Model):
    """
    Represents an individual image that has been optimized.
    Uses OrganizationModelMixin with a nullable organization field for migration purposes.
    """
    # Override the organization field to make it nullable
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.CASCADE,
        related_name="%(class)ss",
        null=True,
        blank=True
    )
    
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    job = models.ForeignKey(OptimizationJob, on_delete=models.CASCADE, related_name='images', null=True, blank=True)
    original_file = models.FileField(upload_to=user_original_path, storage=original_images_storage)
    optimized_file = models.FileField(upload_to=user_optimized_path, storage=optimized_images_storage)
    original_size = models.IntegerField(help_text='Size in bytes')
    optimized_size = models.IntegerField(help_text='Size in bytes')
    compression_ratio = models.FloatField(help_text='Compression ratio in percentage')
    settings_used = models.JSONField(help_text='Optimization settings used')
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Optimized Image'
        verbose_name_plural = 'Optimized Images'

    def __str__(self):
        return f"{self.original_file.name} - {self.compression_ratio}% compression"

    @property
    def size_reduction(self):
        """Returns size reduction in percentage"""
        return ((self.original_size - self.optimized_size) / self.original_size) * 100
