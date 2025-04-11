import os
from django.core.files.storage import Storage, default_storage
from django.utils.deconstruct import deconstructible
from django.conf import settings
from django.core.files.base import ContentFile
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
    # Storage utility methods
    def directory_exists(self, path):
        """
        Check if a directory exists.
        
        Args:
            path: The directory path to check
            
        Returns:
            Boolean indicating if directory exists
        """
        try:
            # Normalize path
            path = self._get_path(path)
            
            # Try to list the directory
            try:
                # Use the storage backend's listdir method
                dirs, files = self.storage.listdir(path)
                return True
            except Exception as e:
                # If the directory doesn't exist, listdir will raise an exception
                if "NoSuchKey" in str(e) or "does not exist" in str(e) or "Not Found" in str(e):
                    return False
                # If it's a different error, log it and try filesystem approach
                logger.warning(f"Error checking if directory exists using storage backend: {str(e)}")
                
            # Fallback to filesystem approach if storage backend approach fails
            try:
                # Get the local filesystem path
                fs_path = self.storage.path(path)
                # Check if it exists and is a directory
                return os.path.isdir(fs_path)
            except Exception as e:
                # If the storage backend doesn't support path method, this will fail
                logger.error(f"Error checking if directory exists using filesystem: {str(e)}")
                return False
                
        except Exception as e:
            logger.error(f"Error checking if directory exists: {str(e)}")
            return False
    
    def create_directory(self, path):
        """
        Create a directory.
        
        Args:
            path: The directory path to create
            
        Returns:
            The created directory path
        """
        try:
            # Normalize path
            path = self._get_path(path)
            
            # Try to create the directory using the storage backend
            try:
                # Some storage backends have a create_directory method
                if hasattr(self.storage, 'create_directory'):
                    self.storage.create_directory(path)
                    return path
                
                # For S3/MinIO, create an empty file with a trailing slash
                if hasattr(self.storage, 'save'):
                    # Create an empty file with a trailing slash to represent a directory
                    self.storage.save(f"{path.rstrip('/')}/.keep", ContentFile(b''))
                    return path
            except Exception as e:
                # Log the error and try filesystem approach
                logger.warning(f"Error creating directory using storage backend: {str(e)}")
            
            # Fallback to filesystem approach if storage backend approach fails
            try:
                # Get the local filesystem path
                fs_path = self.storage.path(path)
                # Create the directory
                os.makedirs(fs_path, exist_ok=True)
                return path
            except Exception as e:
                # If the storage backend doesn't support path method, this will fail
                logger.error(f"Error creating directory using filesystem: {str(e)}")
                raise
                
        except Exception as e:
            logger.error(f"Error creating directory: {str(e)}")
            raise
    
    def list_directory(self, path):
        """
        List contents of a directory.
        
        Args:
            path: The directory path to list
            
        Returns:
            A tuple of (directories, files)
        """
        try:
            # Normalize path
            path = self._get_path(path)
            
            # Use the storage backend's listdir method
            return self.storage.listdir(path)
        except Exception as e:
            logger.error(f"Error listing directory: {str(e)}")
            raise
    
    def delete_directory(self, path):
        """
        Delete a directory and all its contents.
        
        Args:
            path: The directory path to delete
            
        Returns:
            Number of files deleted
        """
        try:
            # Normalize path
            path = self._get_path(path)
            
            # Check if the directory exists
            if not self.directory_exists(path):
                logger.warning(f"Directory does not exist: {path}")
                return 0
            
            # Get all files in the directory and subdirectories
            files_to_delete = []
            
            # Use a recursive approach to find all files
            def find_files(dir_path):
                try:
                    dirs, files = self.list_directory(dir_path)
                    
                    # Add files in current directory
                    for file_name in files:
                        file_path = os.path.join(dir_path, file_name).replace('\\', '/')
                        files_to_delete.append(file_path)
                    
                    # Recursively process subdirectories
                    for dir_name in dirs:
                        subdir_path = os.path.join(dir_path, dir_name).replace('\\', '/') + '/'
                        find_files(subdir_path)
                except Exception as e:
                    logger.error(f"Error finding files in {dir_path}: {str(e)}")
            
            # Start the recursive search
            find_files(path)
            
            # Delete all files
            deleted_count = 0
            for file_path in files_to_delete:
                try:
                    self.delete(file_path)
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"Error deleting file {file_path}: {str(e)}")
            
            # Try to delete the directory itself (if it's an actual directory object)
            try:
                # Some storage backends might have empty directories as objects
                self.delete(path.rstrip('/'))
            except Exception:
                # Ignore errors when deleting the directory itself
                pass
            
            return deleted_count
        except Exception as e:
            logger.error(f"Error deleting directory: {str(e)}")
            raise
    
    def batch_delete(self, paths):
        """
        Delete multiple files efficiently.
        
        Args:
            paths: List of file paths to delete
            
        Returns:
            Number of files deleted
        """
        deleted_count = 0
        for path in paths:
            try:
                # Normalize path
                path = self._get_path(path)
                
                # Delete the file
                self.delete(path)
                deleted_count += 1
            except Exception as e:
                logger.warning(f"Error deleting file {path}: {str(e)}")
        
        return deleted_count
    
    def get_nested_directory_structure(self, path=''):
        """
        Generate a nested directory structure.
        
        Args:
            path: The root directory path
            
        Returns:
            A list of dictionaries representing the directory structure
        """
        try:
            # Normalize path
            path = self._get_path(path)
            
            # Create the root node
            root = {
                'name': 'Home',
                'path': '',
                'directories': []
            }
            
            # Use a recursive approach to build the directory structure
            def build_structure(dir_path, parent):
                try:
                    dirs, files = self.list_directory(dir_path)
                    
                    # Add subdirectories
                    for dir_name in sorted(dirs):
                        # Skip hidden directories
                        if dir_name.startswith('.'):
                            continue
                        
                        # Create the directory node
                        rel_path = os.path.join(dir_path, dir_name).replace('\\', '/')
                        if path:
                            # Remove the root path prefix
                            rel_path = rel_path[len(path):].lstrip('/')
                        
                        dir_node = {
                            'name': dir_name,
                            'path': rel_path,
                            'directories': []
                        }
                        
                        # Add the directory node to the parent
                        parent['directories'].append(dir_node)
                        
                        # Recursively process subdirectories
                        subdir_path = os.path.join(dir_path, dir_name).replace('\\', '/') + '/'
                        build_structure(subdir_path, dir_node)
                except Exception as e:
                    logger.error(f"Error building directory structure for {dir_path}: {str(e)}")
            
            # Start the recursive build
            build_structure(path, root)
            
            return [root]
        except Exception as e:
            logger.error(f"Error generating directory structure: {str(e)}")
            # Return a basic structure as fallback
            return [{
                'name': 'Home',
                'path': '',
                'directories': []
            }]
