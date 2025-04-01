import os
from django.core.files.storage import default_storage
from core.storage import SecureFileStorage # Import SecureFileStorage
import logging
import io
import zipfile
import csv
from urllib.parse import unquote

logger = logging.getLogger(__name__)

class PathManager:
    """Handles file storage operations with proper error handling using SecureFileStorage"""
    
    def __init__(self, user_id=None):
        """Initialize with optional user_id for base directory and SecureFileStorage"""
        self.user_id = str(user_id) if user_id else None
        self.base_dir = f"{self.user_id}/" if self.user_id else ""
        # Initialize SecureFileStorage. We assume files here are private.
        # Collection is not set here, path construction happens in _get_full_path
        self.secure_storage = SecureFileStorage(private=True, collection='') 
        
    def _get_full_path(self, path):
        """Get full path including user base directory"""
        path = path.strip('/')
        # Ensure the path is relative to the user's base directory
        if self.user_id and not path.startswith(self.base_dir):
            return os.path.join(self.base_dir, path)
        # Handle case where user_id is None (e.g., admin access?) or path already includes base_dir
        return path
    
    def list_contents(self, prefix=''):
        """List contents of a directory using the underlying storage"""
        try:
            prefix = self._get_full_path(prefix)
            # Ensure prefix ends with / for directory listing
            if prefix and not prefix.endswith('/'):
                prefix = f"{prefix}/"
                
            # Use listdir from the underlying storage accessed via SecureFileStorage
            directories, files = self.secure_storage.storage.listdir(prefix)
            contents = []
            
            # Add directories
            for dir_name in sorted(directories):
                if not dir_name.startswith('.'): # Ignore hidden directories
                    full_path = os.path.join(prefix, dir_name) if prefix else dir_name
                    # Generate URL using secure_storage.url which handles private/public
                    dir_url = self.secure_storage.url(full_path + '/') # Append slash for consistency? Or handle in view?
                    contents.append({
                        'name': dir_name,
                        'path': full_path.replace(self.base_dir, '', 1), # Remove base_dir for display path
                        'type': 'directory',
                        'size': 0, # Directories don't have a size in this context
                        'url': dir_url # URL to browse the directory
                    })
            
            # Add files
            for file_name in sorted(files):
                if not file_name.startswith('.'): # Ignore hidden files
                    full_path = os.path.join(prefix, file_name) if prefix else file_name
                    try:
                        # Get size and URL using secure_storage methods
                        file_size = self.secure_storage.size(full_path)
                        file_url = self.secure_storage.url(full_path) 
                        contents.append({
                            'name': file_name,
                            'path': full_path.replace(self.base_dir, '', 1), # Remove base_dir for display path
                            'type': 'file',
                            'size': file_size,
                            'extension': os.path.splitext(file_name)[1][1:].lower(),
                            'url': file_url # URL for preview/download via secure view
                        })
                    except Exception as file_e:
                        logger.error(f"Error processing file {full_path}: {str(file_e)}")
                        # Optionally add file with error status
                        contents.append({
                             'name': file_name,
                             'path': full_path.replace(self.base_dir, '', 1),
                             'type': 'error',
                             'error': str(file_e)
                        })

            return contents
            
        except Exception as e:
            logger.error(f"Error listing contents for prefix '{prefix}': {str(e)}", exc_info=True)
            raise # Re-raise the exception to be handled by the view

    def delete(self, path):
        """Delete a file or directory using SecureFileStorage"""
        try:
            full_path = self._get_full_path(path)
            
            # Check if it's a file first using secure_storage.exists
            if self.secure_storage.exists(full_path):
                 # Attempt to determine if it's a directory by checking for trailing slash behavior 
                 # or by trying to list its contents. This part is tricky across backends.
                 # A common pattern is to try deleting as a file first.
                 try:
                     self.secure_storage.delete(full_path)
                     logger.info(f"Successfully deleted file: {full_path}")
                     return True
                 except Exception as file_delete_error:
                     # If deleting as a file fails, it might be a directory.
                     logger.warning(f"Could not delete {full_path} as file ({file_delete_error}), trying as directory.")
                     # Proceed to directory deletion logic
                     pass

            # If it wasn't deleted as a file or didn't exist as a file, try deleting as a directory
            # Need robust way to check if it's a directory. Listing is one option.
            # Use the underlying storage for listdir
            try:
                 dir_path_check = full_path.rstrip('/') + '/' # Ensure trailing slash for listing
                 dirs, files = self.secure_storage.storage.listdir(dir_path_check)
                 # If listdir succeeds without error and/or returns content, assume it's a directory
                 if dirs is not None or files is not None: 
                      logger.info(f"{full_path} appears to be a directory. Proceeding with directory deletion.")
                      return self._delete_directory_recursive(dir_path_check)
            except Exception as list_err:
                 # If listdir fails, it's likely not a directory or doesn't exist
                 logger.warning(f"Could not list contents of {dir_path_check} ({list_err}). Assuming not a directory or does not exist.")
                 pass

            logger.warning(f"Path not found or could not be deleted: {full_path}")
            return False
            
        except Exception as e:
            logger.error(f"Error deleting path {path}: {str(e)}", exc_info=True)
            raise

    def _delete_directory_recursive(self, dir_path):
        """Recursively delete a directory using SecureFileStorage"""
        try:
            # Use underlying storage's listdir via secure_storage
            dirs, files = self.secure_storage.storage.listdir(dir_path)
            
            # Delete files in the current directory
            for file_name in files:
                file_path = os.path.join(dir_path, file_name)
                try:
                    self.secure_storage.delete(file_path)
                    logger.debug(f"Deleted file: {file_path}")
                except Exception as e:
                    logger.error(f"Error deleting file {file_path}: {str(e)}")
                    # Continue deleting other files/dirs even if one fails? Or raise?
                    raise

            # Recursively delete subdirectories
            for dir_name in dirs:
                subdir_path = os.path.join(dir_path, dir_name) + '/' # Ensure trailing slash
                self._delete_directory_recursive(subdir_path)
            
            # Finally, delete the now-empty directory itself
            # Some storage backends might automatically remove empty "folders", 
            # others might require an explicit delete. The `delete` method should handle this.
            # We attempt to delete the directory path itself. If it's just a prefix (like S3),
            # this might do nothing, which is fine. If it's an actual directory object, it should be deleted.
            try:
                # Attempt to delete the directory marker/object itself
                self.secure_storage.delete(dir_path.rstrip('/')) # Delete without trailing slash
                logger.info(f"Successfully deleted directory: {dir_path}")
            except Exception as e:
                 # If the backend doesn't support explicit directory deletion or it was already removed
                 logger.warning(f"Could not explicitly delete directory path {dir_path}: {str(e)}. May already be removed.")

            return True
        except Exception as e:
            # If listdir fails (e.g., directory doesn't exist anymore)
            if "NoSuchKey" in str(e) or "does not exist" in str(e): # Example error checks
                 logger.warning(f"Directory {dir_path} likely already deleted or does not exist: {str(e)}")
                 return True # Consider it successful if it's already gone
            logger.error(f"Error deleting directory contents {dir_path}: {str(e)}", exc_info=True)
            raise # Re-raise the exception

    def save_file(self, file_obj, path):
        """Save an uploaded file using SecureFileStorage"""
        try:
            full_path = self._get_full_path(path)
            logger.debug(f"Saving file to storage path via SecureStorage: {full_path}")
            
            # Use SecureFileStorage's _save method
            saved_path = self.secure_storage._save(full_path, file_obj)
            logger.info(f"File saved successfully via SecureStorage: {saved_path}")
            
            # Verify storage using SecureFileStorage's exists method
            if self.secure_storage.exists(saved_path):
                logger.debug(f"SecureStorage verification passed: {saved_path}")
            else:
                # This case should ideally not happen if _save succeeded without error
                logger.error(f"SecureStorage verification failed after save: {saved_path}")
            
            # Return the path relative to the user's base directory
            return saved_path.replace(self.base_dir, '', 1) if self.base_dir else saved_path
            
        except Exception as e:
            logger.error(f"Error saving file {path} via SecureStorage: {str(e)}", exc_info=True)
            raise

    def download_file(self, path):
        """Get file contents for download using SecureFileStorage"""
        try:
            # Normalize the path and handle URL encoding
            path = unquote(path).strip('/')
            full_path = self._get_full_path(path)
            
            logger.debug(f"Attempting to download file via SecureStorage: {full_path}")
            
            # Check existence using SecureFileStorage
            if not self.secure_storage.exists(full_path):
                logger.error(f"File not found via SecureStorage: {full_path}")
                return None
            
            try:
                # Open using SecureFileStorage's _open method
                with self.secure_storage._open(full_path, 'rb') as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Error reading file {full_path} via SecureStorage: {str(e)}")
                return None # Or re-raise depending on desired view behavior
            
        except Exception as e:
            logger.error(f"Error in download_file for path {path} using SecureStorage: {str(e)}", exc_info=True)
            return None # Or re-raise

    def create_directory_zip(self, path):
        """Create zip file from directory contents using SecureFileStorage"""
        try:
            path = path.strip('/')
            full_path = self._get_full_path(path)
            logger.debug(f"Creating zip for directory via SecureStorage: {full_path}")
            
            zip_buffer = io.BytesIO()
            
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                # List files using the underlying storage via SecureFileStorage
                # Need to handle potential errors if directory doesn't exist
                try:
                    dirs, files = self.secure_storage.storage.listdir(full_path.rstrip('/') + '/')
                except Exception as list_e:
                     logger.error(f"Cannot list directory {full_path} to create zip: {list_e}")
                     return None # Cannot create zip if directory cannot be listed

                # Add files from current directory
                for file_name in files:
                    file_path = os.path.join(full_path, file_name)
                    logger.debug(f"Adding file to zip: {file_path}")
                    
                    try:
                        # Open file using SecureFileStorage's _open
                        with self.secure_storage._open(file_path, 'rb') as f:
                            zip_file.writestr(file_name, f.read())
                    except Exception as e:
                        logger.error(f"Error adding file {file_path} to zip: {str(e)}")
                        # Optionally skip this file and continue? Or fail the zip creation?
                
                # Recursively add files from subdirectories
                for dir_name in dirs:
                    dir_path = os.path.join(full_path, dir_name)
                    # Pass the relative path within the zip file correctly
                    self._add_directory_to_zip(zip_file, dir_path, dir_name) 
            
            zip_data = zip_buffer.getvalue()
            if not zip_data:
                logger.warning(f"No files found in directory: {full_path}, zip is empty.")
                # Decide whether to return None or an empty zip buffer
                # Returning None seems reasonable if the directory was truly empty or only contained errors
                return None 
            
            return zip_data
            
        except Exception as e:
            logger.error(f"Error creating zip for directory {path}: {str(e)}", exc_info=True)
            return None # Return None on error

    def _add_directory_to_zip(self, zip_file, dir_path, rel_path):
        """Recursively add directory contents to zip file using SecureFileStorage"""
        try:
            # Ensure dir_path has trailing slash for listdir
            dir_path_list = dir_path.rstrip('/') + '/'
            # Use underlying storage's listdir via SecureFileStorage
            dirs, files = self.secure_storage.storage.listdir(dir_path_list)
            
            # Add files in this directory
            for file_name in files:
                file_path = os.path.join(dir_path, file_name) # Use original dir_path for joining
                zip_path = os.path.join(rel_path, file_name) # Path inside the zip file
                logger.debug(f"Adding file to zip: {file_path} as {zip_path}")
                
                try:
                    # Open file using SecureFileStorage's _open
                    with self.secure_storage._open(file_path, 'rb') as f:
                        zip_file.writestr(zip_path, f.read())
                except Exception as e:
                    logger.error(f"Error adding file {file_path} to zip: {str(e)}")
                    # Continue with next file?
            
            # Recursively process subdirectories
            for subdir in dirs:
                new_dir_path = os.path.join(dir_path, subdir)
                new_rel_path = os.path.join(rel_path, subdir)
                self._add_directory_to_zip(zip_file, new_dir_path, new_rel_path)
            
        except Exception as e:
            # Log error if listing subdirectory fails, but potentially continue building zip
            logger.error(f"Error adding directory {dir_path} contents to zip: {str(e)}")
            # Decide if this error should stop the whole zip creation process

    def convert_csv_to_text(self, path, max_chars=1000):
        """Convert CSV file content to text with character limit using SecureFileStorage"""
        try:
            full_path = self._get_full_path(path)
            # Open using SecureFileStorage's _open method
            # Need to handle text mode ('rt') - SecureFileStorage._open might return bytes
            with self.secure_storage._open(full_path, 'rb') as file_bytes: # Open as bytes first
                 # Decode bytes to text, handling potential encoding issues
                 try:
                     file_content = file_bytes.read().decode('utf-8')
                 except UnicodeDecodeError:
                     logger.warning(f"UTF-8 decoding failed for {full_path}, trying latin-1")
                     # Reset stream position if necessary (BytesIO allows re-reading)
                     file_bytes.seek(0) 
                     file_content = file_bytes.read().decode('latin-1', errors='replace')

                 # Use io.StringIO to treat the decoded string as a file for csv.reader
                 file_text_io = io.StringIO(file_content)
                 reader = csv.reader(file_text_io)
                 
                 content = []
                 current_chars = 0
                 for row in reader:
                      row_text = ','.join(row)
                      if current_chars + len(row_text) + 1 > max_chars: # +1 for newline
                           remaining_chars = max_chars - current_chars
                           if remaining_chars > 3: # Need space for "..."
                                content.append(row_text[:remaining_chars-3] + "...")
                           break # Stop reading rows
                      content.append(row_text)
                      current_chars += len(row_text) + 1
                 
                 final_text = '\n'.join(content)
                 if current_chars >= max_chars: # Check if truncation happened within the last row or exactly at limit
                     # Add truncation indicator if not already added
                     if not final_text.endswith("..."):
                          final_text += "\n... (Preview truncated)" 
                 
                 return final_text

        except Exception as e:
            logger.error(f"Error converting CSV {path} to text: {str(e)}", exc_info=True)
            return f"Error loading CSV content: {str(e)}"

    # Removed obsolete delete_directory method
    # def delete_directory(self, path): ... 