import os
import uuid
import logging
import io
import zipfile
import csv
from urllib.parse import unquote
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from core.storage import SecureFileStorage

logger = logging.getLogger('file_manager.storage')

class PathManager:
    """
    Handles file storage operations with proper error handling using SecureFileStorage.
    This class ensures all file operations go through SecureFileStorage for security
    and storage backend agnostic operations.
    """
    
    def __init__(self, user_id=None):
        """
        Initialize with optional user_id for base directory and SecureFileStorage.
        
        Args:
            user_id: The user ID to use as the base directory
        """
        self.user_id = str(user_id) if user_id else None
        self.base_dir = f"{self.user_id}/" if self.user_id else ""
        # Initialize SecureFileStorage. We assume files here are private.
        self.secure_storage = SecureFileStorage(private=True, collection='')
        
    def _get_full_path(self, path):
        """
        Get full path including user base directory.
        
        Args:
            path: The relative path
            
        Returns:
            The full path including user base directory
        """
        path = path.strip('/')
        # Ensure the path is relative to the user's base directory
        if self.user_id and not path.startswith(self.base_dir):
            return os.path.join(self.base_dir, path)
        # Handle case where user_id is None or path already includes base_dir
        return path
    
    def list_directory(self, path=''):
        """
        List contents of a directory using SecureFileStorage.
        
        Args:
            path: The directory path to list
            
        Returns:
            A list of dictionaries with file/directory information
        """
        try:
            full_path = self._get_full_path(path)
            # Ensure path ends with / for directory operations
            if full_path and not full_path.endswith('/'):
                full_path = f"{full_path}/"
                
            # Use list_directory from SecureFileStorage
            directories, files = self.secure_storage.list_directory(full_path)
            
            contents = []
            
            # Add directories
            for dir_name in sorted(directories):
                if not dir_name.startswith('.'): # Ignore hidden directories
                    dir_path = os.path.join(full_path, dir_name).replace('\\', '/')
                    rel_path = dir_path.replace(self.base_dir, '', 1) if self.base_dir else dir_path
                    contents.append({
                        'name': dir_name,
                        'path': rel_path,
                        'type': 'directory',
                        'size': 0,
                        'last_modified': None
                    })
            
            # Add files
            for file_name in sorted(files):
                if not file_name.startswith('.') and '.keep' not in file_name: # Ignore hidden and .keep files
                    file_path = os.path.join(full_path, file_name).replace('\\', '/')
                    rel_path = file_path.replace(self.base_dir, '', 1) if self.base_dir else file_path
                    
                    try:
                        # Get file info using SecureFileStorage
                        file_size = self.secure_storage.size(file_path)
                        last_modified = None
                        if hasattr(self.secure_storage, 'get_modified_time'):
                            try:
                                last_modified = self.secure_storage.get_modified_time(file_path)
                            except Exception:
                                pass
                        
                        contents.append({
                            'name': file_name,
                            'path': rel_path,
                            'type': 'file',
                            'size': file_size,
                            'extension': os.path.splitext(file_name)[1][1:].lower(),
                            'last_modified': last_modified
                        })
                    except Exception as e:
                        logger.error(f"Error processing file {file_path}: {str(e)}")
                        # Add file with error status
                        contents.append({
                            'name': file_name,
                            'path': rel_path,
                            'type': 'error',
                            'error': str(e)
                        })
            
            return contents
            
        except Exception as e:
            logger.error(f"Error listing directory {path}: {str(e)}")
            raise
    
    def directory_exists(self, path):
        """
        Check if a directory exists using SecureFileStorage.
        
        Args:
            path: The directory path to check
            
        Returns:
            Boolean indicating if directory exists
        """
        try:
            full_path = self._get_full_path(path)
            # Ensure path ends with / for directory operations
            if full_path and not full_path.endswith('/'):
                full_path = f"{full_path}/"
                
            return self.secure_storage.directory_exists(full_path)
        except Exception as e:
            logger.error(f"Error checking if directory exists {path}: {str(e)}")
            return False
    
    def create_directory(self, path):
        """
        Create a directory using SecureFileStorage.
        
        Args:
            path: The directory path to create
            
        Returns:
            The created directory path
        """
        try:
            full_path = self._get_full_path(path)
            # Ensure path ends with / for directory operations
            if full_path and not full_path.endswith('/'):
                full_path = f"{full_path}/"
                
            return self.secure_storage.create_directory(full_path)
        except Exception as e:
            logger.error(f"Error creating directory {path}: {str(e)}")
            raise
    
    def delete_directory(self, path):
        """
        Delete a directory and all its contents using SecureFileStorage.
        
        Args:
            path: The directory path to delete
            
        Returns:
            Number of files deleted
        """
        try:
            full_path = self._get_full_path(path)
            # Ensure path ends with / for directory operations
            if full_path and not full_path.endswith('/'):
                full_path = f"{full_path}/"
                
            return self.secure_storage.delete_directory(full_path)
        except Exception as e:
            logger.error(f"Error deleting directory {path}: {str(e)}")
            raise
    
    def delete_file(self, path):
        """
        Delete a file using SecureFileStorage.
        
        Args:
            path: The file path to delete
            
        Returns:
            Boolean indicating success
        """
        try:
            full_path = self._get_full_path(path)
            
            if self.secure_storage.exists(full_path):
                self.secure_storage.delete(full_path)
                logger.info(f"Successfully deleted file: {full_path}")
                return True
            else:
                logger.warning(f"File not found: {full_path}")
                return False
        except Exception as e:
            logger.error(f"Error deleting file {path}: {str(e)}")
            raise
    
    def batch_delete(self, paths):
        """
        Delete multiple files efficiently using SecureFileStorage.
        
        Args:
            paths: List of file paths to delete
            
        Returns:
            Number of files deleted
        """
        try:
            full_paths = [self._get_full_path(path) for path in paths]
            return self.secure_storage.batch_delete(full_paths)
        except Exception as e:
            logger.error(f"Error batch deleting files: {str(e)}")
            raise
    
    def save_file(self, file_obj, path):
        """
        Save an uploaded file using SecureFileStorage.
        
        Args:
            file_obj: The file object to save
            path: The path to save the file to
            
        Returns:
            The saved file path
        """
        try:
            full_path = self._get_full_path(path)
            logger.debug(f"Saving file to storage path: {full_path}")
            
            # Use SecureFileStorage's _save method
            saved_path = self.secure_storage._save(full_path, file_obj)
            logger.info(f"File saved successfully: {saved_path}")
            
            # Return the path relative to the user's base directory
            return saved_path.replace(self.base_dir, '', 1) if self.base_dir else saved_path
        except Exception as e:
            logger.error(f"Error saving file {path}: {str(e)}")
            raise
    
    def get_file(self, path):
        """
        Get file contents using SecureFileStorage.
        
        Args:
            path: The file path to get
            
        Returns:
            File contents as bytes
        """
        try:
            full_path = self._get_full_path(path)
            
            if not self.secure_storage.exists(full_path):
                logger.error(f"File not found: {full_path}")
                return None
            
            try:
                with self.secure_storage._open(full_path, 'rb') as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Error reading file {full_path}: {str(e)}")
                return None
        except Exception as e:
            logger.error(f"Error getting file {path}: {str(e)}")
            return None
    
    def move_file(self, source_path, target_path):
        """
        Move a file from source to target using SecureFileStorage.
        
        Args:
            source_path: The source file path
            target_path: The target file path
            
        Returns:
            The target file path
        """
        try:
            full_source_path = self._get_full_path(source_path)
            full_target_path = self._get_full_path(target_path)
            
            # Check if source file exists
            if not self.secure_storage.exists(full_source_path):
                logger.error(f"Source file not found: {full_source_path}")
                return None
            
            # Copy the file to the target path
            with self.secure_storage._open(full_source_path, 'rb') as source_file:
                self.secure_storage._save(full_target_path, source_file)
            
            # Delete the source file
            self.secure_storage.delete(full_source_path)
            
            logger.info(f"Moved file from {full_source_path} to {full_target_path}")
            
            # Return the target path relative to the user's base directory
            return full_target_path.replace(self.base_dir, '', 1) if self.base_dir else full_target_path
        except Exception as e:
            logger.error(f"Error moving file from {source_path} to {target_path}: {str(e)}")
            raise
    
    def get_nested_directory_structure(self):
        """
        Generate a nested directory structure using SecureFileStorage.
        
        Returns:
            A list of dictionaries representing the directory structure
        """
        try:
            return self.secure_storage.get_nested_directory_structure(self.base_dir)
        except Exception as e:
            logger.error(f"Error generating nested directory structure: {str(e)}")
            # Return a basic structure as fallback
            return [{
                'name': 'Home',
                'path': '',
                'directories': []
            }]
    
    def cleanup_keep_files(self):
        """
        Clean up .keep files that are used to create directories.
        
        Returns:
            Number of files deleted
        """
        try:
            # Find all .keep files in the user's directory
            keep_files = []
            
            def find_keep_files(path):
                try:
                    dirs, files = self.secure_storage.list_directory(path)
                    
                    for file_name in files:
                        if '.keep' in file_name:
                            file_path = os.path.join(path, file_name).replace('\\', '/')
                            keep_files.append(file_path)
                            
                    for dir_name in dirs:
                        dir_path = os.path.join(path, dir_name).replace('\\', '/') + '/'
                        find_keep_files(dir_path)
                except Exception as e:
                    logger.error(f"Error finding .keep files in {path}: {str(e)}")
            
            # Start search from user's root directory
            find_keep_files(self.base_dir)
            
            # Delete all found .keep files
            if keep_files:
                deleted_count = self.secure_storage.batch_delete(keep_files)
                logger.info(f"Cleaned up {deleted_count} .keep files for user {self.user_id}")
                return deleted_count
            return 0
        except Exception as e:
            logger.error(f"Error cleaning up .keep files: {str(e)}")
            return 0
