import os
from django.core.files.storage import default_storage
import logging
import io
import zipfile
import csv
from urllib.parse import unquote

logger = logging.getLogger(__name__)

class PathManager:
    """Handles file storage operations with proper error handling"""
    
    def __init__(self, user_id=None):
        """Initialize with optional user_id for base directory"""
        self.user_id = str(user_id) if user_id else None
        self.base_dir = f"{self.user_id}/" if self.user_id else ""
        
    def _get_full_path(self, path):
        """Get full path including user base directory"""
        path = path.strip('/')
        if self.user_id and not path.startswith(f"{self.user_id}/"):
            return os.path.join(self.base_dir, path)
        return path
    
    def list_contents(self, prefix=''):
        """List contents of a directory"""
        try:
            prefix = self._get_full_path(prefix)
            if prefix:
                prefix = f"{prefix}/"
                
            directories, files = default_storage.listdir(prefix)
            contents = []
            
            # Add directories
            for dir_name in sorted(directories):
                if not dir_name.startswith('.'):
                    full_path = os.path.join(prefix, dir_name) if prefix else dir_name
                    contents.append({
                        'name': dir_name,
                        'path': full_path.replace(self.base_dir, '', 1),  # Remove base_dir from path
                        'type': 'directory',
                        'size': 0,
                    })
            
            # Add files
            for file_name in sorted(files):
                if not file_name.startswith('.'):
                    full_path = os.path.join(prefix, file_name) if prefix else file_name
                    contents.append({
                        'name': file_name,
                        'path': full_path.replace(self.base_dir, '', 1),  # Remove base_dir from path
                        'type': 'file',
                        'size': default_storage.size(full_path),
                        'extension': os.path.splitext(file_name)[1][1:].lower(),
                        'url': default_storage.url(full_path)
                    })
                    
            return contents
            
        except Exception as e:
            logger.error(f"Error listing contents: {str(e)}")
            raise
    
    def delete(self, path):
        """Delete a file or directory"""
        try:
            full_path = self._get_full_path(path)
            
            # First check if it's a directory by looking for directory marker
            dir_path = full_path.rstrip('/') + '/'
            dir_objects = list(default_storage.bucket.objects.filter(Prefix=dir_path))
            
            if dir_objects:  # Directory exists
                return self._delete_directory(dir_path)
            
            # Then check if it's a file
            if default_storage.exists(full_path):
                return self._delete_file(full_path)
            
            logger.warning(f"Path not found: {full_path}")
            return False
            
        except Exception as e:
            logger.error(f"Error deleting path {path}: {str(e)}")
            raise
    
    def _delete_file(self, path):
        """Delete a single file"""
        try:
            full_path = self._get_full_path(path)
            logger.debug(f"Checking existence of path: {full_path}")
            # List bucket contents to verify path
            for obj in default_storage.bucket.objects.filter(Prefix=full_path):
                logger.debug(f"Found object in bucket: {obj.key}")
            
            if not default_storage.exists(full_path):
                logger.warning(f"File not found for deletion: {full_path}")
                return False
            
            default_storage.delete(full_path)
            logger.info(f"Successfully deleted file: {full_path}")
            return True
        except Exception as e:
            logger.error(f"Error deleting file {full_path}: {str(e)}")
            raise
    
    def _delete_directory(self, path):
        """Delete a directory and its contents using Django storage API"""
        try:
            full_path = self._get_full_path(path)
            dirs, files = default_storage.listdir(full_path)
            
            # Delete all files recursively
            deleted = False
            for file_name in files:
                file_path = os.path.join(full_path, file_name)
                default_storage.delete(file_path)
                deleted = True
            
            # Recursively delete subdirectories
            for dir_name in dirs:
                self._delete_directory(os.path.join(full_path, dir_name))
            
            # Also delete the directory itself if empty
            if not deleted and default_storage.exists(full_path):
                default_storage.delete(full_path)
            
            return True
            
        except Exception as e:
            logger.error(f"Error deleting directory {path}: {str(e)}")
            raise
    
    def save_file(self, file_obj, path):
        """Save an uploaded file"""
        try:
            full_path = self._get_full_path(path)
            logger.debug(f"Saving file to storage path: {full_path}")
            
            saved_path = default_storage.save(full_path, file_obj)
            logger.info(f"File saved successfully: {saved_path}")
            
            # Verify storage
            if default_storage.exists(saved_path):
                logger.debug(f"Storage verification passed: {saved_path}")
            else:
                logger.error(f"Storage verification failed: {saved_path}")
            
            return saved_path.replace(self.base_dir, '', 1)
            
        except Exception as e:
            logger.error(f"Error saving file {path}: {str(e)}")
            raise

    def download_file(self, path):
        """Get file contents for download"""
        try:
            # Normalize the path and handle URL encoding
            path = unquote(path).strip('/')
            full_path = self._get_full_path(path)
            
            logger.debug(f"Attempting to download file: {full_path}")
            
            if not default_storage.exists(full_path):
                logger.error(f"File not found: {full_path}")
                return None
            
            try:
                with default_storage.open(full_path, 'rb') as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Error reading file {full_path}: {str(e)}")
                return None
            
        except Exception as e:
            logger.error(f"Error in download_file for path {path}: {str(e)}")
            return None

    def create_directory_zip(self, path):
        """Create zip file from directory contents"""
        try:
            path = path.strip('/')
            full_path = self._get_full_path(path)
            logger.debug(f"Creating zip for directory: {full_path}")
            
            zip_buffer = io.BytesIO()
            
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                # List all files in the directory
                dirs, files = default_storage.listdir(full_path)
                
                # Add files from current directory
                for file_name in files:
                    file_path = os.path.join(full_path, file_name)
                    logger.debug(f"Adding file to zip: {file_path}")
                    
                    try:
                        with default_storage.open(file_path, 'rb') as f:
                            zip_file.writestr(file_name, f.read())
                    except Exception as e:
                        logger.error(f"Error adding file {file_path} to zip: {str(e)}")
                
                # Recursively add files from subdirectories
                for dir_name in dirs:
                    dir_path = os.path.join(full_path, dir_name)
                    self._add_directory_to_zip(zip_file, dir_path, dir_name)
            
            zip_data = zip_buffer.getvalue()
            if not zip_data:
                logger.warning(f"No files found in directory: {full_path}")
                return None
            
            return zip_data
            
        except Exception as e:
            logger.error(f"Error creating zip for directory {path}: {str(e)}")
            return None

    def _add_directory_to_zip(self, zip_file, dir_path, rel_path):
        """Recursively add directory contents to zip file"""
        try:
            dirs, files = default_storage.listdir(dir_path)
            
            # Add files in this directory
            for file_name in files:
                file_path = os.path.join(dir_path, file_name)
                zip_path = os.path.join(rel_path, file_name)
                logger.debug(f"Adding file to zip: {file_path} as {zip_path}")
                
                try:
                    with default_storage.open(file_path, 'rb') as f:
                        zip_file.writestr(zip_path, f.read())
                except Exception as e:
                    logger.error(f"Error adding file {file_path} to zip: {str(e)}")
            
            # Recursively process subdirectories
            for subdir in dirs:
                new_dir_path = os.path.join(dir_path, subdir)
                new_rel_path = os.path.join(rel_path, subdir)
                self._add_directory_to_zip(zip_file, new_dir_path, new_rel_path)
            
        except Exception as e:
            logger.error(f"Error adding directory {dir_path} to zip: {str(e)}")

    def convert_csv_to_text(self, path, max_chars=1000):
        """Convert CSV file content to text with character limit"""
        try:
            with default_storage.open(path, 'r') as file:
                reader = csv.reader(file)
                rows = [next(reader) for _ in range(10)]  # Get first 10 rows
                text = '\n'.join(','.join(row) for row in rows)
                
                if len(text) > max_chars:
                    return text[:max_chars] + "...\n(Preview truncated. Download to see full content)"
                return text
            
        except StopIteration:
            return text
        except Exception as e:
            logger.error(f"Error converting CSV to text: {str(e)}")
            return "Error loading CSV content"

    def delete_directory(self, path):
        """Delete directory recursively"""
        try:
            # Implementation depends on your storage backend
            # Example for S3:
            dir_path = f"{self.user_id}{path}"
            if not dir_path.endswith('/'):
                dir_path += '/'
                
            # List all objects in the directory
            objects_to_delete = default_storage.bucket.objects.filter(Prefix=dir_path)
            delete_request = {'Objects': [{'Key': o.key} for o in objects_to_delete]}
            if delete_request['Objects']:
                default_storage.bucket.delete_objects(Delete=delete_request)
            return True
        except Exception as e:
            logger.error(f"Error deleting directory {path}: {str(e)}")
            return False 