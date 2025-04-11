import os
import csv
import uuid
import json
import random
import mimetypes
import logging
from datetime import datetime
from django.shortcuts import render, redirect
from django.http import HttpResponse, Http404, JsonResponse, FileResponse
from django.conf import settings
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from .models import FileInfo, FileTag
from .storage import PathManager

# Configure logger
logger = logging.getLogger('file_manager.views')

# Create your views here.


@login_required(login_url='/accounts/login/basic-login/')
@require_http_methods(["POST"])
def create_folder(request):
    """Create a new folder using default_storage"""
    user_id = str(request.user.id)

    # Get parent directory and new folder name
    parent_directory = request.POST.get('parent_directory', '')
    folder_name = request.POST.get('folder_name', '').strip()

    if not folder_name:
        if request.headers.get('HX-Request'):
            return HttpResponse("Folder name is required", status=400)
        messages.error(request, "Folder name is required.")
        return redirect(request.META.get('HTTP_REFERER'))

    # Sanitize folder name to prevent path traversal
    folder_name = os.path.basename(folder_name)

    # Create the full path for storage
    if parent_directory:
        folder_path = f"{user_id}/{parent_directory}/{folder_name}/"
    else:
        folder_path = f"{user_id}/{folder_name}/"

    # Normalize path separators
    folder_path = folder_path.replace('\\', '/').replace('//', '/')

    try:
        # Check if folder already exists
        if default_storage.exists(folder_path):
            if request.headers.get('HX-Request'):
                return HttpResponse("Folder already exists", status=400)
            messages.error(request, "Folder already exists.")
            return redirect(request.META.get('HTTP_REFERER'))

        # Create the folder by saving a placeholder file
        # Use a unique name to avoid conflicts
        keep_file = f"{folder_path}/.keep_{uuid.uuid4().hex[:8]}"
        default_storage.save(keep_file, ContentFile(b''))

        # Log the folder creation
        logger.info(f"Created folder: {folder_path} with placeholder file: {keep_file}")

        if request.headers.get('HX-Request'):
            # Return updated folder tree
            directories = generate_nested_directory(user_id)
            context = {
                'directories': directories,
                'selected_directory': os.path.join(parent_directory, folder_name) if parent_directory else folder_name
            }
            response = render(request, 'file_manager/components/folder_tree.html', context)
            response['HX-Trigger'] = 'folderCreated'
            return response

        messages.success(request, f"Folder '{folder_name}' created successfully.")
    except Exception as e:
        if request.headers.get('HX-Request'):
            return HttpResponse(str(e), status=500)
        messages.error(request, f"Error creating folder: {str(e)}")

    return redirect(request.META.get('HTTP_REFERER'))


@login_required(login_url='/accounts/login/basic-login/')
@require_http_methods(["POST"])
def rename_folder(request):
    """Rename an existing folder"""
    user_id = str(request.user.id)
    media_path = os.path.join(settings.MEDIA_ROOT, user_id)

    # Get folder path and new name
    folder_path = request.POST.get('folder_path', '')
    new_name = request.POST.get('new_name', '').strip()

    if not folder_path or not new_name:
        if request.headers.get('HX-Request'):
            return HttpResponse("Folder path and new name are required", status=400)
        messages.error(request, "Folder path and new name are required.")
        return redirect(request.META.get('HTTP_REFERER'))

    # Sanitize new name to prevent path traversal
    new_name = os.path.basename(new_name)

    # Get the full paths
    old_path = os.path.join(media_path, folder_path)
    parent_dir = os.path.dirname(old_path)
    new_path = os.path.join(parent_dir, new_name)

    try:
        # Check if folder exists
        if not os.path.exists(old_path) or not os.path.isdir(old_path):
            if request.headers.get('HX-Request'):
                return HttpResponse("Folder not found", status=404)
            messages.error(request, "Folder not found.")
            return redirect(request.META.get('HTTP_REFERER'))

        # Check if new folder name already exists
        if os.path.exists(new_path):
            if request.headers.get('HX-Request'):
                return HttpResponse("A folder with this name already exists", status=400)
            messages.error(request, "A folder with this name already exists.")
            return redirect(request.META.get('HTTP_REFERER'))

        # Rename the folder
        os.rename(old_path, new_path)

        # Update file paths in database
        old_rel_path = os.path.relpath(old_path, settings.MEDIA_ROOT)
        new_rel_path = os.path.relpath(new_path, settings.MEDIA_ROOT)

        # Convert path separators for consistency
        if os.sep != '/':
            old_rel_path = old_rel_path.replace(os.sep, '/')
            new_rel_path = new_rel_path.replace(os.sep, '/')

        # Update all file paths that start with the old path
        for file_info in FileInfo.objects.filter(path__startswith=old_rel_path + '/'):
            file_info.path = file_info.path.replace(old_rel_path, new_rel_path, 1)
            file_info.save()

        if request.headers.get('HX-Request'):
            # Return updated folder tree
            directories = generate_nested_directory(media_path, media_path)
            context = {
                'directories': directories,
                'selected_directory': os.path.relpath(new_path, media_path)
            }
            return render(request, 'file_manager/components/folder_tree.html', context)

        messages.success(request, f"Folder renamed to '{new_name}' successfully.")
    except Exception as e:
        if request.headers.get('HX-Request'):
            return HttpResponse(str(e), status=500)
        messages.error(request, f"Error renaming folder: {str(e)}")

    return redirect(request.META.get('HTTP_REFERER'))


@login_required(login_url='/accounts/login/basic-login/')
@require_http_methods(["POST"])
def delete_folder(request):
    """Delete a folder and all its contents using PathManager"""
    user_id = str(request.user.id)

    # Get folder path
    folder_path = request.POST.get('folder_path', '')

    # Debug logging
    logger.info(f"Delete folder request received for path: {folder_path}")
    logger.info(f"POST data: {request.POST}")
    logger.info(f"Headers: {request.headers}")
    logger.info(f"Is HTMX request: {request.headers.get('HX-Request')}")

    if not folder_path:
        logger.error("Folder path is empty or missing")
        if request.headers.get('HX-Request'):
            return HttpResponse("Folder path is required", status=400)
        messages.error(request, "Folder path is required.")
        return redirect(request.META.get('HTTP_REFERER'))

    try:
        # Create a PathManager instance for the current user
        path_manager = PathManager(user_id=user_id)

        # Get all files in this folder from the database
        storage_folder_path = f"{user_id}/{folder_path}/"
        storage_folder_path = storage_folder_path.replace('//', '/')
        files_to_delete = []
        file_infos = FileInfo.objects.filter(path__startswith=storage_folder_path)

        # Delete the directory and all its contents using PathManager
        deleted_count = path_manager.delete_directory(folder_path)
        logger.info(f"Deleted {deleted_count} files from directory {folder_path}")

        # Delete all file records from database that were in this folder
        for file_info in file_infos:
            files_to_delete.append(file_info.path)

        # Delete all file records from database
        if files_to_delete:
            FileInfo.objects.filter(path__in=files_to_delete).delete()
            logger.info(f"Deleted {len(files_to_delete)} file records from database")

        if request.headers.get('HX-Request'):
            # Return success message and trigger UI update
            context = {
                'success': True
            }
            response = render(request, 'file_manager/components/folder_delete_result.html', context)
            response['HX-Trigger'] = 'folderDeleted'
            return response

        messages.success(request, "Folder deleted successfully.")
    except Exception as e:
        logger.error(f"Error deleting folder {folder_path}: {str(e)}")
        if request.headers.get('HX-Request'):
            context = {
                'error': f"Error deleting folder: {str(e)}"
            }
            return render(request, 'file_manager/components/folder_delete_result.html', context, status=500)
        messages.error(request, f"Error deleting folder: {str(e)}")

    return redirect(request.META.get('HTTP_REFERER'))


def get_nested_folders(request, directory):
    """Get nested folders for a directory"""
    nested_folders = []

    # Get the current path
    user_id = str(request.user.id) if hasattr(request.user, 'id') else request.user
    current_path = f"{user_id}/{directory}/" if directory else f"{user_id}/"

    # List objects in the current directory
    try:
        objects = default_storage.listdir(current_path)[0]
        for obj in objects:
            folder_path = os.path.join(directory, obj) if directory else obj
            nested_folders.append({
                'name': obj,
                'path': folder_path
            })
    except Exception as e:
        logger.error(f"Error listing nested folders: {str(e)}")

    return nested_folders


@login_required(login_url='/accounts/login/basic-login/')
def rename_file(request):
    """Rename a file using PathManager"""
    # Get file path and new name
    file_path = request.POST.get('file_path', '')
    new_name = request.POST.get('new_name', '').strip()

    logger.info(f"rename_file called with file_path={file_path}, new_name={new_name}")
    logger.info(f"POST data: {request.POST}")
    logger.info(f"Headers: {request.headers}")

    if not file_path or not new_name:
        if request.headers.get('HX-Request'):
            return HttpResponse("File path and new name are required", status=400)
        messages.error(request, "File path and new name are required.")
        return redirect(request.META.get('HTTP_REFERER'))

    # Sanitize new name to prevent path traversal
    new_name = os.path.basename(new_name)

    # Clean up the file path
    file_path = file_path.replace('%slash%', '/')

    # Create a PathManager instance for the current user
    user_id = str(request.user.id)
    path_manager = PathManager(user_id=user_id)

    try:
        # Get the directory
        directory = os.path.dirname(file_path)

        # Construct the new path
        new_path = os.path.join(directory, new_name) if directory else new_name

        logger.info(f"Renaming file from {file_path} to {new_path}")

        # Check if file exists in storage
        if not path_manager.secure_storage.exists(file_path):
            logger.error(f"File not found: {file_path}")
            if request.headers.get('HX-Request'):
                return HttpResponse("File not found", status=404)
            messages.error(request, "File not found.")
            return redirect(request.META.get('HTTP_REFERER'))

        # Check if new file name already exists in storage
        if path_manager.secure_storage.exists(new_path):
            logger.error(f"File already exists: {new_path}")
            if request.headers.get('HX-Request'):
                return HttpResponse("A file with this name already exists", status=400)
            messages.error(request, "A file with this name already exists.")
            return redirect(request.META.get('HTTP_REFERER'))

        # Move the file using PathManager
        path_manager.move_file(file_path, new_path)

        logger.info(f"File renamed successfully from {file_path} to {new_path}")

        # Update file info in database
        file_info = FileInfo.objects.filter(path=file_path).first()
        if file_info:
            file_info.path = new_path
            file_info.filename = new_name
            file_info.save()
            logger.info(f"File info updated for {new_path}")

        # Check if this is an HTMX request
        if request.headers.get('HX-Request'):
            # Instead of trying to rebuild the file list, redirect to the current directory
            # with an HTMX header to trigger a refresh of the file grid
            response = HttpResponse("File renamed successfully")
            response['HX-Redirect'] = request.META.get('HTTP_REFERER', '/file-manager/')
            return response

        messages.success(request, f"File renamed to '{new_name}' successfully.")
    except Exception as e:
        import traceback
        logger.error(f"Error renaming file: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        if request.headers.get('HX-Request'):
            return HttpResponse(str(e), status=500)
        messages.error(request, f"Error renaming file: {str(e)}")

    return redirect(request.META.get('HTTP_REFERER'))


@login_required(login_url='/accounts/login/basic-login/')
@require_http_methods(["POST"])
def move_files(request):
    """Move files to a different folder using PathManager"""
    # Add detailed logging for debugging
    logger.info(f"move_files called with POST data: {request.POST}")
    logger.info(f"Headers: {request.headers}")

    # Get file paths and target directory
    file_paths = request.POST.getlist('file_paths[]')

    # Check for file paths in the request body
    # The checkboxes are included with hx-include but might be named differently
    for key, values in request.POST.lists():
        if key != 'file_paths[]' and key != 'csrfmiddlewaretoken' and key != 'target_directory':
            logger.info(f"Found potential file paths with key: {key}, values: {values}")
            file_paths.extend(values)

    target_directory = request.POST.get('target_directory', '')

    logger.info(f"file_paths after processing: {file_paths}")
    logger.info(f"target_directory: {target_directory}")
    logger.info(f"All POST data: {request.POST}")

    if not file_paths:
        logger.error("No file paths provided")
        if request.headers.get('HX-Request'):
            return HttpResponse("File paths are required", status=400)
        messages.error(request, "File paths are required.")
        return redirect(request.META.get('HTTP_REFERER'))

    if target_directory is None:  # Check separately to provide more specific error messages
        logger.error("Target directory is None")
        if request.headers.get('HX-Request'):
            return HttpResponse("Target directory is required", status=400)
        messages.error(request, "Target directory is required.")
        return redirect(request.META.get('HTTP_REFERER'))

    # Get user ID for storage paths
    user_id = str(request.user.id)

    # Create a PathManager instance for the current user
    path_manager = PathManager(user_id=user_id)

    # Check if target directory exists using PathManager
    if target_directory:
        try:
            # Use PathManager to check if directory exists
            if not path_manager.directory_exists(target_directory):
                if request.headers.get('HX-Request'):
                    return HttpResponse("Target directory not found", status=404)
                messages.error(request, "Target directory not found.")
                return redirect(request.META.get('HTTP_REFERER'))
        except Exception as e:
            logger.error(f"Error checking if target directory exists: {str(e)}")
            if request.headers.get('HX-Request'):
                return HttpResponse(f"Error checking target directory: {str(e)}", status=500)
            messages.error(request, f"Error checking target directory: {str(e)}")
            return redirect(request.META.get('HTTP_REFERER'))

    # Log the target directory for debugging
    logger.info(f"Moving files to target directory: {target_directory if target_directory else 'Home'}")

    moved_files = []
    errors = []

    for path in file_paths:
        try:
            # Clean up the file path
            path = path.replace('%slash%', '/')

            # Check if file exists using PathManager's secure_storage
            if not path_manager.secure_storage.exists(path):
                errors.append({'path': path, 'error': 'File not found'})
                continue

            # Get the filename
            filename = os.path.basename(path)

            # Create the target path
            if target_directory:
                target_path = f"{target_directory}/{filename}"
            else:
                target_path = filename

            # Check if a file with the same name already exists in the target directory
            full_target_path = path_manager._get_full_path(target_path)
            if path_manager.secure_storage.exists(full_target_path):
                # Add timestamp to filename to make it unique
                name, ext = os.path.splitext(filename)
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                filename = f"{name}_{timestamp}{ext}"

                # Update target path with new filename
                if target_directory:
                    target_path = f"{target_directory}/{filename}"
                else:
                    target_path = filename
                full_target_path = path_manager._get_full_path(target_path)

            # Move the file using PathManager
            path_manager.move_file(path, target_path)

            # Log the move operation
            logger.info(f"Moved file from {path} to {full_target_path}")

            # Update file info in database
            file_info = FileInfo.objects.filter(path=path).first()
            if file_info:
                file_info.path = full_target_path
                file_info.save()

            moved_files.append({
                'old_path': path,
                'new_path': full_target_path,
                'filename': filename
            })
        except Exception as e:
            errors.append({'path': path, 'error': str(e)})

    # Handle htmx request
    if request.headers.get('HX-Request'):
        context = {
            'moved_files': moved_files,
            'errors': errors,
            'target_directory': target_directory
        }
        return render(request, 'file_manager/components/move_result.html', context)

    # Handle regular form submission
    if errors:
        messages.error(request, f"Error moving {len(errors)} files.")
    if moved_files:
        messages.success(request, f"Successfully moved {len(moved_files)} files.")

    return redirect(request.META.get('HTTP_REFERER'))


@login_required(login_url='/accounts/login/basic-login/')
@require_http_methods(["GET"])
def get_file_tags(request):
    """Get all available tags and tags for a specific file"""
    file_path = request.GET.get('file_path', '')

    # Get all available tags
    all_tags = FileTag.objects.all().values('id', 'name', 'color')

    # Get tags for the specific file if a file path is provided
    file_tags = []
    if file_path:
        file_path = file_path.replace('%slash%', '/')
        file_info = FileInfo.objects.filter(path=file_path).first()
        if file_info:
            file_tags = file_info.tags.all().values_list('id', flat=True)

    # Render the template with the tags data
    context = {
        'all_tags': list(all_tags),
        'file_tags': list(file_tags)
    }
    return render(request, 'file_manager/components/file_tags.html', context)


@login_required(login_url='/accounts/login/basic-login/')
@require_http_methods(["GET"])
def get_file_info(request):
    """Get file information via AJAX"""
    file_path = request.GET.get('file_path', '')
    logger.info(f"get_file_info called for path: {file_path}")

    if not file_path:
        return JsonResponse({'error': 'File path is required', 'success': False}, status=400)

    # Normalize the file path
    file_path = file_path.replace('%slash%', '/')

    # Get file info
    file_info = FileInfo.objects.filter(path=file_path).first()

    if not file_info:
        logger.warning(f"File info not found for path: {file_path}")
        return JsonResponse({'error': 'File not found', 'success': False}, status=404)

    # Log the file info for debugging
    logger.info(f"File info found: {file_info.id}, is_favorite: {file_info.is_favorite}")

    # Return file info
    return JsonResponse({
        'success': True,
        'info': file_info.info,
        'is_favorite': file_info.is_favorite,
        'filename': file_info.filename,
        'file_type': file_info.file_type,
        'file_size': file_info.file_size,
        'updated_at': file_info.updated_at.isoformat() if file_info.updated_at else None
    })


def convert_csv_to_text(csv_file_path):
    with open(csv_file_path, 'r') as file:
        reader = csv.reader(file)
        rows = list(reader)

    text = ''
    for row in rows:
        text += ','.join(row) + '\n'

    return text


def get_files_from_directory(directory_path, user):
    """Get files from a directory and update the FileInfo model using PathManager"""
    files = []
    # Extract the relative path from the full directory path
    if hasattr(user, 'user'):
        # If user is a request object
        user = user.user

    user_id = str(user.id) if hasattr(user, 'id') else user

    # Create a PathManager instance for the current user
    path_manager = PathManager(user_id=user_id)

    # Handle the case where directory_path is just the user's media path
    if directory_path == os.path.join(settings.MEDIA_ROOT, user_id):
        rel_dir = ""
    else:
        # Get the relative path and normalize it
        rel_path = os.path.relpath(directory_path, os.path.join(settings.MEDIA_ROOT, user_id))
        # Replace backslashes with forward slashes if on Windows
        rel_path = rel_path.replace(os.sep, '/') if os.sep != '/' else rel_path
        # Handle the case where rel_path is '.' (current directory)
        if rel_path == '.':
            rel_dir = ""
        else:
            # Make sure the path ends with a slash for directories
            rel_dir = rel_path if rel_path.endswith('/') else f"{rel_path}/"

    # Get files in the directory using PathManager
    storage_files = []
    try:
        # List contents of the directory
        contents = path_manager.list_directory(rel_dir)

        # Filter for files only
        for item in contents:
            if item['type'] == 'file':
                storage_files.append({
                    'path': path_manager._get_full_path(item['path']),
                    'size': item['size'],
                    'last_modified': item.get('last_modified')
                })

        # Log the files found
        logger.info(f"Found {len(storage_files)} files in {rel_dir}")
        for sf in storage_files:
            logger.info(f"  - {sf['path']}")
    except Exception as e:
        logger.error(f"Error listing files from directory {rel_dir}: {str(e)}")

    # Get existing file info records
    file_info_dict = {}
    for file_info in FileInfo.objects.filter(user=user):
        file_info_dict[file_info.path] = file_info

    # Process files from storage
    for storage_file in storage_files:
        try:
            path = storage_file['path']
            filename = os.path.basename(path)
            _, extension = os.path.splitext(filename)
            file_type = extension.lower().lstrip('.')
            file_size = storage_file['size']

            # Get or create file info
            if path in file_info_dict:
                file_info = file_info_dict[path]
                # Update if needed
                if file_info.file_size != file_size:
                    file_info.file_size = file_size
                    file_info.save()
            else:
                # Create new file info record
                file_info = FileInfo.objects.create(
                    user=user,
                    path=path,
                    filename=filename,
                    file_type=file_type,
                    file_size=file_size
                )
                file_info_dict[path] = file_info

            # Prepare CSV text if needed
            csv_text = ''
            if extension.lower() == '.csv':
                try:
                    with path_manager.secure_storage._open(path) as f:
                        reader = csv.reader(f)
                        rows = list(reader)
                        csv_text = '\n'.join([','.join(row) for row in rows])
                except Exception as e:
                    logger.error(f"Error reading CSV file {path}: {str(e)}")

            # Add file to the list
            files.append({
                'file': path,
                'filename': filename,
                'file_path': path,
                'file_info': file_info,
                'csv_text': csv_text
            })
        except Exception as e:
            logger.error(f'Error processing file {storage_file["path"]}: {str(e)}')

    return files


@login_required(login_url='/accounts/login/basic-login/')
@require_http_methods(["POST"])
def save_info(request, file_path=None):
    """Save or update file information"""
    # Get the file path from the URL parameter or form data
    if file_path is None:
        file_path = request.POST.get('file_path')
        if not file_path:
            messages.error(request, 'File path is required')
            return redirect(request.META.get('HTTP_REFERER'))

    path = file_path.replace('%slash%', '/')
    logger.info(f"save_info called for path: {path}")
    logger.info(f"POST data: {request.POST}")
    logger.info(f"Headers: {request.headers}")

    if request.method == 'POST':
        # Get existing file info or create new one
        file_info, created = FileInfo.objects.get_or_create(
            path=path,
            defaults={
                'user': request.user,
                'info': request.POST.get('info', ''),
                'filename': os.path.basename(path)
            }
        )

        logger.info(f"File info {'created' if created else 'retrieved'}: {file_info.id}")

        # Update info if it exists
        if not created:
            file_info.info = request.POST.get('info', '')
            file_info.save()

        # Handle tags if provided
        tags = request.POST.getlist('tags[]')
        if tags:
            # Clear existing tags and add new ones
            file_info.tags.clear()
            for tag_name in tags:
                tag, _ = FileTag.objects.get_or_create(name=tag_name)
                file_info.tags.add(tag)

        # Handle favorite status
        # Check if the is_favorite parameter is in the POST data
        is_favorite_in_post = 'is_favorite' in request.POST
        old_favorite_status = file_info.is_favorite

        # Update the favorite status
        file_info.is_favorite = is_favorite_in_post
        file_info.save()

        # Log the favorite status change for debugging
        logger.info(f"File {file_path} favorite status changed from {old_favorite_status} to {file_info.is_favorite}")
        logger.info(f"is_favorite in POST: {is_favorite_in_post}")
        logger.info(f"POST keys: {list(request.POST.keys())}")

        # Force a database refresh to ensure the changes are saved
        file_info.refresh_from_db()

    # Handle standard form submission
    # Add a success message
    messages.success(request, 'File information saved successfully')

    # Check if this is an HTMX request
    if request.headers.get('HX-Request'):
        # Instead of trying to rebuild the file list, redirect to the current directory
        # with an HTMX header to trigger a refresh of the file grid
        response = HttpResponse("File info saved successfully")
        response['HX-Redirect'] = request.META.get('HTTP_REFERER', '/file-manager/')
        return response
    else:
        # Get the referer URL to redirect back to the same page
        referer = request.META.get('HTTP_REFERER')
        if referer:
            return redirect(referer)
        else:
            # Fallback to the file manager root
            return redirect('file_manager:file_manager')

def get_breadcrumbs(request):
    path_components = [component for component in request.path.split("/") if component]
    breadcrumbs = []
    url = ''

    for component in path_components:
        url += f'/{component}'
        if component == "file-manager":
            component = "media"

        breadcrumbs.append({'name': component, 'url': url})

    return breadcrumbs

def cleanup_keep_files(user_id):
    """Clean up .keep files that are used to create directories using PathManager"""
    try:
        # Create a PathManager instance for the current user
        path_manager = PathManager(user_id=user_id)

        # Use PathManager to clean up .keep files
        deleted_count = path_manager.cleanup_keep_files()
        logger.info(f"Cleaned up {deleted_count} .keep files for user {user_id}")
    except Exception as e:
        logger.error(f"Error cleaning up .keep files: {str(e)}")


def file_manager(request, directory=''):
    """Main file manager view with htmx support"""
    user_id = str(request.user.id)

    # URL decode the directory path
    if directory:
        try:
            from urllib.parse import unquote
            directory = unquote(directory)
            logger.info(f"URL decoded directory: {directory}")
        except Exception as e:
            logger.error(f"Error decoding directory path: {str(e)}")

    # Create user directory if it doesn't exist
    user_directory = f"{user_id}/"
    if not default_storage.exists(user_directory):
        # Use a unique name to avoid conflicts
        keep_file = f"{user_id}/.keep_{uuid.uuid4().hex[:8]}"
        default_storage.save(keep_file, ContentFile(b''))

    # Clean up .keep files periodically
    # Only do this occasionally to avoid performance impact
    # We use a simple random check to avoid doing this on every request
    if random.random() < 0.05:  # 5% chance
        cleanup_keep_files(user_id)

    # Get directory structure using the new method that works with any storage backend
    directory_structure = generate_nested_directory(user_id)
    selected_directory = directory

    # Log the selected directory and directory structure
    logger.info(f"Selected directory: {selected_directory}")
    logger.info(f"Directory structure: {directory_structure}")

    # Get nested folders for the current directory
    nested_folders = []

    # Create a PathManager instance for the current user
    path_manager = PathManager(user_id=user_id)

    # Determine the current directory path
    current_dir = selected_directory if selected_directory else ""

    logger.info(f"Getting nested folders for current directory: {current_dir}")

    # Use PathManager to list directories
    try:
        # List contents of the current directory
        contents = path_manager.list_directory(current_dir)

        # Filter for directories only and convert to the format expected by the template
        for item in contents:
            if item['type'] == 'directory':
                nested_folders.append({
                    'name': item['name'],
                    'path': item['path']
                })

        logger.info(f"Found {len(nested_folders)} nested folders: {nested_folders}")
    except Exception as e:
        logger.error(f"Error listing directories: {str(e)}")

    # Get files in the selected directory
    files = []
    # Create the full path for the selected directory
    if selected_directory:
        # Make sure the directory path is properly formatted
        selected_directory_path = os.path.join(settings.MEDIA_ROOT, user_id, selected_directory)
    else:
        # Use the user's root directory
        selected_directory_path = os.path.join(settings.MEDIA_ROOT, user_id)

    # Get files using the updated function that uses default_storage
    files = get_files_from_directory(selected_directory_path, request.user)

    # Get breadcrumbs for navigation
    breadcrumbs = get_breadcrumbs(request)

    # Get available tags for filtering
    tags = FileTag.objects.all()

    # Handle search query
    search_query = request.GET.get('search', '')
    if search_query and len(files) > 0:
        filtered_files = []
        for file in files:
            if search_query.lower() in file['filename'].lower():
                filtered_files.append(file)
        files = filtered_files

    # Handle file type filter
    file_type_filter = request.GET.get('file_type', '')
    if file_type_filter and len(files) > 0:
        filtered_files = []
        for file in files:
            if file['file_info'].file_type == file_type_filter:
                filtered_files.append(file)
        files = filtered_files

    # Handle tag filter
    tag_filter = request.GET.get('tag', '')
    if tag_filter and len(files) > 0:
        filtered_files = []
        for file in files:
            if file['file_info'].tags.filter(name=tag_filter).exists():
                filtered_files.append(file)
        files = filtered_files

    # Handle sorting
    sort_by = request.GET.get('sort', 'name')
    sort_direction = request.GET.get('direction', 'asc')

    # Handle view mode
    view_mode = request.GET.get('view_mode', 'list')

    if sort_by == 'name':
        files = sorted(files, key=lambda x: x['filename'].lower(), reverse=(sort_direction == 'desc'))
    elif sort_by == 'size':
        files = sorted(files, key=lambda x: x['file_info'].file_size, reverse=(sort_direction == 'desc'))
    elif sort_by == 'type':
        files = sorted(files, key=lambda x: x['file_info'].file_type.lower(), reverse=(sort_direction == 'desc'))
    elif sort_by == 'date':
        files = sorted(files, key=lambda x: x['file_info'].updated_at, reverse=(sort_direction == 'desc'))

    # Prepare context
    context = {
        'directories': directory_structure,  # Use the directory structure from generate_nested_directory
        'nested_folders': nested_folders,  # Add nested folders to the context
        'files': files,
        'selected_directory': selected_directory,
        'segment': 'file_manager',
        'parent': 'apps',
        'breadcrumbs': breadcrumbs,
        'user_id': str(request.user.id),
        'tags': tags,
        'search_query': search_query,
        'file_type_filter': file_type_filter,
        'tag_filter': tag_filter,
        'sort_by': sort_by,
        'sort_direction': sort_direction,
        'view_mode': view_mode,
    }

    # Debug logging
    logger.info(f"Context for file_manager: files={len(files)}, nested_folders={len(nested_folders)}, view_mode={view_mode}")

    # Log the context being passed to the template
    logger.info(f"Directories passed to template: {directory_structure}")

    # Handle htmx requests for partial updates
    if request.headers.get('HX-Request') or request.GET.get('component'):
        component = request.GET.get('component')
        logger.info(f"HTMX request for component: {component}")

        if component == 'file-list':
            return render(request, 'file_manager/components/file_list.html', context)
        elif component == 'file-grid':
            return render(request, 'file_manager/components/file_grid.html', context)
        elif component == 'folder-tree':
            return render(request, 'file_manager/components/folder_tree.html', context)
        elif component == 'file-preview':
            # Get file path and load content for text files
            file_path = request.GET.get('file_path', '')
            file_path = file_path.replace('%slash%', '/')
            file_content = ''

            # For text files, load the content
            if file_path:
                _, extension = os.path.splitext(file_path)
                extension = extension.lower()

                if extension in ['.txt', '.md', '.csv', '.json', '.xml', '.html', '.css', '.js']:
                    try:
                        with default_storage.open(file_path) as f:
                            file_content = f.read().decode('utf-8')
                    except Exception as e:
                        logger.error(f"Error reading file {file_path}: {str(e)}")
                        file_content = f"Error reading file: {str(e)}"

            preview_context = {
                'file_path': file_path,
                'filename': os.path.basename(file_path) if file_path else '',
                'file_content': file_content
            }
            return render(request, 'file_manager/components/file_preview.html', preview_context)
        elif component == 'move-modal':
            # Get selected files for move operation
            file_paths = request.GET.getlist('file_paths[]')
            move_context = context.copy()
            move_context['selected_files'] = file_paths
            return render(request, 'file_manager/components/modals/move_files_modal.html', move_context)

    # Render full page for non-htmx requests
    return render(request, 'file_manager/file_manager.html', context)


def generate_nested_directory(user_id):
    """
    Generate a nested directory structure using PathManager.
    This ensures compatibility with any storage backend.

    Args:
        user_id: The user ID to get directories for

    Returns:
        A list of dictionaries representing the directory structure
    """
    try:
        # Create a PathManager instance for the current user
        path_manager = PathManager(user_id=user_id)

        # Use PathManager to get nested directory structure
        directory_structure = path_manager.get_nested_directory_structure()
        logger.info(f"Generated directory structure for user {user_id}")
        return directory_structure
    except Exception as e:
        logger.error(f"Error generating directory structure: {str(e)}")
        # Return a basic structure as fallback
        return [{
            'name': 'Home',
            'path': '',
            'directories': []
        }]

@login_required(login_url='/accounts/login/basic-login/')
@require_http_methods(["POST", "DELETE"])
def delete_file(request, file_path=None):
    """Delete a file or multiple files with htmx support"""
    # Handle multiple file deletion
    if request.method == "POST" and not file_path:
        file_paths = request.POST.getlist('file_paths[]')
        if not file_paths:
            # Try to parse JSON data for htmx requests
            try:
                data = json.loads(request.body.decode('utf-8'))
                file_paths = data.get('file_paths', [])
            except json.JSONDecodeError:
                file_paths = []

        deleted_files = []
        errors = []

        for path in file_paths:
            try:
                # Assume paths might still use %slash% encoding if passed directly from values
                path = path.replace('%slash%', '/')
                if default_storage.exists(path):
                    default_storage.delete(path)
                # Add to list of deleted files
                deleted_files.append(path)
            except Exception as e:
                errors.append({'path': path, 'error': str(e)})

        # Handle htmx request
        if request.headers.get('HX-Request'):
            # Instead of rendering a template, redirect back to the file manager
            # with an HTMX header to trigger a refresh of the file grid
            response = HttpResponse("Files deleted successfully")
            response['HX-Redirect'] = request.META.get('HTTP_REFERER', '/file-manager/')
            return response

        # Handle regular form submission
        if errors:
            messages.error(request, f"Error deleting {len(errors)} files.")
        if deleted_files:
            messages.success(request, f"Successfully deleted {len(deleted_files)} files.")

        return redirect(request.META.get('HTTP_REFERER'))

    # Handle single file deletion
    elif file_path:
        try:
            path = file_path.replace('%slash%', '/')

            # Delete the file from storage
            if default_storage.exists(path):
                default_storage.delete(path)

                # Delete the file info from database
                FileInfo.objects.filter(path=path).delete()

                if request.headers.get('HX-Request'):
                    # Instead of returning an empty response, redirect back to the file manager
                    # with an HTMX header to trigger a refresh of the file grid
                    response = HttpResponse("File deleted successfully")
                    response['HX-Redirect'] = request.META.get('HTTP_REFERER', '/file-manager/')
                    return response

                messages.success(request, "File deleted successfully.")
            else:
                if request.headers.get('HX-Request'):
                    # Return a more user-friendly error message
                    response = HttpResponse("File not found")
                    response['HX-Redirect'] = request.META.get('HTTP_REFERER', '/file-manager/')
                    return response

                messages.error(request, "File not found.")
        except Exception as e:
            if request.headers.get('HX-Request'):
                # Return a more user-friendly error message
                response = HttpResponse(f"Error deleting file: {str(e)}")
                response['HX-Redirect'] = request.META.get('HTTP_REFERER', '/file-manager/')
                return response

            messages.error(request, f"Error deleting file: {str(e)}")

    return redirect(request.META.get('HTTP_REFERER'))

@login_required(login_url='/accounts/login/basic-login/')
def download_file(request, file_path=None):
    """Download a single file or multiple files as a zip archive using PathManager"""
    # Create a PathManager instance for the current user
    user_id = str(request.user.id)
    path_manager = PathManager(user_id=user_id)

    # Handle multiple file download as zip
    if request.method == "POST" and not file_path:
        file_paths = request.POST.getlist('file_paths[]')
        if not file_paths:
            # Try to parse JSON data for htmx requests
            try:
                data = json.loads(request.body.decode('utf-8'))
                file_paths = data.get('file_paths', [])
            except json.JSONDecodeError:
                file_paths = []

        if not file_paths:
            if request.headers.get('HX-Request'):
                return HttpResponse("No files selected", status=400)
            messages.error(request, "No files selected for download.")
            return redirect(request.META.get('HTTP_REFERER'))

        # Create a zip file in memory
        import io
        import zipfile

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for path in file_paths:
                path = path.replace('%slash%', '/')
                if path_manager.secure_storage.exists(path):
                    # Get file content using PathManager
                    file_content = path_manager.get_file(path)
                    if file_content:
                        # Add file to zip with just the filename (not the full path)
                        zip_file.writestr(os.path.basename(path), file_content)

        # Prepare response with zip file
        zip_buffer.seek(0)
        response = HttpResponse(zip_buffer.read(), content_type='application/zip')
        response['Content-Disposition'] = 'attachment; filename=files.zip'
        return response

    # Handle single file download
    elif file_path:
        path = file_path.replace('%slash%', '/')

        if path_manager.secure_storage.exists(path):
            # Determine content type based on file extension
            content_type, _ = mimetypes.guess_type(path)
            if not content_type:
                content_type = 'application/octet-stream'  # Default content type

            # Get file from storage using PathManager
            file = path_manager.secure_storage._open(path)
            response = FileResponse(file, content_type=content_type)

            # Determine if file should be displayed inline or downloaded
            filename = os.path.basename(path)
            disposition = 'inline'

            # Force download for certain file types
            if content_type not in ['image/jpeg', 'image/png', 'image/gif', 'application/pdf', 'text/plain']:
                disposition = 'attachment'

            response['Content-Disposition'] = f'{disposition}; filename="{filename}"'
            return response

        # File not found
        if request.headers.get('HX-Request'):
            return HttpResponse("File not found", status=404)
        raise Http404("File not found")

@login_required(login_url='/accounts/login/basic-login/')
@require_http_methods(["POST"])
def upload_file(request):
    """Handle file uploads with htmx support for progress updates using PathManager"""
    # Get user ID for storage paths
    user_id = str(request.user.id)

    # Create a PathManager instance for the current user
    path_manager = PathManager(user_id=user_id)

    # Get the selected directory from the request
    selected_directory = request.POST.get('directory', '')

    # Create the selected directory if it doesn't exist
    if selected_directory:
        path_manager.create_directory(selected_directory)

    # Process uploaded files
    uploaded_files = []
    errors = []

    # Handle multiple files
    files = request.FILES.getlist('files') if 'files' in request.FILES else [request.FILES.get('file')]

    for file in files:
        if file:
            try:
                # Generate safe filename to prevent path traversal
                safe_filename = os.path.basename(file.name)

                # Construct the target path
                target_path = os.path.join(selected_directory, safe_filename) if selected_directory else safe_filename

                # Check if file already exists
                full_path = path_manager._get_full_path(target_path)
                if path_manager.secure_storage.exists(full_path):
                    # Add timestamp to filename to make it unique
                    name, ext = os.path.splitext(safe_filename)
                    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                    safe_filename = f"{name}_{timestamp}{ext}"
                    target_path = os.path.join(selected_directory, safe_filename) if selected_directory else safe_filename
                    full_path = path_manager._get_full_path(target_path)

                # Save the file using PathManager
                path_manager.save_file(file, target_path)

                # Get file info
                file_size = file.size
                file_type = os.path.splitext(safe_filename)[1].lower().lstrip('.')

                # Create or update file info in database
                file_info, created = FileInfo.objects.get_or_create(
                    path=full_path,
                    defaults={
                        'user': request.user,
                        'filename': safe_filename,
                        'file_type': file_type,
                        'file_size': file_size
                    }
                )

                if not created:
                    file_info.file_size = file_size
                    file_info.save()

                uploaded_files.append({
                    'name': safe_filename,
                    'size': file_size,
                    'type': file_type,
                    'path': full_path
                })

            except Exception as e:
                errors.append({
                    'name': file.name,
                    'error': str(e)
                })

    # Prepare context
    context = {
        'uploaded_files': uploaded_files,
        'errors': errors,
        'selected_directory': selected_directory
    }

    # Log the upload results
    logger.info(f"Upload results: {len(uploaded_files)} files uploaded, {len(errors)} errors")
    logger.info(f"Selected directory: {selected_directory}")

    # Handle htmx request
    if request.headers.get('HX-Request'):
        response = render(request, 'file_manager/components/upload_result.html', context)
        # Add HX-Redirect header to force a full page reload if needed
        response['HX-Redirect'] = request.META.get('HTTP_REFERER') or reverse('file_manager:file_manager', args=[selected_directory])
        return response

    # Handle regular form submission
    if errors:
        messages.error(request, f"Error uploading {len(errors)} files.")
    if uploaded_files:
        messages.success(request, f"Successfully uploaded {len(uploaded_files)} files.")

    # Redirect to the file manager with the current directory
    return redirect('file_manager:file_manager', directory=selected_directory)

@login_required(login_url='/accounts/login/basic-login/')
@require_http_methods(["POST"])
def delete_files(request):
    """Delete multiple files based on POST data and return updated file list via HTMX."""
    file_paths = request.POST.getlist('file_paths[]')
    user = request.user
    user_id = str(user.id)
    deleted_count = 0
    errors = []

    if not file_paths:
        messages.error(request, "No files selected for deletion.")
        # Return an empty response or appropriate error for HTMX
        return HttpResponse("<p class='text-danger'>No files selected.</p>", status=400)

    # Create a PathManager instance for the current user
    path_manager = PathManager(user_id=user_id)

    # Clean up file paths
    cleaned_paths = [path.replace('%slash%', '/') for path in file_paths]

    # Use PathManager to batch delete files
    try:
        # Delete files in batch
        deleted_count = path_manager.batch_delete(cleaned_paths)
        logger.info(f"Batch deleted {deleted_count} files for user {user_id}")

        # Delete FileInfo records for the deleted files
        FileInfo.objects.filter(user=user, path__in=cleaned_paths).delete()
    except Exception as e:
        logger.error(f"Error batch deleting files: {str(e)}")
        errors.append(f"Error deleting files: {str(e)}")

    if errors:
        messages.error(request, " \n".join(errors))
    elif deleted_count > 0:
        messages.success(request, f"Successfully deleted {deleted_count} file(s).")

    # Trigger a full page refresh using HTMX header
    response = HttpResponse(status=200) # Content doesn't matter
    response['HX-Refresh'] = 'true'
    return response