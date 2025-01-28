import os
from django.core.files.storage import default_storage
import logging
import io
import zipfile
import csv

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
            if not default_storage.exists(full_path):
                logger.warning(f"Attempted to delete non-existent path: {full_path}")
                return False
                
            if path.endswith('/'):
                return self._delete_directory(full_path)
            return self._delete_file(full_path)
            
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
        """Delete a directory and its contents"""
        try:
            full_path = self._get_full_path(path)
            prefix = full_path.rstrip('/') + '/'
            logger.debug(f"Attempting to delete directory with prefix: {prefix}")
            
            deleted = False
            for obj in default_storage.bucket.objects.filter(Prefix=prefix):
                logger.debug(f"Deleting object: {obj.key}")
                obj.delete()
                deleted = True
            
            if deleted:
                logger.info(f"Successfully deleted directory and contents: {prefix}")
            else:
                logger.warning(f"No objects found to delete in directory: {prefix}")
                
            return deleted
            
        except Exception as e:
            logger.error(f"Error deleting directory {path}: {str(e)}")
            raise
    
    def save_file(self, file_obj, path):
        """Save an uploaded file"""
        try:
            full_path = self._get_full_path(path)
            saved_path = default_storage.save(full_path, file_obj)
            logger.info(f"Successfully saved file: {saved_path}")
            return saved_path.replace(self.base_dir, '', 1)  # Remove base_dir from path
        except Exception as e:
            logger.error(f"Error saving file {path}: {str(e)}")
            raise

    def download_file(self, path):
        """Get file contents for download"""
        try:
            path = path.strip('/')
            if not default_storage.exists(path):
                logger.error(f"File not found: {path}")
                return None
            
            with default_storage.open(path, 'rb') as f:
                return f.read()
            
        except Exception as e:
            logger.error(f"Error reading file {path}: {str(e)}")
            raise

    def create_directory_zip(self, path):
        """Create zip file from directory contents"""
        try:
            path = path.strip('/')
            zip_buffer = io.BytesIO()
            
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                prefix = path + '/'
                for obj in default_storage.bucket.objects.filter(Prefix=prefix):
                    if not obj.key.endswith('/'):  # Skip directory markers
                        with default_storage.open(obj.key, 'rb') as f:
                            zip_file.writestr(obj.key[len(prefix):], f.read())
                        
            return zip_buffer.getvalue()
            
        except Exception as e:
            logger.error(f"Error creating zip for directory {path}: {str(e)}")
            raise

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