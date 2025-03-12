import json
import logging
import os
import time
import re
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from celery.result import AsyncResult
from apps.agents.tools.crawl_website_tool.crawl_website_tool import CrawlWebsiteTool
from apps.agents.tools.screenshot_tool import screenshot_tool
from core.storage import SecureFileStorage
from urllib.parse import urlparse
from django.core.files.base import ContentFile
from celery import shared_task
from apps.agents.tasks.base import ProgressTask

logger = logging.getLogger(__name__)

# Initialize the storage object
crawl_storage = SecureFileStorage(private=True, collection='')

@login_required
def index(request):
    logger.debug("Rendering index page for crawl_website")
    context = {
        'page_title': 'Crawl Website',
    }
    return render(request, 'crawl_website/index.html', context)

def sanitize_url_for_filename(url):
    """Convert URL to a safe filename component."""
    # Parse the URL to extract domain
    parsed = urlparse(url)
    domain = parsed.netloc
    
    # Remove www prefix if present
    if domain.startswith('www.'):
        domain = domain[4:]
        
    # Remove non-alphanumeric characters and replace with underscores
    domain = re.sub(r'[^a-zA-Z0-9]', '_', domain)
    
    # Limit length to prevent very long filenames
    if len(domain) > 50:
        domain = domain[:50]
        
    return domain

@shared_task(bind=True, base=ProgressTask, time_limit=600, soft_time_limit=540)
def crawl_website_task(self, website_url, user_id, max_pages=100, max_depth=3,
                     wait_for=None, css_selector=None, include_patterns=None, 
                     exclude_patterns=None, output_type="markdown", save_file=True,
                     save_as_csv=True):
    """Celery task to crawl a website using the simplified CrawlWebsiteTool."""
    
    try:
        logger.info(f"Starting crawl for {website_url}, user_id={user_id}, max_pages={max_pages}")
        
        # Update initial progress
        self.update_progress(0, max_pages, "Starting crawl", crawled_urls=[])
        
        # Initialize the tool
        tool = CrawlWebsiteTool()
        
        # Run the crawl tool
        result_json = tool._run(
            website_url=website_url,
            user_id=user_id,
            max_pages=max_pages,
            max_depth=max_depth,
            wait_for=wait_for,
            css_selector=css_selector,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            output_type=output_type,
            task=self  # Pass the task for progress updates
        )
        
        # Parse the result
        result = json.loads(result_json)
        
        # Get total pages (default to 0 if not found)
        total_pages = result.get('total_pages', 0)
        
        # Extract crawled URLs for tracking
        crawled_urls = []
        if 'results' in result and isinstance(result['results'], list):
            crawled_urls = [item.get('url', '') for item in result['results'] if item.get('url')]
        
        # Update result with crawled URLs for reporting to frontend
        result['crawled_urls'] = crawled_urls
        
        if result.get('status') == 'success' and save_file:
            # Sanitize the URL for use in the filename
            sanitized_url = sanitize_url_for_filename(website_url if isinstance(website_url, str) else website_url[0])
            
            # Format timestamp as YYYY-MM-DD-HH-MM-SS
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
            
            # Create the filename
            filename = f"{user_id}/crawled_websites/{sanitized_url}_{timestamp}_{total_pages}.json"
            
            # Save the file using SecureFileStorage
            file_content = json.dumps(result, indent=4)
            file_path = crawl_storage._save(filename, 
                                          ContentFile(file_content.encode('utf-8')))
            
            # Get the file URL
            file_url = crawl_storage.url(file_path)
            
            # Add file information to the result
            result['file_url'] = file_url
            result['file_path'] = file_path
            logger.info(f"File saved to: {file_path}")
            
            # If CSV option is enabled, create and save a CSV file
            if save_as_csv and 'results' in result and isinstance(result['results'], list):
                import csv
                import io
                
                # Create CSV filename
                csv_filename = f"{user_id}/crawled_websites/{sanitized_url}_{timestamp}_{total_pages}.csv"
                
                # Create CSV content
                csv_buffer = io.StringIO()
                
                # Create a custom dialect for CSV that properly handles newlines
                class CustomDialect(csv.excel):
                    lineterminator = '\n'
                    quoting = csv.QUOTE_ALL
                    doublequote = True
                    escapechar = '\\'
                
                csv.register_dialect('custom', CustomDialect)
                csv_writer = csv.writer(csv_buffer, dialect='custom')
                
                # Write header row
                csv_writer.writerow(['URL', 'Content'])
                
                # Write data rows
                for item in result['results']:
                    url = item.get('url', '')
                    content = item.get('content', '')
                    
                    # Handle different content types
                    if isinstance(content, dict):
                        # For FULL output type or other dictionary content
                        content = json.dumps(content)
                    
                    # Make sure content is a string
                    if not isinstance(content, str):
                        content = str(content)
                    
                    # Replace all newlines with spaces to ensure CSV compatibility
                    # This is necessary for proper spreadsheet import
                    content = content.replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ')
                    
                    # Write the row with proper quoting
                    csv_writer.writerow([url, content])
                
                # Save the CSV file
                csv_content = csv_buffer.getvalue()
                csv_path = crawl_storage._save(csv_filename, 
                                             ContentFile(csv_content.encode('utf-8')))
                
                # Get the CSV URL
                csv_url = crawl_storage.url(csv_path)
                
                # Add CSV information to the result
                result['csv_url'] = csv_url
                result['csv_path'] = csv_path
                logger.info(f"CSV file saved to: {csv_path}")
        
        # Final progress update
        self.update_progress(100, 100, "Completed successfully", result=result)
        
        logger.info(f"Completed crawl for {website_url}, processed {total_pages} pages")
        return json.dumps(result)
        
    except Exception as e:
        logger.error(f"Error in crawl_website_task: {str(e)}", exc_info=True)
        self.update_progress(100, 100, f"Error: {str(e)}", error=str(e))
        return json.dumps({
            "status": "error",
            "message": str(e)
        })

@csrf_exempt
@login_required
def initiate_crawl(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            url = data.get('url')
            max_pages = int(data.get('max_pages', 100))
            max_depth = int(data.get('max_depth', 3))
            wait_for = data.get('wait_for')
            css_selector = data.get('css_selector')
            output_type = data.get('output_type', 'markdown')
            save_file = data.get('save_file', True)
            save_as_csv = data.get('save_as_csv', True)
            include_patterns = data.get('include_patterns')
            exclude_patterns = data.get('exclude_patterns')
            
            logger.debug(f"Initiating crawl for URL: {url} with max_pages: {max_pages}, output_type: {output_type}")
            if not url:
                return JsonResponse({'error': 'URL is required'}, status=400)
            
            # Launch the Celery task
            task = crawl_website_task.delay(
                website_url=url, 
                user_id=request.user.id,
                max_pages=max_pages,
                max_depth=max_depth,
                wait_for=wait_for,
                css_selector=css_selector,
                include_patterns=include_patterns,
                exclude_patterns=exclude_patterns,
                output_type=output_type,
                save_file=save_file,
                save_as_csv=save_as_csv
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
