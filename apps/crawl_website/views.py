import json
import logging
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from celery.result import AsyncResult
from apps.common.tools.async_crawl_website_tool import crawl_website_task
from django.contrib.auth.decorators import login_required
from apps.crawl_website.models import CrawlResult
from apps.common.tools.screenshot_tool import screenshot_tool
from django.contrib import messages
from django.urls import reverse

logger = logging.getLogger(__name__)

@login_required
def index(request):
    logger.debug("Rendering index page for crawl_website")
    return render(request, 'crawl_website/index.html')

@csrf_exempt
@login_required
def initiate_crawl(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            url = data.get('url')
            
            if not url:
                return JsonResponse({'error': 'URL is required'}, status=400)
            
            # Initiate the Celery task
            task = crawl_website_task.delay(url, request.user.id)
            
            return JsonResponse({'task_id': task.id})
        except Exception as e:
            logger.exception(f"An error occurred: {str(e)}")
            return JsonResponse({'error': 'An unexpected error occurred'}, status=500)
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)

@csrf_exempt
@login_required
def get_crawl_progress(request):
    if request.method == 'GET':
        task_id = request.GET.get('task_id')
        if not task_id:
            return JsonResponse({'error': 'Task ID is required'}, status=400)
        
        result = AsyncResult(task_id)
        if result.state == 'PENDING':
            response = {
                'state': result.state,
                'current': 0,
                'total': 0,
                'status': 'Pending...',
                'links_to_visit': []
            }
        elif result.state == 'PROGRESS':
            response = {
                'state': result.state,
                'current': result.info.get('current', 0),
                'total': result.info.get('total', 0),
                'status': result.info.get('status', ''),
                'links_to_visit': result.info.get('links_to_visit', [])
            }
        elif result.state == 'SUCCESS':
            crawl_result = CrawlResult.objects.get(id=result.result)
            response = {
                'state': result.state,
                'current': len(crawl_result.links_visited),
                'total': crawl_result.total_links,
                'status': 'Completed',
                'links_to_visit': crawl_result.links_to_visit
            }
        else:
            response = {
                'state': result.state,
                'current': 0,
                'total': 1,
                'status': str(result.info),
                'links_to_visit': []
            }
        return JsonResponse(response)
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)

@csrf_exempt
@login_required
def get_crawl_result(request, task_id):
    try:
        result = AsyncResult(task_id)
        if result.state == 'SUCCESS':
            crawl_result = CrawlResult.objects.get(id=result.result)
            file_url = reverse('download_crawl_result', kwargs={'result_id': crawl_result.id})
            messages.success(request, f'Crawl completed! <a href="{file_url}">Download result</a>')
            return JsonResponse({
                'website_url': crawl_result.website_url,
                'links_visited': crawl_result.links_visited,
                'total_links': crawl_result.total_links,
                'links_to_visit': crawl_result.links_to_visit,
                'result_file_path': crawl_result.result_file_path,
                'file_url': file_url
            })
        else:
            return JsonResponse({'error': 'Task not completed yet'}, status=400)
    except CrawlResult.DoesNotExist:
        return JsonResponse({'error': 'Crawl result not found'}, status=404)
    except Exception as e:
        logger.exception(f"An error occurred: {str(e)}")
        return JsonResponse({'error': 'An unexpected error occurred'}, status=500)

@login_required
def download_crawl_result(request, result_id):
    try:
        crawl_result = CrawlResult.objects.get(id=result_id, user=request.user)
        file_path = crawl_result.result_file_path
        if os.path.exists(file_path):
            with open(file_path, 'rb') as file:
                response = HttpResponse(file.read(), content_type='text/plain')
                response['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'
                return response
        else:
            messages.error(request, 'File not found.')
            return redirect('crawl_website:index')
    except CrawlResult.DoesNotExist:
        messages.error(request, 'Crawl result not found.')
        return redirect('crawl_website:index')

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
                logger.error("URL is required")
                return JsonResponse({'error': 'URL is required'}, status=400)
            
            result = screenshot_tool.run(url=url)
            
            if 'error' in result:
                logger.error(f"Failed to get screenshot: {result['error']}")
                return JsonResponse({'error': result['error']}, status=500)
            
            logger.debug(f"Screenshot saved: {result['screenshot_url']}")
            return JsonResponse({'screenshot_url': result['screenshot_url']})
        except Exception as e:
            logger.exception(f"An error occurred: {str(e)}")
            return JsonResponse({'error': 'An unexpected error occurred'}, status=500)
    
    logger.error("Invalid request method")
    return JsonResponse({'error': 'Invalid request method'}, status=405)
