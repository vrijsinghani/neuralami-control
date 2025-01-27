import os
from typing import Optional
from django.conf import settings
from django.core.files.storage import default_storage
from django.contrib.auth import get_user_model
import logging

logger = logging.getLogger(__name__)

def get_safe_path(user_id: int, path: str, directory: Optional[str] = None) -> str:
    """
    Ensures the path is valid for cloud storage and sanitizes it.
    
    Args:
        user_id: The ID of the user
        path: The requested path (/ represents user's media root)
        directory: Optional directory path
    
    Returns:
        str: Sanitized relative path for cloud storage
        
    Raises:
        ValueError: If path attempts directory traversal
    """
    try:
        # Construct user's base path
        user_base_path = str(user_id)
        
        # Handle root directory request
        if path == "/" or path == "":
            return user_base_path
        
        # Remove leading slash if present to make path relative
        path = path.lstrip('/')
        
        # Combine directory and path if directory is provided
        if directory:
            path = os.path.join(directory.lstrip('/'), path)
        
        # Create the full relative path
        relative_path = os.path.join(user_base_path, path)
        
        # Normalize path to resolve any . or .. components
        normalized_path = os.path.normpath(relative_path)
        
        # Security check: Verify the normalized path starts with user_id
        if not normalized_path.startswith(user_base_path):
            error_msg = f"Access denied: Path {path} attempts to access parent directory"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Ensure the path exists in storage (create if needed)
        if not path.endswith('/'):  # Only create directories for directory paths
            directory_path = os.path.dirname(normalized_path)
            if directory_path and not default_storage.exists(directory_path):
                # Create an empty placeholder file to ensure directory exists
                default_storage.save(os.path.join(directory_path, '.keep'), ContentFile(''))
                logger.debug(f"Created directory structure: {directory_path}")
        
        return normalized_path
        
    except Exception as e:
        if not isinstance(e, ValueError):  # Don't log ValueError as it's already logged
            logger.error(f"Error in get_safe_path: {str(e)}")
        raise 