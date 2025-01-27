from django.core.files.storage import Storage, default_storage
from django.conf import settings
from django.utils.deconstruct import deconstructible
from b2sdk.v2 import B2Api, InMemoryAccountInfo
from django.core.files.utils import validate_file_name
import logging
import os
from django.core.files.base import ContentFile
from io import BytesIO

logger = logging.getLogger('core.storage')

class B2ObjectsCollection:
    """Mimics S3's objects collection interface"""
    def __init__(self, bucket):
        self.bucket = bucket

    def filter(self, Prefix=''):
        """Mimics S3's filter method"""
        try:
            for file_version, _ in self.bucket.ls(folder_to_list=Prefix):
                yield B2Object(file_version)
        except Exception as e:
            logger.error(f"Error listing objects with prefix {Prefix}: {str(e)}")
            raise

class B2Object:
    """Mimics S3's Object interface"""
    def __init__(self, file_version):
        self.file_version = file_version
        self.key = file_version.file_name
        self.size = file_version.size

    def delete(self):
        """Mimics S3's delete method"""
        try:
            self.file_version.bucket.delete_file_version(
                self.file_version.id_,
                self.file_version.file_name
            )
        except Exception as e:
            logger.error(f"Error deleting object {self.key}: {str(e)}")
            raise

@deconstructible
class B2Storage(Storage):
    """
    Backblaze B2 Storage backend for Django with S3-compatible interface
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            logger.info("Creating new B2Storage instance")
            cls._instance = super().__new__(cls)
            # Initialize here to ensure it happens only once
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not getattr(self, '_initialized', False):
            logger.info("Initializing B2Storage backend")
            super().__init__()
            self._b2_api = None
            self._bucket = None
            self._objects = None
            self._initialize_b2()
            self._initialized = True
            logger.info("B2Storage backend initialization complete")
        else:
            logger.debug("Reusing existing B2Storage instance")

    def _initialize_b2(self):
        """Initialize B2 connection and bucket"""
        try:
            logger.debug("Starting B2 API initialization")
            logger.debug(f"Using credentials - Key ID: {settings.B2_APPLICATION_KEY_ID[:4]}..., Bucket: {settings.B2_BUCKET_NAME}")
            
            # Create API client
            self._b2_api = B2Api(InMemoryAccountInfo())
            
            # Authorize
            logger.debug("Authorizing with B2...")
            self._b2_api.authorize_account(
                "production",
                settings.B2_APPLICATION_KEY_ID,
                settings.B2_APPLICATION_KEY
            )
            logger.debug("B2 authorization successful")
            
            # Get bucket and verify access
            self._bucket = self._b2_api.get_bucket_by_name(settings.B2_BUCKET_NAME)
            logger.debug(f"Got bucket: {self._bucket.name}")
            
            # Test bucket access
            logger.debug("Testing bucket access...")
            test_file = "test_access.txt"
            test_data = b"Testing bucket access"
            try:
                # Try to upload
                self._bucket.upload_bytes(
                    data_bytes=test_data,
                    file_name=test_file
                )
                logger.debug("Test upload successful")
                
                # Try to download
                download = self._bucket.download_file_by_name(test_file)
                logger.debug("Test download successful")
                
                # Clean up
                file_version = self._bucket.get_file_info_by_name(test_file)
                self._bucket.delete_file_version(file_version.id_, test_file)
                logger.debug("Test cleanup successful")
                
            except Exception as e:
                logger.error(f"Bucket access test failed: {str(e)}", exc_info=True)
                raise
                
            self._objects = B2ObjectsCollection(self._bucket)
            logger.debug("B2 Storage initialization complete")
            
        except Exception as e:
            logger.error(f"B2 Storage initialization failed: {str(e)}", exc_info=True)
            raise RuntimeError(f"Failed to initialize B2 storage backend: {str(e)}") from e

    @property
    def bucket(self):
        """Accessor for B2 bucket with S3-compatible interface"""
        if not self._bucket:
            logger.warning("B2 bucket not initialized, reinitializing...")
            self._initialize_b2()
        return self

    @property
    def objects(self):
        """S3-compatible objects collection"""
        if not self._objects:
            self._initialize_b2()
        return self._objects

    def _save(self, name, content):
        """Save a file to B2"""
        try:
            logger.info(f"B2Storage._save called with name: {name}")
            if not self._bucket:
                logger.error("No bucket available!")
                self._initialize_b2()
                
            # Reset file pointer
            content.seek(0)
            
            # Read the content
            data = content.read()
            logger.info(f"Content type: {type(data)}, length: {len(data) if data else 0}")
            
            # If it's a string, encode it
            if isinstance(data, str):
                data = data.encode('utf-8')
                logger.info("Encoded string content to bytes")
            
            logger.info(f"Uploading to B2 with name: {name}")
            try:
                # Get upload URL and auth token
                upload_url = self._bucket.get_upload_url()
                logger.info(f"Got upload URL: {upload_url.upload_url}")
                
                # Upload the file
                file_info = self._bucket.upload_bytes(
                    data_bytes=data,
                    file_name=name,
                )
                
                # Verify the upload
                try:
                    verification = self._bucket.get_file_info_by_name(name)
                    logger.info(f"Verified file upload - ID: {verification.id_}, Size: {verification.size}")
                    if verification.size != len(data):
                        raise Exception(f"Upload size mismatch - Expected: {len(data)}, Got: {verification.size}")
                except Exception as e:
                    logger.error(f"Failed to verify upload: {str(e)}", exc_info=True)
                    raise
                    
                logger.info(f"B2 upload_bytes completed and verified successfully")
                return name
                
            except Exception as e:
                logger.error(f"B2 upload_bytes failed: {str(e)}", exc_info=True)
                # Try to get more details about the error
                if hasattr(e, 'response'):
                    logger.error(f"B2 API Response: {e.response.text if hasattr(e.response, 'text') else str(e.response)}")
                raise
            
        except Exception as e:
            logger.error(f"Failed to save file to B2: {str(e)}", exc_info=True)
            raise

    def _open(self, name, mode='rb'):
        """Retrieve a file from B2"""
        try:
            output = BytesIO()
            self._bucket.download_file_by_name(name).save(output)
            output.seek(0)
            content = output.getvalue()
            
            # If in text mode and content is bytes, decode it
            if 'b' not in mode and isinstance(content, bytes):
                content = content.decode('utf-8')
            
            return ContentFile(content)
        except Exception as e:
            logger.error(f"Failed to retrieve file from B2: {str(e)}", exc_info=True)
            raise

    def exists(self, name):
        """Check if a file exists in B2"""
        try:
            # Force a fresh check from B2
            self._bucket.get_file_info_by_name(name, force_fresh=True)
            return True
        except:
            return False

    def delete(self, name):
        """Delete a file from B2"""
        try:
            file_version = self._bucket.get_file_info_by_name(name)
            self._bucket.delete_file_version(file_version.id_, name)
        except Exception as e:
            logger.error(f"Failed to delete file from B2: {str(e)}")
            raise

    def url(self, name):
        """Get the URL for a file"""
        try:
            return self._bucket.get_download_url(name)
        except Exception as e:
            logger.error(f"Failed to get URL for file: {str(e)}")
            raise

    def size(self, name):
        """Get the size of a file"""
        try:
            file_info = self._bucket.get_file_info_by_name(name)
            return file_info.size
        except Exception as e:
            logger.error(f"Failed to get file size: {str(e)}")
            raise

    def __str__(self):
        return f"B2Storage(bucket={settings.B2_BUCKET_NAME})"

    def __repr__(self):
        return self.__str__()

    def get_modified_time(self, name):
        """
        Get the last modified time of a file
        """
        try:
            file_info = self._bucket.get_file_info_by_name(name)
            return file_info.upload_timestamp
        except Exception as e:
            logger.error(f"Failed to get modified time: {str(e)}")
            raise

    def get_accessed_time(self, name):
        """
        Get the last accessed time of a file
        """
        return self.get_modified_time(name)

    def get_created_time(self, name):
        """
        Get the creation time of a file
        """
        return self.get_modified_time(name)

    def listdir(self, path):
        """
        List the contents of a directory
        """
        try:
            directories = set()
            files = []
            
            for file_version, _ in self._bucket.ls(folder_to_list=path):
                name = file_version.file_name
                relative_name = name[len(path):].lstrip('/')
                
                if not relative_name:
                    continue
                    
                parts = relative_name.split('/', 1)
                
                if len(parts) > 1:
                    # This is a file in a subdirectory
                    directories.add(parts[0])
                else:
                    # This is a file in the current directory
                    files.append(parts[0])
                    
            return list(sorted(directories)), sorted(files)
        except Exception as e:
            logger.error(f"Failed to list directory: {str(e)}")
            raise

    def get_valid_name(self, name):
        """
        Returns a filename suitable for use with the underlying storage system.
        """
        return validate_file_name(name)

    def get_available_name(self, name, max_length=None):
        """
        Returns a filename that's free on the target storage system.
        """
        dir_name, file_name = os.path.split(name)
        file_root, file_ext = os.path.splitext(file_name)
        
        while self.exists(name):
            # If the filename already exists, add an underscore and a random character
            file_root = f"{file_root}_{os.urandom(2).hex()}"
            name = os.path.join(dir_name, f"{file_root}{file_ext}")
            if max_length and len(name) > max_length:
                raise ValueError("Max length exceeded")
        
        return name

def initialize_storage():
    """Initialize the default storage with B2Storage"""
    logger.info("Initializing default storage with B2Storage")
    try:
        if not isinstance(default_storage._wrapped, B2Storage):
            storage = B2Storage()
            default_storage._wrapped = storage
            logger.info("Successfully initialized default storage with B2Storage")
        else:
            logger.info("Default storage is already B2Storage")
    except Exception as e:
        logger.error(f"Failed to initialize default storage: {str(e)}", exc_info=True)
        raise 