import os
import csv
import uuid
import zipfile
import tempfile
from django.shortcuts import render, redirect
from django.http import HttpResponse, Http404
from django.conf import settings
from .models import *
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from urllib.parse import unquote

def convert_csv_to_text(csv_file_path):
    with open(csv_file_path, 'r') as file:
        reader = csv.reader(file)
        rows = list(reader)

    text = ''
    for row in rows:
        text += ','.join(row) + '\n'

    return text

def get_directory_contents(directory_path, user_id):
    contents = []
    if not os.path.exists(directory_path):
        return contents
    
    for name in os.listdir(directory_path):
        path = os.path.join(directory_path, name)
        rel_path = os.path.relpath(path, os.path.join(settings.MEDIA_ROOT, user_id))
        if os.path.isdir(path):
            contents.append({
                'name': name,
                'type': 'directory',
                'path': rel_path
            })
        else:
            _, extension = os.path.splitext(name)
            contents.append({
                'name': name,
                'size' : get_file_size(path),
                'type': 'file',
                'path': rel_path,
                'extension': extension[1:].lower()  # Remove the dot and convert to lowercase
            })

    return sorted(contents, key=lambda x: (x['type'] == 'file', x['name'].lower()))

@login_required(login_url='/accounts/login/basic-login/')
def save_info(request, file_path):
    path = unquote(file_path)
    if request.method == 'POST':
        FileInfo.objects.update_or_create(
            path=path,
            defaults={
                'info': request.POST.get('info')
            }
        )
    
    return redirect(request.META.get('HTTP_REFERER'))

def get_breadcrumbs(request):
    path_components = [unquote(component) for component in request.path.split("/") if component]
    breadcrumbs = []
    url = ''

    for component in path_components:
        url += f'/{component}'
        if component == "file-manager":
            component = "media"

        breadcrumbs.append({'name': component, 'url': url})

    return breadcrumbs

def generate_nested_directory(root_path, current_path):
    directory = {}
    for name in os.listdir(current_path):
        path = os.path.join(current_path, name)
        rel_path = os.path.relpath(path, root_path)
        if os.path.isdir(path):
            directory[rel_path] = {
                'type': 'directory',
                'contents': generate_nested_directory(root_path, path)
            }
        else:
            directory[rel_path] = {
                'type': 'file'
            }
    return directory

@login_required(login_url='/accounts/login/illustration-login/')
def file_manager(request, directory=''):
    user_id = str(request.user.id)
    media_path = os.path.join(settings.MEDIA_ROOT, user_id)

    if not os.path.exists(media_path):
        os.makedirs(media_path)
        
    directory_structure = generate_nested_directory(media_path, media_path)
    
    selected_directory_path = os.path.join(media_path, unquote(directory))
    contents = get_directory_contents(selected_directory_path, user_id)

    breadcrumbs = get_breadcrumbs(request)

    context = {
        'page_title': 'File Manager',
        'directory': directory_structure, 
        'contents': contents,
        'selected_directory': directory,
        'segment': 'file_manager',
        'parent': 'apps',
        'breadcrumbs': breadcrumbs,
        'user_id': user_id,
    }
    return render(request, 'pages/apps/file-manager.html', context)

@login_required(login_url='/accounts/login/basic-login/')
def delete_file(request, file_path):
    user_id = str(request.user.id)
    path = unquote(file_path)
    absolute_file_path = os.path.join(settings.MEDIA_ROOT, user_id, path)
    if os.path.exists(absolute_file_path):
        if os.path.isdir(absolute_file_path):
            import shutil
            shutil.rmtree(absolute_file_path)
        else:
            os.remove(absolute_file_path)
        print("File/Directory deleted", absolute_file_path)
    return redirect(request.META.get('HTTP_REFERER'))

@login_required(login_url='/accounts/login/basic-login/')
def download_file(request, file_path):
    user_id = str(request.user.id)
    path = unquote(file_path)
    absolute_file_path = os.path.join(settings.MEDIA_ROOT, user_id, path)
    if os.path.exists(absolute_file_path):
        if os.path.isdir(absolute_file_path):
            # Create a temporary zip file
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                with zipfile.ZipFile(temp_file, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    for root, dirs, files in os.walk(absolute_file_path):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, absolute_file_path)
                            zip_file.write(file_path, arcname)

            # Read the temporary file and create the response
            with open(temp_file.name, 'rb') as f:
                response = HttpResponse(f.read(), content_type='application/zip')
                response['Content-Disposition'] = f'attachment; filename="{os.path.basename(absolute_file_path)}.zip"'

            # Delete the temporary file
            os.unlink(temp_file.name)

            return response
        else:
            with open(absolute_file_path, 'rb') as fh:
                response = HttpResponse(fh.read(), content_type="application/octet-stream")
                response['Content-Disposition'] = 'attachment; filename=' + os.path.basename(absolute_file_path)
                return response
    raise Http404

@login_required(login_url='/accounts/login/basic-login/')
def upload_file(request):
    user_id = str(request.user.id)
    media_user_path = os.path.join(settings.MEDIA_ROOT, user_id)

    if not os.path.exists(media_user_path):
        os.makedirs(media_user_path)

    selected_directory = unquote(request.POST.get('directory', ''))
    selected_directory_path = os.path.join(media_user_path, selected_directory)

    if not os.path.exists(selected_directory_path):
        os.makedirs(selected_directory_path)

    if request.method == 'POST':
        file = request.FILES.get('file')
        file_path = os.path.join(selected_directory_path, file.name)

        with open(file_path, 'wb') as destination:
            for chunk in file.chunks():
                destination.write(chunk)

    return redirect(request.META.get('HTTP_REFERER'))

def get_file_size(file_path):
    try:
        return os.path.getsize(file_path)
    except OSError:
        return 0  # Return 0 if there's an error reading the file size
