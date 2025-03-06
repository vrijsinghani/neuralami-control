import mimetypes
import os
import re
from django.http import HttpResponse, Http404
from django.core.files.storage import default_storage
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
import logging

logger = logging.getLogger(__name__)

@login_required
def serve_protected_file(request, path):
    """
    Serve a file from storage with access control.
    
    This view provides authenticated access to files stored in Django's storage backend.
    It can be extended to include specific permission checks based on the file path.
    
    Args:
        request: The HTTP request
        path: The path to the file in storage
        
    Returns:
        HttpResponse with the file content
    """
    logger.debug(f"Serving protected file: {path}")
    
    # Default permission to True for authenticated users
    has_permission = True
    
    # Example permission check for organization logos
    if path.startswith('organization_logos/'):
        # Organization logos can be viewed by any authenticated user
        # Additional permissions could be added here if needed
        pass
    
    # Permission check for user avatars
    elif path.startswith('user_avatars/'):
        # Extract user ID from path (format: user_avatars/user_id/filename)
        user_id_match = re.match(r'user_avatars/(\d+)/.*', path)
        
        if user_id_match:
            avatar_user_id = user_id_match.group(1)
            # Only allow access if it's the user's own avatar or they're an admin
            if str(request.user.id) != avatar_user_id and not request.user.is_staff:
                logger.warning(f"User {request.user.id} tried to access avatar of user {avatar_user_id}")
                has_permission = False
        else:
            # If we can't extract a user ID, default to allowed for backward compatibility
            # But log it as a potential issue
            logger.warning(f"Couldn't extract user ID from avatar path: {path}")
    
    if not has_permission:
        logger.warning(f"User {request.user.id} denied access to {path}")
        raise Http404("File not found")
    
    # Check if file exists
    if not default_storage.exists(path):
        logger.error(f"File not found in storage: {path}")
        raise Http404("File not found")
    
    try:
        # Open the file and read content
        file_content = default_storage.open(path, 'rb').read()
        
        # Guess content type
        content_type, encoding = mimetypes.guess_type(path)
        if content_type is None:
            content_type = 'application/octet-stream'
        
        # Create response with file content
        response = HttpResponse(file_content, content_type=content_type)
        
        # Add Content-Disposition header for browser handling
        filename = os.path.basename(path)
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        
        return response
    except Exception as e:
        logger.error(f"Error serving file {path}: {str(e)}", exc_info=True)
        raise Http404("Error serving file") 