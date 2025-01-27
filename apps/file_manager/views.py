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

def get_directory_contents(request, prefix=None):
    """List contents of a directory in storage"""
    try:
        logger.debug(f"DEFAULT_FILE_STORAGE setting: {settings.DEFAULT_FILE_STORAGE}")
        logger.debug(f"Storage backend type: {type(default_storage._wrapped)}")
        logger.debug(f"Storage backend class: {default_storage._wrapped.__class__.__name__}")
        
        storage = default_storage
        logger.debug(f"Storage backend: {storage.__class__.__name__}")
        logger.debug(f"Attempting to list contents with prefix: {prefix or ''}")

        contents = []
        try:
            # Use the storage backend's listdir method
            directories, files = storage.listdir(prefix or '')
            
            # Add directories
            for dirname in directories:
                full_path = os.path.join(prefix or '', dirname) if prefix else dirname
                contents.append({
                    'name': dirname,
                    'path': full_path,
                    'type': 'directory',
                    'size': 0,
                    'last_modified': None,
                    'url': None,
                    'extension': ''  # Empty extension for directories
                })
            
            # Add files
            for filename in files:
                full_path = os.path.join(prefix or '', filename) if prefix else filename
                try:
                    size = storage.size(full_path)
                except:
                    size = 0
                    
                try:
                    modified = storage.get_modified_time(full_path)
                except:
                    modified = None

                # Get file extension
                _, extension = os.path.splitext(filename)
                extension = extension[1:] if extension else ''  # Remove the dot

                file_data = {
                    'name': filename,
                    'path': full_path,
                    'type': 'file',
                    'size': size,
                    'last_modified': modified,
                    'url': reverse('download_file', args=[full_path]) if full_path else None,
                    'extension': extension.lower()
                }

                # Add csv_text only for CSV files
                if extension.lower() == 'csv':
                    try:
                        file_data['csv_text'] = convert_csv_to_text(full_path)
                    except Exception as e:
                        logger.error(f"Error converting CSV to text: {str(e)}")
                        file_data['csv_text'] = "Error loading CSV content"

                contents.append(file_data)

        except NotImplementedError:
            logger.warning(f"Storage backend {storage.__class__.__name__} doesn't implement listdir")
            return []

        return sorted(contents, key=lambda x: (x['type'] == 'file', x['name'].lower()))

    except Exception as e:
        logger.error(f"Error listing directory contents: {str(e)}", exc_info=True)
        return []

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

@login_required(login_url='/accounts/login/illustration-login/')
def file_manager(request, directory=''):
    """File manager view."""
    try:
        user_id = str(request.user.id)
        full_path = os.path.join(user_id, directory.lstrip('/')) if directory else user_id
        contents = get_directory_contents(request, full_path)
        breadcrumbs = get_breadcrumbs(request)
        
        context = {
            'page_title': 'File Manager',
            'contents': contents,
            'selected_directory': directory,
            'segment': 'file_manager',
            'parent': 'apps',
            'breadcrumbs': breadcrumbs,
            'user_id': user_id,
            'directory': directory,
            'directories': get_directory_contents(request, user_id)
        }
        return render(request, 'pages/apps/file-manager.html', context)
        
    except Exception as e:
        logger.error(f"Error in file manager view: {str(e)}")
        raise Http404

@login_required(login_url='/accounts/login/basic-login/')
def delete_file(request, file_path):
    """Delete file from storage."""
    try:
        user_id = str(request.user.id)
        path = unquote(file_path)
        full_path = os.path.join(user_id, path.lstrip('/'))
        
        if default_storage.exists(full_path):
            if not path.endswith('/'):
                # Delete single file
                default_storage.delete(full_path)
            else:
                # Delete directory and contents for S3/B2
                prefix = full_path.rstrip('/') + '/'
                for obj in default_storage.bucket.objects.filter(Prefix=prefix):
                    obj.delete()
            
            logger.info(f"Deleted: {full_path}")
            
    except Exception as e:
        logger.error(f"Error deleting file: {str(e)}")
        
    return redirect(request.META.get('HTTP_REFERER'))

@login_required(login_url='/accounts/login/basic-login/')
def download_file(request, file_path):
    """Download file or directory as zip."""
    try:
        user_id = str(request.user.id)
        path = unquote(file_path).rstrip('/')  # Remove trailing slash
        
        # Check if the path already starts with user_id to avoid doubling it
        if not path.startswith(user_id):
            full_path = os.path.join(user_id, path.lstrip('/'))
        else:
            full_path = path
            
        logger.info(f"Attempting to download file: {full_path}")
        
        if not default_storage.exists(full_path):
            logger.error(f"File not found: {full_path}")
            raise Http404("File not found")
        
        if path.endswith('/'):
            # Create zip file for directory
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                prefix = full_path.rstrip('/') + '/'
                # Use S3/B2 style listing
                for obj in default_storage.bucket.objects.filter(Prefix=prefix):
                    if not obj.key.endswith('/'):  # Skip directory markers
                        with default_storage.open(obj.key, 'rb') as f:
                            zip_file.writestr(obj.key[len(prefix):], f.read())
            
            response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename="{os.path.basename(path.rstrip("/"))}.zip"'
            return response
        else:
            # Download single file
            try:
                with default_storage.open(full_path, 'rb') as f:
                    content = f.read()
                    response = HttpResponse(content, content_type='application/octet-stream')
                    response['Content-Disposition'] = f'attachment; filename="{os.path.basename(path)}"'
                    return response
            except Exception as e:
                logger.error(f"Error reading file {full_path}: {str(e)}")
                raise Http404("Error reading file")
                
    except Exception as e:
        logger.error(f"Error downloading file: {str(e)}")
        raise Http404("Error downloading file")

@login_required(login_url='/accounts/login/basic-login/')
def upload_file(request):
    """Upload file to storage."""
    try:
        if request.method == 'POST':
            user_id = str(request.user.id)
            file = request.FILES.get('file')
            directory = unquote(request.POST.get('directory', ''))
            
            if file:
                path = os.path.join(user_id, directory.lstrip('/'), file.name)
                default_storage.save(path, ContentFile(file.read()))
                logger.info(f"Uploaded file: {path}")
                
    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}")
        
    return redirect(request.META.get('HTTP_REFERER'))

def get_breadcrumbs(request):
    """Generate breadcrumb navigation."""
    path_components = [unquote(component) for component in request.path.split("/") if component]
    breadcrumbs = []
    url = ''
    
    for component in path_components:
        url += f'/{component}'
        if component == "file-manager":
            component = "media"
        breadcrumbs.append({'name': component, 'url': url})
    
    return breadcrumbs
