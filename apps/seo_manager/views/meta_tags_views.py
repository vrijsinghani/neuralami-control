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
from ..tasks import extract_sitemap_task, extract_sitemap_from_url_task
import logging
from datetime import datetime
import time
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from celery.result import AsyncResult

logger = logging.getLogger(__name__)
User = get_user_model()

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
                    # Count non-empty meta tag fields from our known meta tag columns
                    meta_tag_fields = ['meta_description', 'meta_charset', 'viewport', 
                                      'robots', 'canonical', 'og_title', 'og_description', 'og_image', 
                                      'twitter_card', 'twitter_title', 'twitter_description', 
                                      'twitter_image', 'author']
                    
                    for field in meta_tag_fields:
                        if field in row and row[field]:
                            total_tags += 1
                    
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
def meta_tags(request, client_id):
    """Meta tags dashboard view for specified client"""
    try:
        client = Client.objects.get(id=client_id)
        # Verify the user has access to this client (could be based on group permissions)
        # This is a simplified check - you may need more comprehensive permission logic
    except Client.DoesNotExist:
        messages.error(request, "Client not found.")
        return redirect('seo_clients')
        
    # Define the relative path for meta tags
    meta_tags_prefix = f"{request.user.id}/meta-tags/"
    meta_tags_files = []
    latest_stats = None
    
    # Get list of meta tags files for this client from storage
    try:
        # Different storage backends have different listing methods
        if hasattr(default_storage, 'listdir'):
            # For traditional storage backends
            _, file_names = default_storage.listdir(meta_tags_prefix)
            for filename in file_names:
                if filename.endswith('.csv') and client.name.lower().replace(' ', '_') in filename:
                    file_path = os.path.join(meta_tags_prefix, filename)
                    meta_tags_files.append(filename)
                    
                    # Try to extract statistics from the latest file
                    if not latest_stats and len(meta_tags_files) == 1:
                        try:
                            latest_stats = get_snapshot_stats(file_path)
                            logger.info(f"Extracted stats for {file_path}: {latest_stats}")
                        except Exception as e:
                            logger.error(f"Error extracting stats from meta tags file: {e}")
        
        elif hasattr(default_storage, 'bucket'):
            # For S3-like storage
            for obj in default_storage.bucket.objects.filter(Prefix=meta_tags_prefix):
                filename = os.path.basename(obj.key)
                if filename.endswith('.csv') and client.name.lower().replace(' ', '_') in filename:
                    meta_tags_files.append(filename)
                    
                    # Try to extract statistics from the latest file
                    if not latest_stats and len(meta_tags_files) == 1:
                        try:
                            latest_stats = get_snapshot_stats(obj.key)
                            logger.info(f"Extracted stats for {obj.key}: {latest_stats}")
                        except Exception as e:
                            logger.error(f"Error extracting stats from meta tags file: {e}")
    except Exception as e:
        logger.error(f"Error listing meta tags files: {e}")
    
    # Sort files by date (newest first)
    meta_tags_files.sort(reverse=True)
    
    context = {
        'client': client,
        'meta_tags_files': meta_tags_files,
        'latest_stats': latest_stats,
    }
    
    # Check if task_id is in the request parameters
    task_id = request.GET.get('task_id')
    if task_id:
        context['task_id'] = task_id
    
    return render(request, 'seo_manager/meta_tags/meta_tags_dashboard.html', context)

@login_required
@csrf_exempt
def create_snapshot(request, client_id):
    """Create a new meta tags snapshot from client's website"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)
    
    try:
        client = Client.objects.get(id=client_id)
        # Verify the user has access to this client (could be based on group permissions)
        # This is a simplified check - you may need more comprehensive permission logic
        # Additional permission check could be added here if needed
    except Client.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Client not found'}, status=404)
    
    website_url = client.website_url  # Fixed property name from website to website_url
    if not website_url:
        return JsonResponse({'success': False, 'message': 'Client has no website URL defined'}, status=400)
    
    # Set up file path using storage-compatible path handling
    user_id = request.user.id
    
    # File name format: client_name_YYYY-MM-DD_HH-MM-SS.csv
    timestamp = timezone.now().strftime('%Y-%m-%d_%H-%M-%S')
    filename = f"{client.name.lower().replace(' ', '_')}_{timestamp}.csv"
    relative_path = f"{user_id}/meta-tags/{filename}"
    
    try:
        # Enqueue the Celery task
        task = extract_sitemap_task.delay(
            website_url=website_url,
            output_file=relative_path,
            user_id=user_id
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Meta tags extraction started',
            'task_id': task.id
        })
    except Exception as e:
        logger.error(f"Error starting meta tags extraction: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error starting extraction: {str(e)}'
        }, status=500)

@login_required
@csrf_exempt
def create_snapshot_from_url(request):
    """Create a new meta tags snapshot from a user-provided URL"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        website_url = data.get('url')
        
        if not website_url:
            return JsonResponse({'success': False, 'message': 'No URL provided'}, status=400)
        
        # Set up file path using storage-compatible path handling
        user_id = request.user.id
        
        # Extract domain from URL for the filename
        import re
        domain = re.sub(r'^https?://', '', website_url)
        domain = re.sub(r'/.*$', '', domain)  # Remove path
        
        # File name format: domain_YYYY-MM-DD_HH-MM-SS.csv
        timestamp = timezone.now().strftime('%Y-%m-%d_%H-%M-%S')
        filename = f"{domain.replace('.', '_')}_{timestamp}.csv"
        relative_path = f"{user_id}/meta-tags/{filename}"
        
        # Enqueue the Celery task
        task = extract_sitemap_from_url_task.delay(
            website_url=website_url,
            output_file=relative_path,
            user_id=user_id
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Meta tags extraction started',
            'task_id': task.id
        })
    except Exception as e:
        logger.error(f"Error starting meta tags extraction from URL: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Error starting extraction: {str(e)}'
        }, status=500)

@login_required
def check_task_status(request, task_id):
    """Check the status of a meta tags extraction task"""
    try:
        # Get the task result
        task_result = AsyncResult(task_id)
        
        # Check task status
        if task_result.ready():
            if task_result.successful():
                return JsonResponse({
                    'success': True,
                    'status': 'complete',
                    'result': task_result.result
                })
            else:
                # Task failed
                error = str(task_result.result) if task_result.result else "Unknown error"
                return JsonResponse({
                    'success': False,
                    'status': 'failed',
                    'message': error
                })
        else:
            # Task still in progress
            return JsonResponse({
                'success': True,
                'status': 'pending',
                'state': task_result.state
            })
    
    except Exception as e:
        logger.error(f"Error checking task status: {e}")
        return JsonResponse({
            'success': False,
            'status': 'error',
            'message': str(e)
        }, status=500)
