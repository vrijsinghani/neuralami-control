from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import os

# Create your models here.


class FileTag(models.Model):
    """Model for file tags to categorize files"""
    name = models.CharField(max_length=50, unique=True)
    color = models.CharField(max_length=20, default='primary')  # Bootstrap color class

    def __str__(self):
        return self.name


class FileInfo(models.Model):
    """Enhanced model for storing file metadata"""
    path = models.URLField()
    info = models.CharField(max_length=255, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, related_name='files')
    filename = models.CharField(max_length=255, blank=True)  # Store filename separately for easier querying
    file_type = models.CharField(max_length=50, blank=True)  # Store file type/extension
    file_size = models.PositiveIntegerField(default=0)  # File size in bytes
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    tags = models.ManyToManyField(FileTag, blank=True, related_name='files')
    is_favorite = models.BooleanField(default=False)

    def __str__(self):
        return self.filename or self.path

    def get_file_extension(self):
        """Get the file extension from the path"""
        _, extension = os.path.splitext(self.path)
        return extension.lower()

    def get_file_size_display(self):
        """Return human-readable file size"""
        size = self.file_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024 or unit == 'GB':
                return f"{size:.2f} {unit}"
            size /= 1024