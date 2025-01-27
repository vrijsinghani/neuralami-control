from django.db import models

# Create your models here.


class FileInfo(models.Model):
    path = models.CharField(max_length=255, unique=True)
    info = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.path