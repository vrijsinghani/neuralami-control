import os
import csv
from django.shortcuts import render, redirect
from django.http import HttpResponse, Http404, JsonResponse
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from urllib.parse import unquote
from .models import FileInfo
import logging
import tempfile
import zipfile
import io
from storages.backends.s3boto3 import S3Boto3Storage
from django.conf import settings
import json
from .storage import PathManager
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)

def convert_csv_to_text(file_path: str, max_chars: int = 1000) -> str:
    """Convert CSV file content to text with character limit."""
    try:
        with default_storage.open(file_path, 'r') as file:
            reader = csv.reader(file)
            # Get first 10 rows
            rows = [next(reader) for _ in range(10)]
            text = '\n'.join(','.join(row) for row in rows)
            if len(text) > max_chars:
                return text[:max_chars] + "...\n(Preview truncated. Download to see full content)"
            return text
    except StopIteration:
        # If file has fewer than 10 rows
        return text
    except Exception as e:
        logger.error(f"Error converting CSV to text: {str(e)}")
        return "Error loading CSV content"

def get_directory_contents(request, prefix=''):
    """Get contents of a directory in storage."""
    try:
        logger.debug(f"DEFAULT_FILE_STORAGE setting: {settings.DEFAULT_FILE_STORAGE}")
        logger.debug(f"Storage backend type: {type(default_storage)}")
        logger.debug(f"Storage backend class: {default_storage.__class__.__name__}")
        logger.debug(f"Storage backend: {default_storage}")
        logger.debug(f"Attempting to list contents with prefix: {prefix}")

        # Normalize the prefix path
        prefix = prefix.strip('/')
        if prefix:
            prefix = f"{prefix}/"

        # Get list of files directly from storage
        files_and_dirs = []
        
        # List both directories and files
        directories, files = default_storage.listdir(prefix)
        
        # Add directories
        for dir_name in directories:
            if dir_name.startswith('.'):
                continue
                
            full_path = os.path.join(prefix, dir_name) if prefix else dir_name
            files_and_dirs.append({
                'name': dir_name,
                'path': full_path,
                'type': 'directory',
                'size': 0,
                'modified': None
            })

        # Add files
        for file_name in files:
            if file_name.startswith('.'):
                continue
                
            full_path = os.path.join(prefix, file_name) if prefix else file_name
            
            try:
                file_info = {
                    'name': file_name,
                    'path': full_path,
                    'type': 'file',
                    'size': default_storage.size(full_path),
                    'modified': default_storage.get_modified_time(full_path),
                    'extension': os.path.splitext(file_name)[1][1:].lower(),
                    'url': reverse('file_manager:preview', kwargs={'file_path': full_path})
                }
                
                # Add CSV preview if applicable
                if file_info['extension'] == 'csv':
                    file_info['csv_text'] = convert_csv_to_text(full_path)
                    
                files_and_dirs.append(file_info)
            except Exception as e:
                logger.error(f"Error getting info for file {full_path}: {str(e)}")

        # Sort contents - directories first, then files alphabetically
        contents = sorted(files_and_dirs, 
                        key=lambda x: (x['type'] == 'file', x['name'].lower()))

        return JsonResponse({'contents': contents})

    except Exception as e:
        logger.error(f"Error in get_directory_contents: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

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
    logger.debug("FILE_MANAGER VIEW ENTERED")  # Simple test message
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
    """Delete file or directory"""
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
            return JsonResponse({'status': 'error', 'message': 'Not found'}, status=404)
            
        return redirect(request.META.get('HTTP_REFERER', '/'))
        
    except Exception as e:
        logger.error(f"Error deleting {path}: {str(e)}", exc_info=True)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
        raise

@login_required
def download_file(request, file_path):
    """Download file or directory as zip"""
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
                logger.error(f"No files found in directory: {path}")
                raise Http404("No files found in directory")
                
            response = HttpResponse(zip_data, content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename="{os.path.basename(path)}.zip"'
            return response
        else:
            file_data = path_manager.download_file(path)
            if file_data is None:
                logger.error(f"File not found or error reading file: {path}")
                raise Http404("File not found or could not be read")
                
            filename = os.path.basename(path)
            safe_filename = filename.replace('"', '\\"')
            
            response = HttpResponse(file_data, content_type='application/octet-stream')
            response['Content-Disposition'] = f'attachment; filename="{safe_filename}"'
            return response
            
    except Http404:
        raise
    except Exception as e:
        logger.error(f"Error downloading file: {str(e)}", exc_info=True)
        raise Http404("Error downloading file")

@login_required
def upload_file(request):
    """Handle file upload"""
    try:
        logger.debug(f"Upload request received. Method: {request.method}")
        
        if request.method == 'POST':
            logger.debug(f"POST data: {request.POST}")
            logger.debug(f"FILES: {request.FILES}")
            
            file_obj = request.FILES.get('file')
            if not file_obj:
                logger.error("No file found in upload request")
                return redirect(request.META.get('HTTP_REFERER', reverse('file_manager:index')))
            
            directory = unquote(request.POST.get('directory', '')).strip('/')
            logger.debug(f"Raw directory from POST: '{request.POST.get('directory', '')}'")
            logger.debug(f"Processed directory: '{directory}'")
            
            if file_obj:
                logger.debug(f"Processing file upload: {file_obj.name}")
                path_manager = PathManager(user_id=request.user.id)
                full_path = os.path.join(directory, file_obj.name).lstrip('/')
                logger.debug(f"Attempting to save to full path: '{full_path}'")
                
                saved_path = path_manager.save_file(file_obj, full_path)
                logger.info(f"File uploaded successfully. Storage path: {saved_path}")
                
                # Verify file exists after upload
                if default_storage.exists(saved_path):
                    logger.debug(f"File verification successful: {saved_path}")
                else:
                    logger.error(f"File verification failed: {saved_path}")
            
            # Redirect back to the directory where the upload was initiated
            if directory:
                return redirect('file_manager:browse', path=directory)
            return redirect('file_manager:index')
            
    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}", exc_info=True)
        # On error, redirect back to previous page
        return redirect(request.META.get('HTTP_REFERER', reverse('file_manager:index')))

def get_breadcrumbs(path):
    """Generate breadcrumb navigation."""
    try:
        breadcrumbs = [{'name': 'Home', 'path': '', 'url': reverse('file_manager:index')}]
        
        if path:
            current = ''
            parts = path.split('/')
            for part in parts:
                if part:  # Skip empty parts
                    current = f"{current}/{part}".lstrip('/')
                    breadcrumbs.append({
                        'name': part,
                        'path': current,
                        'url': reverse('file_manager:browse', kwargs={'path': current})
                    })
        
        return breadcrumbs
    except Exception as e:
        logger.error(f"Error generating breadcrumbs: {str(e)}")
        return [{'name': 'Home', 'path': '', 'url': reverse('file_manager:index')}]

@login_required
def file_preview(request, file_path):
    """Serve file preview through Django with truncation for text files"""
    try:
        path = unquote(file_path).rstrip('/')
        path_manager = PathManager(user_id=request.user.id)
        full_path = path_manager._get_full_path(path)
        
        # Get file extension
        ext = os.path.splitext(path)[1][1:].lower()
        
        # Handle text-based files
        text_extensions = {'txt', 'log', 'md', 'json', 'xml', 'yaml', 'yml', 'ini', 'conf'}
        if ext in text_extensions:
            content = path_manager.download_file(full_path).decode('utf-8', errors='ignore')
            
            # Truncate to 50 lines or 1000 characters
            lines = content.split('\n')[:50]
            truncated = '\n'.join(lines)
            if len(truncated) > 1000:
                truncated = truncated[:1000] + '\n... (truncated)'
            
            return HttpResponse(f'<pre class="text-light bg-dark p-3">{truncated}</pre>', 
                              content_type='text/html')

        # Existing handling for other file types
        file_data = path_manager.download_file(full_path)
        if not file_data:
            raise Http404("File not found")

        response = HttpResponse(file_data, content_type='application/octet-stream')
        response['Content-Disposition'] = f'inline; filename="{os.path.basename(path)}"'
        return response

    except Exception as e:
        logger.error(f"Error previewing file {path}: {str(e)}", exc_info=True)
        raise Http404("Error accessing file")
