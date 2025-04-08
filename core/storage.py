import os
from django.core.files.storage import Storage, default_storage
from django.utils.deconstruct import deconstructible
from django.conf import settings
from django.urls import reverse
from django.utils.module_loading import import_string
import logging

logger = logging.getLogger('core.storage')

# Only import B2 if it's being used
if settings.STORAGE_BACKEND == 'B2':
    from b2sdk.v2 import B2Api, InMemoryAccountInfo

# Import django-storages backends
if settings.STORAGE_BACKEND in ['S3', 'MINIO']:
    from storages.backends.s3boto3 import S3Boto3Storage
elif settings.STORAGE_BACKEND == 'GCS':
    from storages.backends.gcloud import GoogleCloudStorage
elif settings.STORAGE_BACKEND == 'AZURE':
    from storages.backends.azure_storage import AzureStorage

@deconstructible
class BaseStorage(Storage):
    """Base storage class with common functionality"""
    def get_valid_name(self, name):
        """Returns a filename suitable for use with the storage system."""
        return name.replace('\\', '/')

    def get_available_name(self, name, max_length=None):
        """Returns a filename that's free on the target storage system."""
        dir_name, file_name = os.path.split(name)
        file_root, file_ext = os.path.splitext(file_name)
        
        counter = 0
        while self.exists(name):
            counter += 1
            name = os.path.join(dir_name, f"{file_root}_{counter}{file_ext}")
            if max_length and len(name) > max_length:
                raise ValueError("Max length exceeded")
        
        return name

@deconstructible
class B2Storage(Storage):
    """Backblaze B2 Storage backend"""
    def __init__(self):
        super().__init__()
        self._api = B2Api(InMemoryAccountInfo())
        self._api.authorize_account("production", 
                                  settings.B2_APPLICATION_KEY_ID,
                                  settings.B2_APPLICATION_KEY)
        self._bucket = self._api.get_bucket_by_name(settings.B2_BUCKET_NAME)

    def _save(self, name, content):
        content.seek(0)
        self._bucket.upload_bytes(content.read(), name)
        return name

    def _open(self, name, mode='rb'):
        file_data = self._bucket.download_file_by_name(name)
        return file_data.get_content()

@deconstructible
class SecureFileStorage(Storage):
    """
    A secure file storage implementation that handles private files by routing 
    access through Django views with permission checks.
    
    This class provides a wrapping interface that can use any of the supported 
    storage backends while ensuring secure access to files.
    """
    def __init__(self, private=True, collection='default'):
        """
        Initialize the secure storage.
        
        Args:
            private (bool): Whether files should be served via Django views (True) or 
                          direct from storage (False)
            collection (str): A logical grouping for the files (e.g., 'logos', 'avatars')
        """
        self.private = private
        self.collection = collection
        
        # Get the actual storage backend from Django's default_storage
        self.storage = default_storage
        #logger.debug(f"SecureFileStorage initialized with backend: {self.storage.__class__.__name__}")
        
    def _get_path(self, name):
        """
        Get the normalized path, prefixed with collection if provided.
        """
        if self.collection and self.collection != 'default':
            # Check if the name already starts with the collection prefix to avoid duplication
            if name.startswith(f"{self.collection}/"):
                return name
            return f"{self.collection}/{name}"
        return name
        
    def _save(self, name, content):
        """Save the file using the underlying storage"""
        path = self._get_path(name)
        return self.storage._save(path, content)
        
    def _open(self, name, mode='rb'):
        """Open the file using the underlying storage"""
        path = self._get_path(name)
        return self.storage._open(path, mode)
        
    def delete(self, name):
        """Delete the file using the underlying storage"""
        path = self._get_path(name)
        return self.storage.delete(path)
        
    def exists(self, name):
        """Check if the file exists using the underlying storage"""
        path = self._get_path(name)
        return self.storage.exists(path)
        
    def size(self, name):
        """Get the file size using the underlying storage"""
        path = self._get_path(name)
        return self.storage.size(path)
        
    def url(self, name):
        """
        Return a URL for the file.
        
        For private files, return a URL to the Django view that will serve the file
        with permission checks.
        For public files, return a direct URL to the storage backend.
        """
        path = self._get_path(name)
        
        if self.private:
            # Return URL to Django view for secure file access
            return reverse('serve_protected_file', kwargs={
                'path': path
            })
        else:
            # Return direct URL from storage backend
            return self.storage.url(path)
            
    def path(self, name):
        """
        Return the file's path on the underlying storage if available
        """
        if hasattr(self.storage, 'path'):
            path = self._get_path(name)
            return self.storage.path(path)
        raise NotImplementedError("This storage doesn't support absolute paths")

    def get_accessed_time(self, name):
        """Get the last accessed time using the underlying storage if available"""
        if hasattr(self.storage, 'get_accessed_time'):
            path = self._get_path(name)
            return self.storage.get_accessed_time(path)
        raise NotImplementedError("This storage doesn't support accessed time")
        
    def get_created_time(self, name):
        """Get the creation time using the underlying storage if available"""
        if hasattr(self.storage, 'get_created_time'):
            path = self._get_path(name)
            return self.storage.get_created_time(path)
        raise NotImplementedError("This storage doesn't support created time")
        
    def get_modified_time(self, name):
        """Get the last modified time using the underlying storage if available"""
        if hasattr(self.storage, 'get_modified_time'):
            path = self._get_path(name)
            return self.storage.get_modified_time(path)
        raise NotImplementedError("This storage doesn't support modified time")

# No need for get_storage() function since Django handles this through DEFAULT_FILE_STORAGE setting 