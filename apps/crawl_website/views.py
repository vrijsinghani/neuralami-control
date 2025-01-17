import json
import logging
import os
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from celery.result import AsyncResult
from apps.agents.tools.crawl_website_tool.crawl_website_tool import crawl_website_task
from django.contrib.auth.decorators import login_required
from apps.crawl_website.models import CrawlResult
from apps.common.tools.screenshot_tool import screenshot_tool
from django.contrib import messages

logger = logging.getLogger(__name__)

@login_required
def index(request):
    logger.debug("Rendering index page for crawl_website")
    context = {
        'page_title': 'Crawl Website',
    }
    return render(request, 'crawl_website/index.html', context)

@csrf_exempt
@login_required
def initiate_crawl(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            url = data.get('url')
            max_pages = data.get('max_pages', 100)
            
            if not url:
                return JsonResponse({'error': 'URL is required'}, status=400)
            
            task = crawl_website_task.delay(
                website_url=url, 
                user_id=request.user.id,
                max_pages=max_pages
            )
            
            return JsonResponse({
                'task_id': task.id,
                'status': 'started'
            })
        except Exception as e:
            logger.error(f"An error occurred: {e}", exc_info=True)
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)

@csrf_exempt
@login_required
def get_crawl_progress(request):
    """Get the progress of a crawl task."""
    task_id = request.GET.get('task_id')
    if not task_id:
        return JsonResponse({'error': 'Task ID is required'}, status=400)

    try:
        task = AsyncResult(task_id)
        logger.debug(f"Checking progress for task: {task_id}")
        
        if task.ready():
            if task.successful():
                crawl_result = CrawlResult.objects.get(id=task.result)
                return JsonResponse({
                    'status': 'completed',
                    'content': crawl_result.get_content(),
                    'file_url': crawl_result.get_file_url(),
                    'links_visited': crawl_result.links_visited,
                    'total_links': crawl_result.total_links
                })
            else:
                return JsonResponse({
                    'status': 'failed',
                    'error': str(task.result)
                })
        
        # Task is still running
        progress = task.info or {}
        return JsonResponse({
            'status': 'in_progress',
            'current': progress.get('current', 0),
            'total': progress.get('total', 1),
            'status_message': progress.get('status', 'Processing...')
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
            crawl_result = CrawlResult.objects.get(id=result.result)
            return JsonResponse({
                'state': 'SUCCESS',
                'website_url': crawl_result.website_url,
                'content': crawl_result.get_content(),
                'links_visited': crawl_result.links_visited.get('internal', []),
                'total_links': crawl_result.total_links,
                'file_url': crawl_result.get_file_url()
            })
        else:
            return JsonResponse({
                'state': result.state,
                'status': 'Task not completed yet'
            }, status=202)
    except CrawlResult.DoesNotExist:
        return JsonResponse({'error': 'Crawl result not found'}, status=404)
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
