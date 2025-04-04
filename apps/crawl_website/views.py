import json
import logging
import os
import time
import re
import uuid
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from celery.result import AsyncResult
from celery.contrib.abortable import AbortableAsyncResult
from core.storage import SecureFileStorage
from urllib.parse import urlparse
from django.core.files.base import ContentFile
from .tasks import crawl_website_task, sitemap_crawl_wrapper_task
from celery import current_app
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)

# Initialize the storage object
crawl_storage = SecureFileStorage(private=True, collection='')

@login_required
def index(request):
    logger.debug("Rendering index page for crawl_website")
    context = {
        'page_title': 'Crawl Website',
        'task_id': 'initial'
    }
    return render(request, 'crawl_website/index.html', context)

@login_required
def crawl(request):
    logger.debug("Rendering alternative crawl page with HTMX UI")
    context = {
        'page_title': 'Website Crawler',
        'task_id': 'initial'
    }
    return render(request, 'crawl_website/crawl.html', context)

@csrf_exempt
@login_required
def initiate_crawl(request):
    if request.method == 'POST':
        task_id = None # Initialize task_id
        try:
            # Read data from request.POST (form submission) instead of request.body (JSON)
            url = request.POST.get('url')
            crawl_type = request.POST.get('crawl_type', 'standard')
            output_format = request.POST.get('output_format', 'text')
            css_selector = request.POST.get('css_selector')
            wait_for_element = request.POST.get('wait_for_element')
            save_file = 'save-file' in request.POST
            save_as_csv = 'save-as-csv' in request.POST

            logger.debug(f"Initiating crawl via form POST for URL: {url}, Type: {crawl_type}")
            if not url:
                return HttpResponse('<div class="alert alert-danger">URL is required</div>', status=400)

            task_id = uuid.uuid4().hex

            if crawl_type == 'sitemap':
                max_sitemap_urls = int(request.POST.get('max_sitemap_urls', 50))
                max_retriever_pages = int(request.POST.get('max_sitemap_retriever_pages', 1000))
                req_per_sec = float(request.POST.get('sitemap_requests_per_second', 5.0))
                timeout = int(request.POST.get('sitemap_timeout', 15000))

                sitemap_crawl_wrapper_task.delay(
                    task_id=task_id,
                    user_id=request.user.id,
                    url=url,
                    max_sitemap_urls_to_process=max_sitemap_urls,
                    max_sitemap_retriever_pages=max_retriever_pages,
                    requests_per_second=req_per_sec,
                    output_format=output_format,
                    timeout=timeout,
                    save_file=save_file,
                    save_as_csv=save_as_csv
                )
                logger.info(f"Launched sitemap crawl task {task_id} for {url}")

            else: # Default to standard crawl
                max_pages = int(request.POST.get('max_pages', 100))
                max_depth = int(request.POST.get('max_depth', 3))
                include_patterns_str = request.POST.get('include_patterns')
                exclude_patterns_str = request.POST.get('exclude_patterns')

                include_patterns = [p.strip() for p in include_patterns_str.split(',') if p.strip()] if include_patterns_str else None
                exclude_patterns = [p.strip() for p in exclude_patterns_str.split(',') if p.strip()] if exclude_patterns_str else None

                wait_for = request.POST.get('wait-for')

                crawl_website_task.delay(
                    task_id=task_id,
                    website_url=url,
                    user_id=request.user.id,
                    max_pages=max_pages,
                    max_depth=max_depth,
                    wait_for=wait_for,
                    css_selector=css_selector,
                    include_patterns=include_patterns,
                    exclude_patterns=exclude_patterns,
                    output_format=output_format,
                    save_file=save_file,
                    save_as_csv=save_as_csv,
                    wait_for_element=wait_for_element
                )
                logger.info(f"Launched standard crawl task {task_id} for {url}")

            # Return success response with task_id in header for JS
            response = HttpResponse(
                '<div id="crawl-status-message" hx-swap-oob="true"><div class="alert alert-info">Crawl initiated...</div></div>',
                status=200
            )
            response['X-Task-ID'] = task_id
            return response

        # Removed JSONDecodeError as we are not parsing JSON anymore
        except ValueError as e:
             logger.warning(f"Value error during crawl initiation for task_id={task_id}: {e}")
             return HttpResponse(f'<div class="alert alert-danger">Invalid parameter value: {e}</div>', status=400)
        except Exception as e:
            logger.error(f"Error initiating crawl task_id={task_id}: {e}", exc_info=True)
            return HttpResponse(f'<div class="alert alert-danger">Error initiating crawl: {e}</div>', status=500)

    return HttpResponse('<div class="alert alert-danger">Invalid request method</div>', status=405)

@csrf_exempt
@login_required
def cancel_crawl(request, task_id):
    """Cancel a running crawl task."""
    if request.method != 'POST':
        return HttpResponse('<div class="alert alert-danger">Invalid request method</div>', status=405)

    try:
        # Get the task
        result = AbortableAsyncResult(task_id)

        # Check if task exists and is not already done
        if not result.state or result.state in ['SUCCESS', 'FAILURE', 'REVOKED']:
            return HttpResponse(
                '<div class="alert alert-warning">Task is not running or does not exist</div>',
                status=404
            )

        # Revoke and terminate the task
        result.revoke(terminate=True)

        # Send a cancellation message via WebSocket
        channel_layer = get_channel_layer()
        if channel_layer:
            group_name = f"crawl_{task_id}"
            message = {
                'type': 'crawl_update',
                'data': {
                    'update_type': 'cancelled',
                    'status': 'cancelled',
                    'message': 'Crawl was cancelled by user.'
                }
            }
            async_to_sync(channel_layer.group_send)(group_name, message)

        return HttpResponse(
            '<div class="alert alert-success">Crawl task cancelled successfully</div>',
            status=200
        )
    except Exception as e:
        logger.error(f"Error cancelling crawl task {task_id}: {e}", exc_info=True)
        return HttpResponse(
            f'<div class="alert alert-danger">Error cancelling task: {str(e)}</div>',
            status=500
        )

@login_required
def list_active_crawls(request):
    """List active crawl tasks for the current user."""
    try:
        # Get all active tasks from Celery
        i = current_app.control.inspect()
        active_tasks = i.active() or {}
        scheduled_tasks = i.scheduled() or {}
        reserved_tasks = i.reserved() or {}

        # Combine all tasks
        all_tasks = []

        # Process active tasks
        for worker, tasks in active_tasks.items():
            for task in tasks:
                if task['name'] in ['apps.crawl_website.tasks.crawl_website_task', 'apps.crawl_website.tasks.sitemap_crawl_wrapper_task']:
                    # Extract task info
                    task_info = {
                        'id': task['id'],
                        'name': task['name'].split('.')[-1],
                        'status': 'RUNNING',
                        'worker': worker,
                        'started': task.get('time_start', 'Unknown'),
                        'args': task.get('args', []),
                        'kwargs': task.get('kwargs', {})
                    }

                    # Check if this task belongs to the current user
                    kwargs = task.get('kwargs', {})
                    if kwargs.get('user_id') == request.user.id:
                        all_tasks.append(task_info)

        # Process scheduled and reserved tasks similarly
        for worker, tasks in scheduled_tasks.items():
            for task in tasks:
                task_info = task['request']
                if task_info['name'] in ['apps.crawl_website.tasks.crawl_website_task', 'apps.crawl_website.tasks.sitemap_crawl_wrapper_task']:
                    if task_info.get('kwargs', {}).get('user_id') == request.user.id:
                        all_tasks.append({
                            'id': task_info['id'],
                            'name': task_info['name'].split('.')[-1],
                            'status': 'SCHEDULED',
                            'worker': worker,
                            'args': task_info.get('args', []),
                            'kwargs': task_info.get('kwargs', {})
                        })

        for worker, tasks in reserved_tasks.items():
            for task in tasks:
                if task['name'] in ['apps.crawl_website.tasks.crawl_website_task', 'apps.crawl_website.tasks.sitemap_crawl_wrapper_task']:
                    if task.get('kwargs', {}).get('user_id') == request.user.id:
                        all_tasks.append({
                            'id': task['id'],
                            'name': task['name'].split('.')[-1],
                            'status': 'RESERVED',
                            'worker': worker,
                            'args': task.get('args', []),
                            'kwargs': task.get('kwargs', {})
                        })

        # Return the tasks as JSON
        return JsonResponse({'tasks': all_tasks})
    except Exception as e:
        logger.error(f"Error listing active crawls: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@login_required
def get_crawl_progress(request):
    """Get the progress of a crawl task."""
    task_id = request.GET.get('task_id')
    if not task_id:
        return JsonResponse({'error': 'Task ID is required'}, status=400)

    try:
        task = AsyncResult(task_id)

        if task.ready():
            if task.successful():
                # Parse the JSON string result
                result = json.loads(task.result)

                if result.get('status') == 'error':
                    return JsonResponse({
                        'status': 'failed',
                        'error': result.get('message', 'Unknown error occurred')
                    })

                return JsonResponse({
                    'status': 'completed',
                    'result': result,
                    'total_pages': result.get('total_pages', 0),
                    'file_url': result.get('file_url'),
                    'csv_url': result.get('csv_url'),
                    'crawled_urls': result.get('crawled_urls', [])
                })
            else:
                return JsonResponse({
                    'status': 'failed',
                    'error': str(task.result)
                })
        else:
            # Return current progress from task meta
            info = task.info or {}  # Handle None case
            return JsonResponse({
                'status': 'in_progress',
                'current': info.get('current', 0) if isinstance(info, dict) else 0,
                'total': info.get('total', 1) if isinstance(info, dict) else 1,
                'status_message': info.get('status', 'Processing...') if isinstance(info, dict) else str(info),
                'crawled_urls': info.get('crawled_urls', []) if isinstance(info, dict) else []
            })

    except Exception as e:
        logger.error(f"Error checking progress: {str(e)}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

@csrf_exempt
@login_required
def get_crawl_result(request, task_id):
    try:
        result = AsyncResult(task_id)
        if result.state == 'SUCCESS':
            # Parse the JSON string result
            task_result = json.loads(result.result)

            if task_result.get('status') == 'error':
                return JsonResponse({
                    'state': 'FAILURE',
                    'error': task_result.get('message', 'Unknown error occurred')
                })

            # The file should already be saved by the Celery task, just return the result
            file_url = task_result.get('file_url')
            csv_url = task_result.get('csv_url')

            return JsonResponse({
                'state': 'SUCCESS',
                'website_url': task_result.get('website_url'),
                'result': task_result,
                'total_pages': task_result.get('total_pages', 0),
                'file_url': file_url,
                'csv_url': csv_url
            })
        else:
            return JsonResponse({
                'state': result.state,
                'status': 'Task not completed yet'
            }, status=202)
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@login_required
def get_screenshot(request):
    logger.debug("get_screenshot function called")
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            url = data.get('url')
            logger.debug(f"Received URL: {url}")

            if not url:
                return JsonResponse({'error': 'URL is required'}, status=400)

            result = screenshot_tool.run(url=url)
            if 'error' in result:
                logger.error(f"Failed to get screenshot: {result['error']}")
                return JsonResponse({'error': result['error']}, status=500)

            logger.debug(f"Screenshot saved: {result['screenshot_url']}")
            return JsonResponse({'screenshot_url': result['screenshot_url']})
        except Exception as e:
            logger.error(f"An error occurred: {e}", exc_info=True)
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Invalid request method'}, status=405)
