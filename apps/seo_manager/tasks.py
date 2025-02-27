import logging
from celery import shared_task
from django.contrib.auth import get_user_model
from .models import Client
from .sitemap_extractor import extract_sitemap_and_meta_tags, extract_sitemap_and_meta_tags_from_url
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import json
from celery.exceptions import SoftTimeLimitExceeded

logger = logging.getLogger(__name__)

User = get_user_model()
channel_layer = get_channel_layer()

def send_progress_update(task_id, progress_data):
    """
    Send a progress update via WebSocket.
    
    Args:
        task_id: The Celery task ID
        progress_data: Dict containing progress information
    """
    try:
        group_name = f"metatags_task_{task_id}"
        logger.debug(f"Sending progress update to group {group_name}: {progress_data}")
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'progress_update',
                'progress': progress_data
            }
        )
        logger.debug(f"Progress update sent successfully to group {group_name}")
    except Exception as e:
        logger.error(f"Error sending progress update: {str(e)}")

class ProgressTracker:
    """Helper class to track and report progress during extraction."""
    
    def __init__(self, task_id, total_steps=4):
        self.task_id = task_id
        self.total_steps = total_steps
        self.current_step = 0
        self.current_action = "Starting"
        self.urls_found = 0
        self.urls_processed = 0
        self.total_urls = 0
    
    def update(self, step=None, action=None, urls_found=None, 
              urls_processed=None, total_urls=None):
        """Update progress and send via WebSocket."""
        if step is not None:
            self.current_step = step
        if action is not None:
            self.current_action = action
        if urls_found is not None:
            self.urls_found = urls_found
        if urls_processed is not None:
            self.urls_processed = urls_processed
        if total_urls is not None:
            self.total_urls = total_urls
        
        # Calculate overall progress percentage
        step_weight = 100 / self.total_steps
        base_progress = (self.current_step - 1) * step_weight if self.current_step > 0 else 0
        
        # Add progress within current step
        if self.current_step == 2 and self.total_urls > 0:  # URL processing step
            step_progress = (self.urls_processed / self.total_urls) * step_weight
        else:
            step_progress = 0
        
        overall_progress = min(base_progress + step_progress, 100)
        
        # Send progress update
        progress_data = {
            'percent': overall_progress,
            'step': self.current_step,
            'action': self.current_action,
            'urls_found': self.urls_found,
            'urls_processed': self.urls_processed,
            'total_urls': self.total_urls
        }
        
        send_progress_update(self.task_id, progress_data)
        return progress_data

@shared_task(bind=True, max_retries=1, default_retry_delay=30, time_limit=6*60*60, soft_time_limit=5*60*60)
def extract_sitemap_task(self, website_url, output_file, user_id):
    """
    Background task to extract sitemap and meta tags from a website URL.
    
    Args:
        website_url: The URL of the website to extract from
        output_file: The path where the output should be saved
        user_id: The id of the user initiating the task
        
    Returns:
        dict: Results of the extraction process
    """
    try:
        logger.info(f"Starting sitemap extraction task for URL {website_url}")
        
        # Create progress tracker
        progress = ProgressTracker(self.request.id)
        progress.update(step=1, action="Initializing extraction")
        
        # Get the user object
        user = User.objects.get(id=user_id)
        
        # Set up a callback for the extraction process to report progress
        def progress_callback(action, urls_found=None, urls_processed=None, total_urls=None):
            nonlocal progress
            # Update step based on action
            if "Finding sitemaps" in action:
                step = 1
            elif "Processing URLs" in action:
                step = 2
            elif "Saving results" in action:
                step = 3
            else:
                step = progress.current_step
                
            progress.update(
                step=step,
                action=action,
                urls_found=urls_found,
                urls_processed=urls_processed,
                total_urls=total_urls
            )
        
        # Run the extraction with progress callback
        from .sitemap_extractor import extract_sitemap_and_meta_tags_from_url
        
        file_path = extract_sitemap_and_meta_tags_from_url(
            website_url, 
            user, 
            output_file=output_file,
            progress_callback=progress_callback
        )
        
        # Final progress update
        progress.update(step=4, action="Completed")
        
        logger.info(f"Sitemap extraction completed for URL {website_url}. File path: {file_path}")
        
        # Return the file path for reference
        return {
            'success': True,
            'file_path': file_path,
            'url': website_url
        }
        
    except SoftTimeLimitExceeded:
        logger.error(f"Soft time limit exceeded for sitemap extraction from URL {website_url}")
        # Send a timeout message via WebSocket
        send_progress_update(self.request.id, {
            'status': 'error',
            'message': 'Task timed out. The website may have too many pages to process in the allowed time.',
            'progress': 100,
            'step': 4,
            'complete': True
        })
        return {
            'success': False,
            'error': 'Extraction timed out. The website may have too many pages to process.',
            'website_url': website_url,
            'file_path': output_file
        }
    except Exception as e:
        logger.error(f"Error in sitemap extraction task: {str(e)}")
        # Send error via WebSocket
        send_progress_update(self.request.id, {
            'error': str(e),
            'action': 'Error occurred'
        })
        
        # Retry once after 30 seconds
        try:
            self.retry(exc=e)
        except Exception as retry_exc:
            logger.error(f"Task retry failed: {str(retry_exc)}")
            return {
                'success': False,
                'error': str(e),
                'url': website_url
            }

@shared_task(bind=True, max_retries=1, default_retry_delay=30, time_limit=6*60*60, soft_time_limit=5*60*60)
def extract_sitemap_from_url_task(self, website_url, output_file, user_id):
    """
    Background task to extract sitemap and meta tags from a URL.
    
    Args:
        website_url: The URL to extract from
        output_file: The path where the output should be saved
        user_id: The id of the user initiating the task
        
    Returns:
        dict: Results of the extraction process
    """
    try:
        logger.info(f"Starting sitemap extraction task for URL {website_url}")
        
        # Create progress tracker
        progress = ProgressTracker(self.request.id)
        progress.update(step=1, action="Initializing extraction")
        
        # Get the user object
        user = User.objects.get(id=user_id)
        
        # Set up a callback for the extraction process to report progress
        def progress_callback(action, urls_found=None, urls_processed=None, total_urls=None):
            nonlocal progress
            # Update step based on action
            if "Finding sitemaps" in action:
                step = 1
            elif "Processing URLs" in action:
                step = 2
            elif "Saving results" in action:
                step = 3
            else:
                step = progress.current_step
                
            progress.update(
                step=step,
                action=action,
                urls_found=urls_found,
                urls_processed=urls_processed,
                total_urls=total_urls
            )
        
        # Run the extraction with progress callback
        from .sitemap_extractor import extract_sitemap_and_meta_tags_from_url
        
        file_path = extract_sitemap_and_meta_tags_from_url(
            website_url, 
            user, 
            output_file=output_file,
            progress_callback=progress_callback
        )
        
        # Final progress update
        progress.update(step=4, action="Completed")
        
        logger.info(f"Sitemap extraction completed for URL {website_url}. File path: {file_path}")
        
        # Return the file path for reference
        return {
            'success': True,
            'file_path': file_path,
            'url': website_url
        }
        
    except SoftTimeLimitExceeded:
        logger.error(f"Soft time limit exceeded for sitemap extraction from URL {website_url}")
        # Send a timeout message via WebSocket
        send_progress_update(self.request.id, {
            'status': 'error',
            'message': 'Task timed out. The website may have too many pages to process in the allowed time.',
            'progress': 100,
            'step': 4,
            'complete': True
        })
        return {
            'success': False,
            'error': 'Extraction timed out. The website may have too many pages to process.',
            'website_url': website_url,
            'file_path': output_file
        }
    except Exception as e:
        logger.error(f"Error in sitemap extraction from URL task: {str(e)}")
        # Send error via WebSocket
        send_progress_update(self.request.id, {
            'error': str(e),
            'action': 'Error occurred'
        })
        
        # Retry once after 30 seconds
        try:
            self.retry(exc=e)
        except Exception as retry_exc:
            logger.error(f"Task retry failed: {str(retry_exc)}")
            return {
                'success': False,
                'error': str(e),
                'url': website_url
            } 