import json
import os
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.conf import settings
from ..models import Client
from ..sitemap_extractor import extract_sitemap_and_meta_tags, extract_sitemap_and_meta_tags_from_url

def get_snapshot_stats(file_path):
    """Get statistics from a meta tags snapshot file"""
    try:
        if not os.path.exists(file_path):
            return {
                'total_pages': 0,
                'total_tags': 0,
                'issues': 0
            }

        # Check file extension
        if file_path.endswith('.csv'):
            import csv
            total_pages = 0
            total_tags = 0
            issues = 0
            
            with open(file_path, 'r') as f:
                csv_reader = csv.DictReader(f)
                for row in csv_reader:
                    total_pages += 1
                    # Assuming meta tags are comma-separated in a column
                    if 'meta_tags' in row:
                        tags = row['meta_tags'].split(',')
                        total_tags += len(tags)
                    # Count issues if there's an issues column
                    if 'issues' in row and row['issues']:
                        issues += 1
                        
            return {
                'total_pages': total_pages,
                'total_tags': total_tags,
                'issues': issues
            }
        else:
            # Handle JSON files as before
            with open(file_path, 'r') as f:
                data = json.load(f)
                total_pages = len(data.get('pages', []))
                total_tags = sum(len(page.get('meta_tags', [])) for page in data.get('pages', []))
                issues = sum(1 for page in data.get('pages', []) 
                            for tag in page.get('meta_tags', []) 
                            if tag.get('issues'))
                return {
                    'total_pages': total_pages,
                    'total_tags': total_tags,
                    'issues': issues
                }
    except Exception as e:
        print(f"Error reading meta tags file: {file_path}")
        print(f"Error details: {str(e)}")
        return {
            'total_pages': 0,
            'total_tags': 0,
            'issues': 0
        }

@login_required
def meta_tags_dashboard(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    
    # Get list of meta tags files for this client
    meta_tags_dir = os.path.join(settings.MEDIA_ROOT, str(request.user.id), 'meta-tags')
    meta_tags_files = []
    latest_stats = None
    
    if os.path.exists(meta_tags_dir):
        meta_tags_files = sorted(
            [os.path.join(str(request.user.id), 'meta-tags', f) 
             for f in os.listdir(meta_tags_dir) if f.endswith('.csv')],
            reverse=True
        )
        
        # Get stats for the latest snapshot
        if meta_tags_files:
            latest_file = os.path.join(settings.MEDIA_ROOT, meta_tags_files[0])
            latest_stats = get_snapshot_stats(latest_file)

    context = {
        'page_title': 'Meta Tags Dashboard',
        'client': client,
        'meta_tags_files': meta_tags_files,
        'latest_stats': latest_stats
    }
    
    return render(request, 'seo_manager/meta_tags/meta_tags_dashboard.html', context)

@login_required
def create_meta_tags_snapshot(request, client_id):
    if request.method == 'POST':
        client = get_object_or_404(Client, id=client_id)
        try:
            file_path = extract_sitemap_and_meta_tags(client, request.user)
            print(f"File being saved at: {file_path}")
            
            # Ensure the directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            return JsonResponse({
                'success': True,
                'message': f"Meta tags snapshot created successfully. File saved as {os.path.basename(file_path)}"
            })
        except Exception as e:
            import traceback
            print(traceback.format_exc())  # This will help debug any errors
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
