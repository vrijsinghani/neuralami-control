import json
import os
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from ..models import Client
from ..sitemap_extractor import extract_sitemap_and_meta_tags, extract_sitemap_and_meta_tags_from_url
import logging

logger = logging.getLogger(__name__)

def get_snapshot_stats(file_path: str) -> dict:
    """
    Get statistics from a meta tags snapshot file in cloud storage.
    
    Args:
        file_path: The relative path to the file
        
    Returns:
        dict: Statistics about the meta tags
    """
    try:
        if not default_storage.exists(file_path):
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
            
            with default_storage.open(file_path, 'r') as f:
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
            # Handle JSON files
            with default_storage.open(file_path, 'r') as f:
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
        logger.error(f"Error reading meta tags file: {file_path} - {str(e)}")
        return {
            'total_pages': 0,
            'total_tags': 0,
            'issues': 0
        }

@login_required
def meta_tags_dashboard(request, client_id):
    """Meta tags dashboard view."""
    try:
        client = get_object_or_404(Client, id=client_id)
        
        # Get list of meta tags files for this client
        meta_tags_files = []
        latest_stats = None
        
        # List files in cloud storage
        prefix = os.path.join(str(request.user.id), 'meta-tags')
        
        if hasattr(default_storage, 'listdir'):
            # For traditional storage backends
            _, files = default_storage.listdir(prefix)
            meta_tags_files = sorted(
                [os.path.join(prefix, f) for f in files if f.endswith('.csv')],
                key=lambda x: default_storage.get_modified_time(x),
                reverse=True
            )
        else:
            # For S3-like storage
            objects = default_storage.bucket.objects.filter(Prefix=prefix)
            meta_tags_files = sorted(
                [obj.key for obj in objects if obj.key.endswith('.csv')],
                key=lambda x: default_storage.get_modified_time(x),
                reverse=True
            )
        
        # Get stats for the latest snapshot
        if meta_tags_files:
            latest_stats = get_snapshot_stats(meta_tags_files[0])

        context = {
            'page_title': 'Meta Tags Dashboard',
            'client': client,
            'meta_tags_files': meta_tags_files,
            'latest_stats': latest_stats
        }
        
        return render(request, 'seo_manager/meta_tags/meta_tags_dashboard.html', context)
        
    except Exception as e:
        logger.error(f"Error in meta_tags_dashboard: {str(e)}")
        raise

@login_required
def create_meta_tags_snapshot(request, client_id):
    """Create a new meta tags snapshot."""
    if request.method == 'POST':
        try:
            client = get_object_or_404(Client, id=client_id)
            file_path = extract_sitemap_and_meta_tags(client, request.user)
            
            logger.info(f"Meta tags snapshot created: {file_path}")
            
            return JsonResponse({
                'success': True,
                'message': f"Meta tags snapshot created successfully. File saved as {os.path.basename(file_path)}"
            })
        except Exception as e:
            logger.error(f"Error creating meta tags snapshot: {str(e)}")
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
    """Create a meta tags snapshot from a URL."""
    try:
        data = json.loads(request.body)
        url = data.get('url')
        
        if not url:
            return JsonResponse({
                'success': False,
                'message': "URL is required."
            })
        
        file_path = extract_sitemap_and_meta_tags_from_url(url, request.user)
        
        logger.info(f"Meta tags snapshot created from URL: {file_path}")
        
        return JsonResponse({
            'success': True,
            'message': f"Meta tags snapshot created successfully. File saved as {os.path.basename(file_path)}"
        })
    except Exception as e:
        logger.error(f"Error creating meta tags snapshot from URL: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': f"An error occurred while creating the snapshot: {str(e)}"
        })
