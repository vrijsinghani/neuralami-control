from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible
from django.conf import settings
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

# No need for get_storage() function since Django handles this through DEFAULT_FILE_STORAGE setting 