import json
import os
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.core.files.base import ContentFile
from ..models import Client
from ..sitemap_extractor import extract_sitemap_and_meta_tags, extract_sitemap_and_meta_tags_from_url, meta_tag_storage
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
import io
from urllib.parse import unquote
from django.utils.html import escape

logger = logging.getLogger(__name__)
User = get_user_model()

def get_snapshot_stats(file_path: str) -> dict:
    """
    Get statistics from a meta tags snapshot file using SecureFileStorage.
    
    Args:
        file_path: The relative path to the file
        
    Returns:
        dict: Statistics about the meta tags
    """
    try:
        if not meta_tag_storage.exists(file_path):
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
            
            with meta_tag_storage._open(file_path, 'rb') as file_bytes:
                try:
                    file_content = file_bytes.read().decode('utf-8')
                except UnicodeDecodeError:
                    logger.warning(f"UTF-8 decoding failed for stats file {file_path}, trying latin-1")
                    file_bytes.seek(0)
                    file_content = file_bytes.read().decode('latin-1', errors='ignore')
                
                file_text_io = io.StringIO(file_content)
                csv_reader = csv.DictReader(file_text_io)
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
            with meta_tag_storage._open(file_path, 'rb') as file_bytes:
                try:
                    file_content = file_bytes.read().decode('utf-8')
                except UnicodeDecodeError:
                    logger.warning(f"UTF-8 decoding failed for stats file {file_path}, trying latin-1")
                    file_bytes.seek(0)
                    file_content = file_bytes.read().decode('latin-1', errors='ignore')
                
                data = json.loads(file_content)
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
    except Client.DoesNotExist:
        messages.error(request, "Client not found.")
        return redirect('seo_clients')

    meta_tags_prefix = f"{request.user.id}/meta-tags/"
    meta_tag_files_info = []
    latest_stats = None
    underlying_storage = meta_tag_storage.storage

    try:
        file_paths = []
        client_name_safe = client.name.lower().replace(' ', '_')

        # Consolidate file discovery
        if hasattr(underlying_storage, 'listdir'):
            _dirs, file_names = underlying_storage.listdir(meta_tags_prefix)
            for filename in file_names:
                if filename.endswith(('.csv', '.json')) and client_name_safe in filename:
                    file_paths.append(os.path.join(meta_tags_prefix, filename))
        elif hasattr(underlying_storage, 'bucket') and hasattr(underlying_storage.bucket, 'objects'):
            for obj in underlying_storage.bucket.objects.filter(Prefix=meta_tags_prefix):
                if not obj.key.endswith('/'):
                    filename = os.path.basename(obj.key)
                    if filename.endswith(('.csv', '.json')) and client_name_safe in filename:
                        file_paths.append(obj.key)
        else:
            logger.warning(f"Underlying storage for meta tags does not support listdir or bucket.objects.filter")

        # Sort discovered file paths by name (descending)
        file_paths.sort(reverse=True)

        # Get stats for each file
        for full_path in file_paths:
            try:
                stats = get_snapshot_stats(full_path)
                meta_tag_files_info.append({
                    'name': os.path.basename(full_path),
                    'path': full_path,
                    'stats': stats # Store the full stats dictionary
                })
                # Update latest_stats if this is the first (most recent) file
                if latest_stats is None:
                    latest_stats = stats
            except Exception as e:
                logger.error(f"Error extracting stats from meta tags file {full_path}: {e}")
                # Add placeholder if stats extraction fails for a specific file
                meta_tag_files_info.append({
                    'name': os.path.basename(full_path),
                    'path': full_path,
                    'stats': {'total_pages': 'N/A', 'total_tags': 'N/A', 'issues': 'N/A'} # Indicate unavailable stats
                })

    except Exception as e:
        logger.error(f"Error listing meta tags files: {e}", exc_info=True)
        messages.error(request, "An error occurred while listing snapshot files.")

    # Note: Sorting is now done on file_paths before fetching stats

    context = {
        'client': client,
        'meta_tags_files_info': meta_tag_files_info,
        'latest_stats': latest_stats,
    }

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

@login_required
def view_meta_tags_report(request, client_id, file_path):
    """
    Render the content of a meta tags report for HTMX.
    Handles both single file view and comparison view.
    Args:
        request: The HTTP request
        client_id: The ID of the client (added for context)
        file_path: The encoded file path to load

    Returns:
        HttpResponse with the report content rendered as HTML or an error status.
    """
    try:
        start_time = time.time()
        file_path = unquote(file_path)
        logger.info(f"[HTMX View Start] Client {client_id}: Loading report for: {file_path}")

        compare_mode = request.GET.get('compare', 'false').lower() == 'true'
        meta_tags_prefix = f"{request.user.id}/meta-tags/"
        underlying_storage = meta_tag_storage.storage

        if compare_mode:
            logger.info(f"[HTMX View] Client {client_id}: Entering comparison mode for {file_path}")
            # --- Comparison Logic ---
            meta_tag_files = []
            try:
                client = Client.objects.get(id=client_id)
                if hasattr(underlying_storage, 'listdir'):
                    _dirs, file_names = underlying_storage.listdir(meta_tags_prefix)
                    client_name_safe = client.name.lower().replace(' ', '_')
                    for filename in file_names:
                        if filename.endswith(('.csv', '.json')) and client_name_safe in filename:
                            full_path = os.path.join(meta_tags_prefix, filename)
                            meta_tag_files.append(full_path)
                # TODO: Add S3 listing logic if needed
            except Client.DoesNotExist:
                 logger.error(f"Client {client_id} not found for comparison.")
                 return HttpResponse('<div class="alert alert-danger">Client not found.</div>', status=404)
            except Exception as e:
                logger.error(f"Client {client_id}: Error listing files for comparison: {str(e)}", exc_info=True)
                return HttpResponse('<div class="alert alert-danger">Error listing files for comparison.</div>', status=500)
            
            meta_tag_files.sort(reverse=True)
            
            try:
                current_index = meta_tag_files.index(file_path)
            except ValueError:
                logger.error(f"Client {client_id}: Current file {file_path} not found in list for comparison.")
                return HttpResponse('<div class="alert alert-danger">Current file not found in list.</div>', status=404)
                
            if current_index == len(meta_tag_files) - 1:
                return HttpResponse('<div class="alert alert-info">This is the oldest snapshot, no comparison available.</div>')
                
            previous_file_path = meta_tag_files[current_index + 1]
            
            # Function to load and parse data (avoids code duplication)
            def load_and_parse(path):
                if not meta_tag_storage.exists(path):
                    logger.error(f"Client {client_id}: File not found during comparison: {path}")
                    raise FileNotFoundError(f"File not found: {os.path.basename(path)}")
                with meta_tag_storage._open(path, 'rb') as fb:
                    try:
                        content = fb.read().decode('utf-8')
                    except UnicodeDecodeError:
                        logger.warning(f"Client {client_id}: UTF-8 decode failed for {path}, trying latin-1")
                        fb.seek(0)
                        content = fb.read().decode('latin-1', errors='ignore')
                    
                    if path.endswith('.json'):
                        return json.loads(content)
                    elif path.endswith('.csv'):
                        from io import StringIO
                        import csv
                        reader = csv.DictReader(StringIO(content))
                        data = {'pages': []}
                        for row in reader:
                            url = row.get('url')
                            if url:
                                page = {'url': url, 'meta_tags': []}
                                for key, value in row.items():
                                    if key != 'url' and value:
                                        page['meta_tags'].append({'name': key, 'content': value})
                                data['pages'].append(page)
                        return data
                    else:
                         raise ValueError("Unsupported file type for comparison")

            try:
                current_data = load_and_parse(file_path)
                previous_data = load_and_parse(previous_file_path)
            except FileNotFoundError as e:
                return HttpResponse(f'<div class="alert alert-danger">{str(e)}</div>', status=404)
            except (json.JSONDecodeError, ValueError, Exception) as e:
                 logger.error(f"Client {client_id}: Error parsing file during comparison: {str(e)}", exc_info=True)
                 return HttpResponse(f'<div class="alert alert-danger">Error parsing file: {str(e)}</div>', status=500)

            # --- Comparison Logic (simplified from before, assuming structure) ---
            changes = []
            current_pages = {p.get('url'): p for p in current_data.get('pages', []) if p.get('url')} 
            previous_pages = {p.get('url'): p for p in previous_data.get('pages', []) if p.get('url')}
            
            # Added/Modified
            for url, current_page in current_pages.items():
                previous_page = previous_pages.get(url)
                if not previous_page:
                    changes.append({'page': url, 'type': 'added', 'details': 'New page added'})
                else:
                    # Compare tags
                    current_tags = {(t.get('name') or t.get('property')): t.get('content', '') 
                                    for t in current_page.get('meta_tags', []) if (t.get('name') or t.get('property'))}
                    previous_tags = {(t.get('name') or t.get('property')): t.get('content', '') 
                                     for t in previous_page.get('meta_tags', []) if (t.get('name') or t.get('property'))}
                    
                    for tag_name, current_content in current_tags.items():
                        previous_content = previous_tags.get(tag_name)
                        if previous_content is None:
                            changes.append({'page': url, 'type': 'added', 'details': f'Added tag: {tag_name}'})
                        elif previous_content != current_content:
                             changes.append({
                                 'page': url, 
                                 'type': 'modified', 
                                 'details': f'Changed {tag_name} from "{previous_content}" to "{current_content}"'
                             }) 
            # Removed
            for url in previous_pages:
                if url not in current_pages:
                    changes.append({'page': url, 'type': 'removed', 'details': 'Page removed'})

            context = {
                'changes': changes,
                'current_file': os.path.basename(file_path),
                'previous_file': os.path.basename(previous_file_path),
                'current_path': file_path,
                'previous_path': previous_file_path
            }
            logger.info(f"[HTMX View] Client {client_id}: Comparison mode finished for {file_path}. Time: {time.time() - start_time:.2f}s")
            return render(request, 'seo_manager/meta_tags/partials/meta_tags_comparison.html', context)

        else:
            # --- Single File View Logic ---
            logger.info(f"[HTMX View] Client {client_id}: Loading single file: {file_path}")
            if not meta_tag_storage.exists(file_path):
                logger.error(f"[HTMX View Error] Client {client_id}: File not found: {file_path}")
                return HttpResponse('<div class="alert alert-danger">File not found.</div>', status=404)

            logger.debug(f"[HTMX View] Client {client_id}: Reading file content for {file_path}")
            with meta_tag_storage._open(file_path, 'rb') as file_bytes:
                try:
                    file_content = file_bytes.read().decode('utf-8')
                    logger.debug(f"[HTMX View] Client {client_id}: File content read (UTF-8) for {file_path}. Length: {len(file_content)}")
                except UnicodeDecodeError:
                    logger.warning(f"[HTMX View Warning] Client {client_id}: UTF-8 decoding failed for {file_path}, trying latin-1")
                    file_bytes.seek(0)
                    file_content = file_bytes.read().decode('latin-1', errors='ignore')
                    logger.debug(f"[HTMX View] Client {client_id}: File content read (Latin-1) for {file_path}. Length: {len(file_content)}")

                try:
                    context = {
                        'file_path': file_path,
                        'file_name': os.path.basename(file_path)
                    }
                    target_template = None

                    if file_path.endswith('.json'):
                        logger.info(f"[HTMX View] Client {client_id}: Processing as JSON: {file_path}")
                        data = json.loads(file_content)
                        context['report_data'] = data
                        target_template = 'seo_manager/meta_tags/partials/meta_tags_report.html'
                        logger.debug(f"[HTMX View] Client {client_id}: JSON Parsed. Keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")

                    elif file_path.endswith('.csv'):
                        logger.info(f"[HTMX View] Client {client_id}: Processing as CSV: {file_path}")
                        from io import StringIO
                        import csv
                        reader = csv.DictReader(StringIO(file_content))
                        rows = list(reader)
                        context['rows'] = rows
                        context['headers'] = reader.fieldnames if rows else []
                        target_template = 'seo_manager/meta_tags/partials/meta_tags_csv.html'
                        logger.debug(f"[HTMX View] Client {client_id}: CSV Parsed. Rows: {len(rows)}. Headers: {context['headers']}")

                    else:
                        logger.warning(f"[HTMX View Warning] Client {client_id}: Attempting to view unsupported file type: {file_path}")
                        return HttpResponse(f'<pre class="bg-dark text-light p-3">{escape(file_content)}</pre>', content_type='text/html')

                    # Check if context seems valid before rendering
                    if target_template:
                        if (target_template.endswith('csv.html') and not context.get('rows')) or \
                           (target_template.endswith('report.html') and not context.get('report_data')):
                           logger.warning(f"[HTMX View Warning] Client {client_id}: Context data for template {target_template} appears empty. File: {file_path}")

                        logger.info(f"[HTMX View] Client {client_id}: Rendering template {target_template} for {file_path}")
                        response = render(request, target_template, context)
                        logger.info(f"[HTMX View Success] Client {client_id}: Rendered {target_template} for {file_path}. Time: {time.time() - start_time:.2f}s")
                        return response
                    else:
                        # This case should technically be handled by the 'else' above, but as a safeguard:
                         logger.error(f"[HTMX View Error] Client {client_id}: No target template determined for {file_path}")
                         return HttpResponse('<div class="alert alert-danger">Could not determine how to display this file type.</div>', status=500)

                except json.JSONDecodeError as e:
                    logger.error(f"[HTMX View Error] Client {client_id}: Error parsing JSON file: {file_path} - {str(e)}", exc_info=True)
                    return HttpResponse('<div class="alert alert-danger">Failed to parse JSON content.</div>', status=500)
                except Exception as e: # Catch potential CSV errors or others
                    logger.error(f"[HTMX View Error] Client {client_id}: Error processing file content: {file_path} - {str(e)}", exc_info=True)
                    return HttpResponse(f'<div class="alert alert-danger">Error processing file: {str(e)}</div>', status=500)

    except Exception as e:
        # Catch-all for unexpected errors like unquote failure etc.
        logger.error(f"[HTMX View Fatal Error] Client {client_id}: Unexpected error in view_meta_tags_report for {file_path}: {str(e)}", exc_info=True)
        return HttpResponse(f'<div class="alert alert-danger">An unexpected server error occurred: {str(e)}</div>', status=500)
