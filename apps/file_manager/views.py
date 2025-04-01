import os
import csv
from django.shortcuts import render, redirect
from django.http import HttpResponse, Http404, JsonResponse
from django.core.files.base import ContentFile
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from urllib.parse import unquote
from .models import FileInfo
import logging
import tempfile
import zipfile
import io
from django.conf import settings
import json
from .storage import PathManager
from django.views.decorators.csrf import csrf_exempt
import mimetypes

logger = logging.getLogger(__name__)

@login_required(login_url='/accounts/login/basic-login/')
def save_info(request, file_path):
    """Save file information."""
    path = unquote(file_path)
    if request.method == 'POST':
        FileInfo.objects.update_or_create(
            path=path,
            defaults={'info': request.POST.get('info')}
        )
    return redirect(request.META.get('HTTP_REFERER'))

@login_required
def file_manager(request, path=''):
    """Render file manager view with directory contents"""
    logger.debug("FILE_MANAGER VIEW ENTERED")
    try:
        path = path.strip('/')
        path_manager = PathManager(user_id=request.user.id)
        
        context = {
            'current_path': path,
            'contents': path_manager.list_contents(path),
            'breadcrumbs': get_breadcrumbs(path),
            'user_id': request.user.id
        }
        
        return render(request, 'file_manager/file-manager.html', context)
    except Exception as e:
        logger.error(f"Error in file manager view: {str(e)}", exc_info=True)
        return render(request, 'file_manager/file-manager.html', {
            'error': str(e),
            'current_path': path,
            'contents': [],
            'breadcrumbs': get_breadcrumbs(path),
            'user_id': request.user.id
        })

@csrf_exempt
@login_required
def delete_file(request, file_path):
    """Delete file or directory using PathManager"""
    logger.debug("DELETE_FILE VIEW ENTERED - PATH: %s", file_path)
    try:
        path = unquote(file_path).rstrip('/')
        logger.debug(f"Deleting: {path}")
        path_manager = PathManager(user_id=request.user.id)
        
        # Let PathManager handle directory/file detection
        success = path_manager.delete(path)
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            if success:
                return JsonResponse({'status': 'success'})
            return JsonResponse({'status': 'error', 'message': 'Path not found or could not be deleted'}, status=404)
            
        referer = request.META.get('HTTP_REFERER', reverse('file_manager:index'))
        return redirect(referer)
        
    except Exception as e:
        logger.error(f"Error deleting {path}: {str(e)}", exc_info=True)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
        raise

@login_required
def download_file(request, file_path):
    """Download file or directory as zip using PathManager"""
    try:
        # Log the raw file_path before any processing
        logger.debug(f"Raw download file_path: {file_path}")
        
        # Normalize and decode the path
        path = unquote(file_path).rstrip('/')
        logger.debug(f"Processed path after unquote: {path}")
        
        path_manager = PathManager(user_id=request.user.id)
        logger.debug(f"User ID: {request.user.id}")
        
        # Check if this is a directory by looking at the original file_path
        is_directory = file_path.endswith('/')
        logger.debug(f"Is directory request: {is_directory}")
        
        if is_directory:
            logger.debug(f"Creating zip for directory: {path}")
            zip_data = path_manager.create_directory_zip(path)
            if not zip_data:
                logger.error(f"No files found or error creating zip for directory: {path}")
                raise Http404("No files found in directory or error creating zip.")
                
            # Sanitize filename for Content-Disposition
            zip_filename = os.path.basename(path) if path else f"user_{request.user.id}_files"
            safe_zip_filename = zip_filename.replace('"', '\\"') + '.zip'
            
            response = HttpResponse(zip_data, content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename="{safe_zip_filename}"'
            return response
        else:
            file_data = path_manager.download_file(path)
            if file_data is None:
                logger.error(f"File not found or error reading file via PathManager: {path}")
                raise Http404("File not found or could not be read")
                
            filename = os.path.basename(path)
            safe_filename = filename.replace('"', '\\"')
            
            # Determine content type (optional but recommended)
            content_type, encoding = mimetypes.guess_type(filename)
            if content_type is None:
                content_type = 'application/octet-stream' # Default binary type

            response = HttpResponse(file_data, content_type=content_type)
            response['Content-Disposition'] = f'attachment; filename="{safe_filename}"'
            return response
            
    except Http404 as e:
        logger.warning(f"Download failed (404): {str(e)} for path {file_path}")
        raise # Re-raise Http404 to let Django handle it
    except Exception as e:
        logger.error(f"Error downloading file/directory {file_path}: {str(e)}", exc_info=True)
        # Generic error, return 500 or raise Http404? Http404 might be safer.
        raise Http404(f"Error downloading file: {str(e)}") 

@login_required
def upload_file(request):
    """Handle file upload using PathManager"""
    try:
        logger.debug(f"Upload request received. Method: {request.method}")
        
        if request.method == 'POST':
            logger.debug(f"POST data: {request.POST}")
            logger.debug(f"FILES: {request.FILES}")
            
            file_obj = request.FILES.get('file')
            if not file_obj:
                logger.error("No file found in upload request")
                # Consider returning an error message via messages framework
                return redirect(request.META.get('HTTP_REFERER', reverse('file_manager:index')))
            
            directory = unquote(request.POST.get('directory', '')).strip('/')
            logger.debug(f"Raw directory from POST: '{request.POST.get('directory', '')}'")
            logger.debug(f"Processed directory: '{directory}'")
            
            if file_obj:
                logger.debug(f"Processing file upload: {file_obj.name}")
                path_manager = PathManager(user_id=request.user.id)
                relative_path = os.path.join(directory, file_obj.name)
                logger.debug(f"Attempting to save to relative path: '{relative_path}'")
                
                saved_relative_path = path_manager.save_file(file_obj, relative_path)
                logger.info(f"File uploaded successfully. Relative path: {saved_relative_path}")
            
            if directory:
                return redirect('file_manager:browse', path=directory)
            return redirect('file_manager:index')
            
    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}", exc_info=True)
        # On error, redirect back to previous page with an error message
        # messages.error(request, f"File upload failed: {str(e)}")
        return redirect(request.META.get('HTTP_REFERER', reverse('file_manager:index')))

def get_breadcrumbs(path):
    """Generate breadcrumbs for a given path."""
    # Start with Home as the root
    breadcrumbs = [{'name': 'Home', 'path': '', 'url': reverse('file_manager:index')}]
    
    if not path:
        return breadcrumbs
    
    # Process each part of the path
    parts = path.strip('/').split('/')
    current_path = ''
    for part in parts:
        current_path = os.path.join(current_path, part)
        breadcrumbs.append({
            'name': part,
            'path': current_path,
            'url': reverse('file_manager:browse', kwargs={'path': current_path})
        })
    
    return breadcrumbs

@login_required
def file_preview(request, file_path):
    """Serve file preview through Django using PathManager"""
    try:
        path = unquote(file_path).rstrip('/')
        path_manager = PathManager(user_id=request.user.id)
        
        # Get file extension
        ext = os.path.splitext(path)[1][1:].lower()
        
        # Handle text-based files using PathManager.convert_csv_to_text (or a new generic method)
        text_extensions = {'txt', 'log', 'md', 'json', 'xml', 'yaml', 'yml', 'ini', 'conf', 'csv'}
        
        if ext in text_extensions:
             if ext == 'csv':
                 # Use the dedicated method in PathManager for CSV preview
                 preview_content = path_manager.convert_csv_to_text(path, max_chars=2000) # Increase limit slightly?
                 # Wrap in pre tags for consistent display
                 html_content = f'<pre class="text-light bg-dark p-3">{preview_content}</pre>'
                 return HttpResponse(html_content, content_type='text/html')
             else:
                 # For other text files, download and truncate
                 file_data = path_manager.download_file(path)
                 if file_data is None:
                     raise Http404("File not found or cannot be read")
                 
                 # Decode, handling potential errors
                 try:
                     content = file_data.decode('utf-8')
                 except UnicodeDecodeError:
                     logger.warning(f"UTF-8 decoding failed for preview {path}, trying latin-1")
                     content = file_data.decode('latin-1', errors='ignore')
                 
                 # Truncate (e.g., 100 lines or 2000 characters)
                 lines = content.split('\n')[:100]
                 truncated = '\n'.join(lines)
                 if len(truncated) > 2000:
                     truncated = truncated[:2000] + '\n... (Preview truncated)'
                 
                 return HttpResponse(f'<pre class="text-light bg-dark p-3">{truncated}</pre>', 
                                   content_type='text/html')

        # Handle image previews (inline display)
        image_extensions = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg'}
        if ext in image_extensions:
             file_data = path_manager.download_file(path)
             if file_data is None:
                 raise Http404("Image file not found or cannot be read")
             
             content_type, _ = mimetypes.guess_type(path)
             if content_type is None:
                  content_type = 'application/octet-stream' # Fallback
             
             # Return image directly for inline display
             response = HttpResponse(file_data, content_type=content_type)
             # 'inline' suggests browser should display if possible
             response['Content-Disposition'] = f'inline; filename="{os.path.basename(path)}"' 
             return response

        # Default: Attempt download for other types (or show 'preview not available')
        # For security, maybe only allow preview for specific safe types?
        # Let's return a 'preview not available' message for unsupported types.
        logger.warning(f"Preview not supported for file type: {ext} (path: {path})")
        return HttpResponse(f"<div class=\"alert alert-warning\">Preview is not available for this file type (.{ext}). <a href=\"{reverse('file_manager:download', kwargs={'file_path': file_path})}\" class=\"alert-link\">Download file</a> instead.</div>",
                           content_type='text/html', status=200) # Return 200 OK but with message

    except Http404 as e:
         logger.warning(f"File preview failed (404): {str(e)} for path {file_path}")
         raise # Let Django handle 404
    except Exception as e:
        logger.error(f"Error previewing file {file_path}: {str(e)}", exc_info=True)
        # Return generic error message, maybe link to download
        return HttpResponse(f"<div class=\"alert alert-danger\">Error accessing file preview: {str(e)}. You can try to <a href=\"{reverse('file_manager:download', kwargs={'file_path': file_path})}\" class=\"alert-link\">download the file</a>.</div>",
                           content_type='text/html', status=500)
