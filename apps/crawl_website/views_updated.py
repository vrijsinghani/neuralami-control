import json
import logging
import os
import uuid
from datetime import datetime
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.crawl_website.models import CrawlResult
from apps.crawl_website.tasks import crawl_website_task
from apps.organizations.models import Organization
from apps.organizations.utils import get_user_organizations

logger = logging.getLogger(__name__)

@login_required
def index(request):
    """
    Display the crawl website interface.
    """
    # Get the user's organizations
    organizations = get_user_organizations(request.user)
    
    # Get the crawl results for the user
    crawl_results = CrawlResult.objects.filter(user=request.user).order_by('-created_at')
    
    # Prepare the context
    context = {
        'organizations': organizations,
        'crawl_results': crawl_results,
    }
    
    return render(request, 'crawl_website/index.html', context)

@login_required
def crawl_result_detail(request, result_id):
    """
    Display the details of a crawl result.
    """
    # Get the crawl result
    crawl_result = get_object_or_404(CrawlResult, id=result_id, user=request.user)
    
    # Prepare the context
    context = {
        'crawl_result': crawl_result,
    }
    
    return render(request, 'crawl_website/result_detail.html', context)

@login_required
def crawl_result_delete(request, result_id):
    """
    Delete a crawl result.
    """
    # Get the crawl result
    crawl_result = get_object_or_404(CrawlResult, id=result_id, user=request.user)
    
    # Delete the crawl result
    crawl_result.delete()
    
    # Redirect to the crawl website index
    return redirect('crawl_website:index')

@login_required
def crawl_website(request):
    """
    Crawl a website and save the results.
    """
    if request.method == 'POST':
        try:
            # Get the form data
            url = request.POST.get('url')
            max_pages = int(request.POST.get('max-pages', 10))
            max_depth = int(request.POST.get('max-depth', 2))
            include_patterns = request.POST.get('include-patterns')
            exclude_patterns = request.POST.get('exclude-patterns')
            save_file = 'save-file' in request.POST
            save_as_csv = 'save-as-csv' in request.POST
            
            # Get the output format
            output_format = []
            if 'output-text' in request.POST:
                output_format.append('text')
            if 'output-html' in request.POST:
                output_format.append('html')
            if 'output-metadata' in request.POST:
                output_format.append('metadata')
            if 'output-links' in request.POST:
                output_format.append('links')
            if 'output-screenshot' in request.POST:
                output_format.append('screenshot')
            
            # If no output format is selected, default to text
            if not output_format:
                output_format = ['text']
            
            # Convert output_format to comma-separated string
            output_format = ','.join(output_format)
            
            # Validate the URL
            if not url:
                return JsonResponse({'error': 'URL is required'}, status=400)
            
            # Create a task ID
            task_id = str(uuid.uuid4())
            
            # Create a crawl result
            crawl_result = CrawlResult.objects.create(
                user=request.user,
                url=url,
                task_id=task_id,
                status='pending',
                max_pages=max_pages,
                max_depth=max_depth,
                include_patterns=include_patterns,
                exclude_patterns=exclude_patterns,
                output_format=output_format,
            )
            
            # Start the crawl task
            crawl_website_task.delay(
                task_id=task_id,
                website_url=url,
                user_id=request.user.id,
                max_pages=max_pages,
                max_depth=max_depth,
                include_patterns=include_patterns,
                exclude_patterns=exclude_patterns,
                output_format=output_format,
                save_file=save_file,
                save_as_csv=save_as_csv
            )
            
            # Return the task ID
            return JsonResponse({'task_id': task_id})
        
        except Exception as e:
            logger.error(f"An error occurred: {e}", exc_info=True)
            return JsonResponse({'error': str(e)}, status=500)
    
    # If not a POST request, redirect to the index
    return redirect('crawl_website:index')

@login_required
def get_task_status(request, task_id):
    """
    Get the status of a crawl task.
    """
    try:
        # Get the crawl result
        crawl_result = get_object_or_404(CrawlResult, task_id=task_id, user=request.user)
        
        # Return the status
        return JsonResponse({
            'status': crawl_result.status,
            'progress': crawl_result.progress,
            'result_id': str(crawl_result.id) if crawl_result.status == 'completed' else None,
            'error': crawl_result.error,
        })
    
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def get_active_tasks(request):
    """
    Get the active crawl tasks for the user.
    """
    try:
        # Get the active crawl results
        active_results = CrawlResult.objects.filter(
            user=request.user,
            status__in=['pending', 'running']
        ).order_by('-created_at')
        
        # Prepare the response
        tasks = []
        for result in active_results:
            tasks.append({
                'task_id': result.task_id,
                'url': result.url,
                'status': result.status,
                'progress': result.progress,
                'created_at': result.created_at.isoformat(),
            })
        
        # Return the tasks
        return JsonResponse({'tasks': tasks})
    
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def cancel_task(request, task_id):
    """
    Cancel a crawl task.
    """
    try:
        # Get the crawl result
        crawl_result = get_object_or_404(CrawlResult, task_id=task_id, user=request.user)
        
        # Update the status
        crawl_result.status = 'cancelled'
        crawl_result.save()
        
        # Return success
        return JsonResponse({'success': True})
    
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def download_result(request, result_id, format):
    """
    Download the crawl result in the specified format.
    """
    try:
        # Get the crawl result
        crawl_result = get_object_or_404(CrawlResult, id=result_id, user=request.user)
        
        # Check if the result has the requested format
        if format not in crawl_result.output_format.split(','):
            return HttpResponse(f"Format '{format}' not available for this result", status=400)
        
        # Get the result data
        result_data = crawl_result.get_result_data()
        
        # Prepare the response based on the format
        if format == 'text':
            response = HttpResponse(result_data.get('text', ''), content_type='text/plain')
            response['Content-Disposition'] = f'attachment; filename="{crawl_result.url_domain}_{result_id}.txt"'
        elif format == 'html':
            response = HttpResponse(result_data.get('html', ''), content_type='text/html')
            response['Content-Disposition'] = f'attachment; filename="{crawl_result.url_domain}_{result_id}.html"'
        elif format == 'metadata':
            response = JsonResponse(result_data.get('metadata', {}))
            response['Content-Disposition'] = f'attachment; filename="{crawl_result.url_domain}_{result_id}_metadata.json"'
        elif format == 'links':
            response = JsonResponse(result_data.get('links', []), safe=False)
            response['Content-Disposition'] = f'attachment; filename="{crawl_result.url_domain}_{result_id}_links.json"'
        else:
            return HttpResponse(f"Format '{format}' not supported for download", status=400)
        
        return response
    
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        return HttpResponse(str(e), status=500)

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

            # Import the screenshot tool
            from apps.agents.tools.screenshot_tool.screenshot_tool import screenshot_tool
            
            # Call the screenshot tool
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
