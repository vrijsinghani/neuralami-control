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
                    'url': default_storage.url(full_path)
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
        path = unquote(file_path).rstrip('/')
        path_manager = PathManager(user_id=request.user.id)
        
        if path.endswith('/'):
            zip_data = path_manager.create_directory_zip(path)
            if not zip_data:
                raise Http404("No files found in directory")
                
            response = HttpResponse(zip_data, content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename="{os.path.basename(path)}.zip"'
            return response
            
        else:
            file_data = path_manager.download_file(path)
            if not file_data:
                raise Http404("File not found")
                
            response = HttpResponse(file_data, content_type='application/octet-stream')
            response['Content-Disposition'] = f'attachment; filename="{os.path.basename(path)}"'
            return response
            
    except Exception as e:
        logger.error(f"Error downloading file: {str(e)}", exc_info=True)
        raise Http404("Error downloading file")

@login_required
def upload_file(request):
    """Handle file upload"""
    try:
        if request.method == 'POST':
            file_obj = request.FILES.get('file')
            directory = unquote(request.POST.get('directory', ''))
            
            if file_obj:
                path = os.path.join(directory.lstrip('/'), file_obj.name)
                PathManager(user_id=request.user.id).save_file(file_obj, path)
                logger.info(f"File uploaded successfully: {path}")
                
        return redirect(request.META.get('HTTP_REFERER', '/'))
        
    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}", exc_info=True)
        raise

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
