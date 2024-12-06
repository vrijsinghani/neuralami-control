import json
import os
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.conf import settings
from ..models import Client
from ..sitemap_extractor import extract_sitemap_and_meta_tags, extract_sitemap_and_meta_tags_from_url

@login_required
def create_meta_tags_snapshot(request, client_id):
    if request.method == 'POST':
        client = get_object_or_404(Client, id=client_id)
        try:
            file_path = extract_sitemap_and_meta_tags(client, request.user)
            
            # Ensure the directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            return JsonResponse({
                'success': True,
                'message': f"Meta tags snapshot created successfully. File saved as {os.path.basename(file_path)}"
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f"An error occurred while creating the snapshot: {str(e)}"
            })
    else:
        return JsonResponse({
            'success': False,
            'message': "Invalid request method."
        })

@login_required
@require_http_methods(["POST"])
def create_meta_tags_snapshot_url(request):
    data = json.loads(request.body)
    url = data.get('url')
    if not url:
        return JsonResponse({
            'success': False,
            'message': "URL is required."
        })
    
    try:
        file_path = extract_sitemap_and_meta_tags_from_url(url, request.user)
        return JsonResponse({
            'success': True,
            'message': f"Meta tags snapshot created successfully. File saved as {os.path.basename(file_path)}"
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f"An error occurred while creating the snapshot: {str(e)}"
        })
