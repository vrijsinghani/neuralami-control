import json
import logging
import uuid
import csv
import io
from datetime import datetime
import time
import threading

from celery import shared_task
from celery.contrib.abortable import AbortableTask
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.template.loader import render_to_string
from django.core.files.base import ContentFile
from pydantic import AnyHttpUrl


# Import tools and utilities (adjust paths as necessary)
from apps.agents.tools.crawl_website_tool.crawl_website_tool import CrawlWebsiteTool
from apps.agents.tools.web_crawler_tool.sitemap_crawler import SitemapCrawlerTool, ContentOutputFormat
from core.storage import SecureFileStorage
from .utils import sanitize_url_for_filename # Import from utils now

logger = logging.getLogger(__name__)

# Initialize storage (if tasks still need direct access)
crawl_storage = SecureFileStorage(private=True, collection='')

# --- Helper Function for Sending WS Updates ---

def send_crawl_update(task_id, update_type, data):
    """Sends an update message to the WebSocket group."""
    try:
        channel_layer = get_channel_layer()
        if not channel_layer:
            logger.warning(f"Cannot send WS update for {task_id}: Channel layer not configured.")
            return

        group_name = f"crawl_{task_id}"
        message = {
            'type': 'crawl.update', # Corresponds to the consumer method name
            'data': {
                'update_type': update_type,
                **data, # Merge the specific data payload
            }
        }
        # # Only log detailed info for non-heartbeat messages to avoid log noise
        # if update_type != 'heartbeat':
        #     logger.debug(f"Sending WS update to group {group_name}: Type={update_type}, DataKeys={list(data.keys())}")
        # else:
        #     # Simplified logging for heartbeats
        #     logger.debug(f"Sending heartbeat to group {group_name}: #{data.get('heartbeat_count', 0)}")

        # Use async_to_sync to call the async channel layer method from sync task
        async_to_sync(channel_layer.group_send)(group_name, message)
    except Exception as e:
        logger.error(f"Error sending WebSocket update for task {task_id}: {e}", exc_info=True)

# --- Celery Tasks ---

# Define a base task class if needed for common logic, otherwise use shared_task directly
# class CrawlBaseTask(AbortableTask):
#     pass # Add common abort/cleanup logic if needed

@shared_task(bind=True, time_limit=1800, soft_time_limit=1620)
def crawl_website_task(self, task_id, website_url, user_id, max_pages=100, max_depth=3,
                     wait_for=None, css_selector=None, include_patterns=None,
                     exclude_patterns=None, output_format="text",
                     save_file=False, save_as_csv=False, # Default to False
                     wait_for_element=None): # Add wait_for_element here
    """Celery task for standard website crawl, sending progress via WebSockets."""
    logger.info(f"Starting standard crawl task {task_id} for {website_url}, user_id={user_id}")

    def progress_reporter(progress, total, message, **kwargs):
        """Callback function to send progress updates via WebSocket."""
        # Ensure progress is between 0 and 100
        percent_complete = min(100, max(0, int((progress / total) * 100) if total > 0 else 0))

        update_data = {
            'status': 'in_progress',
            'message': message,
            'progress': percent_complete,
            'current_step': progress,
            'total_steps': total,
            'current_url': kwargs.get('url', None), # Tool might pass current URL
            'links_visited': progress, # Assuming progress maps to links visited here
        }
        send_crawl_update(task_id, 'progress', update_data)

    try:
        # Send initial update
        progress_reporter(0, max_pages, "Starting crawl", url=website_url)

        # Initialize the tool
        tool = CrawlWebsiteTool()

        result_json = tool._run(
            website_url=website_url,
            user_id=user_id,
            max_pages=max_pages,
            max_depth=max_depth,
            wait_for=wait_for,
            css_selector=css_selector,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            output_type=output_format,
            progress_callback=progress_reporter
        )

        result = json.loads(result_json)

        if result.get('status') == 'success':
            file_url = None
            csv_url = None
            if save_file:
                # Add file/CSV saving logic here using crawl_storage and sanitize_url_for_filename
                # (Copied and adapted from original view logic)
                try:
                    # Determine filename suffix based on output format
                    if output_format == 'json':
                        file_suffix = 'json'
                        content_to_save = json.dumps(result['results'], indent=4) # Save just the results array
                    elif output_format == 'html':
                        file_suffix = 'html'
                        # Combine HTML content (assuming results contain HTML strings)
                        content_to_save = '\n<hr>\n'.join([item.get('content', '') for item in result.get('results', [])])
                    else: # Default to text
                        file_suffix = 'txt'
                        # Combine text content
                        content_to_save = '\n---\n'.join([
                            f"URL: {item.get('url', '')}\n\n{item.get('content', '')}"
                            for item in result.get('results', [])
                        ])

                    sanitized_url = sanitize_url_for_filename(website_url)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

                    filename = f"{user_id}/crawled_websites/{sanitized_url}_{timestamp}.{file_suffix}"
                    file_path = crawl_storage.save(filename, ContentFile(content_to_save.encode('utf-8')))
                    file_url = crawl_storage.url(file_path)
                    logger.info(f"Output file saved to: {file_path} (format: {file_suffix}) for task {task_id}")

                    # --- CSV Save (if requested and output is not JSON already) ---
                    if save_as_csv and 'results' in result and isinstance(result['results'], list) and output_format != 'json':
                        try:
                            csv_filename = f"{user_id}/crawled_websites/{sanitized_url}_{timestamp}.csv"
                            csv_buffer = io.StringIO()
                            csv_writer = csv.writer(csv_buffer, dialect='excel', lineterminator='\n', quoting=csv.QUOTE_ALL)
                            csv_writer.writerow(['URL', 'Content'])
                            for item in result['results']:
                                url_item = item.get('url', '')
                                content_item = item.get('content', '')
                                # Simple string conversion for CSV
                                if not isinstance(content_item, str):
                                    content_item = str(content_item)
                                content_item = content_item.replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ') # Basic newline removal
                                csv_writer.writerow([url_item, content_item])
                            csv_content = csv_buffer.getvalue()
                            csv_path = crawl_storage.save(csv_filename, ContentFile(csv_content.encode('utf-8')))
                            csv_url = crawl_storage.url(csv_path)
                            logger.info(f"CSV file saved to: {csv_path} for task {task_id}")
                        except Exception as csv_save_err:
                            logger.error(f"Error saving CSV results for task {task_id}: {csv_save_err}", exc_info=True)
                except Exception as primary_save_err:
                    logger.error(f"Error saving primary output file for task {task_id}: {primary_save_err}", exc_info=True)
                    # Decide if this should cause the task to fail or just log the error

            final_data = {
                'status': 'completed',
                'message': 'Crawl completed successfully.',
                'results': result.get('results'),
                'output_format': output_format,
                'file_url': file_url, # Pass file URLs to consumer
                'csv_url': csv_url
            }
            send_crawl_update(task_id, 'completion', final_data)
            logger.info(f"Completed standard crawl task {task_id} for {website_url}")
        else:
            error_message = result.get('message', 'Unknown error occurred during crawl.')
            final_data = {'status': 'failed', 'message': error_message}
            send_crawl_update(task_id, 'error', final_data)
            logger.error(f"Failed standard crawl task {task_id} for {website_url}: {error_message}")

        return result_json

    except Exception as e:
        error_message = f"Unexpected error in crawl_website_task: {str(e)}"
        logger.error(f"{error_message} (Task ID: {task_id})", exc_info=True)
        final_data = {'status': 'failed', 'message': error_message}
        send_crawl_update(task_id, 'error', final_data)
        # Reraise to mark the task as failed in Celery
        raise


@shared_task(bind=True, time_limit=1200, soft_time_limit=1140) # Use limits from Sitemap tool
def sitemap_crawl_wrapper_task(self, task_id, user_id, url: str,
                               max_sitemap_urls_to_process: int = 50,
                               max_sitemap_retriever_pages: int = 1000,
                               requests_per_second: float = 5.0,
                               output_format: str = 'text', # Default to text string literal
                               timeout: int = 15000,
                               save_file: bool = False, # Add save flags
                               save_as_csv: bool = False):
    """Celery task wrapper for SitemapCrawlerTool, sending progress via WebSockets."""
    logger.info(f"Starting sitemap crawl task {task_id} for {url}, user_id={user_id}")

    # Heartbeat mechanism - runs in a separate thread
    heartbeat_active = True
    heartbeat_interval = 2  # Reduced to 2 seconds for more frequent heartbeats to maintain connection

    def websocket_heartbeat():
        """Send periodic heartbeats to keep WebSocket connection alive"""
        heartbeat_count = 0
        while heartbeat_active:
            try:
                heartbeat_count += 1
                heartbeat_data = {
                    'status': 'in_progress',
                    'message': f"Working... please wait",
                    'progress': -1,  # Special value indicating a heartbeat
                    'is_heartbeat': True,
                    'heartbeat_count': heartbeat_count
                }
                send_crawl_update(task_id, 'heartbeat', heartbeat_data)
                time.sleep(heartbeat_interval)
            except Exception as e:
                logger.warning(f"Heartbeat thread encountered error: {e}")
                # Don't crash the heartbeat thread, try again after interval
                time.sleep(heartbeat_interval)

    # Start heartbeat thread
    heartbeat_thread = threading.Thread(target=websocket_heartbeat, daemon=True)
    heartbeat_thread.start()

    # Flag to track if completion/error was already sent by callback
    final_update_sent = False

    def progress_reporter(progress, total, message, **kwargs):
        """Callback function passed to the tool to send WS updates."""
        nonlocal final_update_sent # Allow modification of outer scope flag
        percent_complete = min(100, max(0, int((progress / total) * 100) if total > 0 else 0))

        update_data = {
            'status': 'in_progress',
            'message': message,
            'progress': percent_complete,
            'current_step': progress,
            'total_steps': total,
            'current_url': kwargs.get('url', None), # Sitemap tool provides current_url
            'links_visited': progress, # Approximation for sitemap processing
            'is_heartbeat': False  # Regular progress update
        }
        send_crawl_update(task_id, 'progress', update_data)

        # Also handle final result from callback if tool provides it here
        if progress == 100 and 'result' in kwargs:
            if final_update_sent:
                logger.warning(f"Final update already sent for task {task_id}, skipping callback completion.")
                return # Avoid sending duplicate completion messages

            final_result_data = kwargs['result']
            # Check if the result indicates success (adjust based on actual tool output structure)
            if final_result_data.get('success', False):
                file_url = None
                csv_url = None

                # --- File Saving Logic (Similar to standard crawl task) ---
                if save_file and final_result_data.get('results'):
                    try:
                        # Determine filename suffix based on output format
                        if output_format == 'json':
                            file_suffix = 'json'
                            # Save the list of result dictionaries directly
                            content_to_save = json.dumps(final_result_data['results'], indent=4)
                        elif output_format == 'html':
                            file_suffix = 'html'
                            # Combine HTML content
                            content_to_save = '\n<hr>\n'.join([item.get('content', '') for item in final_result_data.get('results', [])])
                        else: # Default to text
                            file_suffix = 'txt'
                            # Combine text content
                            content_to_save = '\n---\n'.join([
                                f"URL: {item.get('url', '')}\n\n{item.get('content', '')}"
                                for item in final_result_data.get('results', [])
                            ])

                        sanitized_url = sanitize_url_for_filename(url)
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

                        filename = f"{user_id}/crawled_websites/{sanitized_url}_{timestamp}.{file_suffix}"
                        file_path = crawl_storage.save(filename, ContentFile(content_to_save.encode('utf-8')))
                        file_url = crawl_storage.url(file_path)
                        logger.info(f"Output file saved to: {file_path} (format: {file_suffix}) for task {task_id}")

                        # Add CSV saving here if needed and format allows
                        if save_as_csv and output_format != 'json' and isinstance(final_result_data.get('results', []), list):
                            try:
                                csv_filename = f"{user_id}/crawled_websites/{sanitized_url}_{timestamp}.csv"
                                csv_buffer = io.StringIO()
                                csv_writer = csv.writer(csv_buffer, dialect='excel', lineterminator='\n', quoting=csv.QUOTE_ALL)
                                csv_writer.writerow(['URL', 'Content'])
                                for item in final_result_data.get('results', []):
                                    url_item = item.get('url', '')
                                    content_item = item.get('content', '')
                                    # Simple string conversion for CSV
                                    if not isinstance(content_item, str):
                                        content_item = str(content_item)
                                    content_item = content_item.replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ') # Basic newline removal
                                    csv_writer.writerow([url_item, content_item])
                                csv_content = csv_buffer.getvalue()
                                csv_path = crawl_storage.save(csv_filename, ContentFile(csv_content.encode('utf-8')))
                                csv_url = crawl_storage.url(csv_path)
                                logger.info(f"CSV file saved to: {csv_path} for task {task_id}")
                            except Exception as csv_save_err:
                                logger.error(f"Error saving CSV results for task {task_id}: {csv_save_err}", exc_info=True)

                    except Exception as primary_save_err:
                        logger.error(f"Error saving primary output file for task {task_id}: {primary_save_err}", exc_info=True)
                        # File saving failed, but task might still be successful
                        # file_url remains None

                completion_data = {
                    'status': 'completed',
                    'message': final_result_data.get('message', 'Sitemap crawl completed successfully.'),
                    'results': final_result_data.get('results'), # Send processed results
                    'output_format': output_format,
                    'sitemap_source_url': final_result_data.get('sitemap_source_url'),
                    'total_sitemap_urls_found': final_result_data.get('total_sitemap_urls_found'),
                    'urls_processed': final_result_data.get('urls_processed'),
                    'file_url': file_url, # Pass URL if file was saved
                    'csv_url': csv_url   # Pass URL if CSV was saved
                }
                send_crawl_update(task_id, 'completion', completion_data)
                logger.info(f"Completed sitemap crawl task {task_id} via callback for {url}")
                final_update_sent = True # Mark as sent
            else:
                # Handle potential error reported within final result callback
                error_message = final_result_data.get('message', final_result_data.get('error', 'Sitemap crawl finished with errors.'))
                error_data = {'status': 'failed', 'message': error_message}
                send_crawl_update(task_id, 'error', error_data)
                logger.error(f"Failed sitemap crawl task {task_id} via callback for {url}: {error_message}")
                final_update_sent = True # Mark as sent


    try:
        tool = SitemapCrawlerTool()
        # Run the tool, passing the progress reporter callback
        result_json = tool._run(
            url=AnyHttpUrl(url),
            user_id=user_id,
            max_sitemap_urls_to_process=max_sitemap_urls_to_process,
            max_sitemap_retriever_pages=max_sitemap_retriever_pages,
            requests_per_second=requests_per_second,
            output_format=output_format,
            timeout=timeout,
            progress_callback=progress_reporter, # Pass the callback here
        )

        # Stop heartbeat thread
        heartbeat_active = False
        heartbeat_thread.join(timeout=2.0)  # Wait up to 2 seconds for clean shutdown

        # Note: The final success/error message might have already been sent by the callback.
        logger.debug(f"SitemapCrawlerTool._run call completed for task {task_id}. Final update handled by callback.")

        # Optional: Parse result_json and send update IF callback didn't handle completion/error
        # This is fallback logic in case the callback fails or the tool changes behavior.
        if not final_update_sent:
             try:
                 result = json.loads(result_json)
                 if result.get('success', False):
                     # Save files here as well? This might duplicate effort if callback handles it.
                     # For now, assume callback handles saving and file URLs.
                     logger.warning(f"Callback did not send final update for successful task {task_id}. Sending fallback completion.")
                     completion_data = {
                         'status': 'completed',
                         'message': result.get('message', 'Sitemap crawl completed (fallback).'),
                         'results': result.get('results'),
                         'output_format': output_format,
                         'sitemap_source_url': result.get('sitemap_source_url'),
                         'total_sitemap_urls_found': result.get('total_sitemap_urls_found'),
                         'urls_processed': result.get('urls_processed'),
                         'file_url': None, # Fallback doesn't have file URLs
                         'csv_url': None
                     }
                     send_crawl_update(task_id, 'completion', completion_data)
                 else:
                     logger.warning(f"Callback did not send final update for failed task {task_id}. Sending fallback error.")
                     error_message = result.get('message', 'Sitemap crawl failed (fallback).')
                     error_data = {'status': 'failed', 'message': error_message}
                     send_crawl_update(task_id, 'error', error_data)
             except json.JSONDecodeError:
                 logger.error(f"Fallback: Failed to parse tool result JSON for task {task_id}")
                 error_data = {'status': 'failed', 'message': 'Failed to parse tool results.'}
                 send_crawl_update(task_id, 'error', error_data)
             except Exception as fallback_err:
                 logger.error(f"Fallback: Error processing tool result for task {task_id}: {fallback_err}", exc_info=True)
                 error_data = {'status': 'failed', 'message': 'Internal error processing results.'}
                 send_crawl_update(task_id, 'error', error_data)

        return result_json # Return the original result from the tool

    except Exception as e:
        error_message = f"Unexpected error in sitemap_crawl_wrapper_task: {str(e)}"
        logger.error(f"{error_message} (Task ID: {task_id})", exc_info=True)
        final_data = {'status': 'failed', 'message': error_message}
        send_crawl_update(task_id, 'error', final_data)

        # Stop heartbeat thread
        heartbeat_active = False
        if heartbeat_thread.is_alive():
            heartbeat_thread.join(timeout=2.0)

        # Reraise to mark the task as failed in Celery
        raise

# Ensure tasks are discoverable by Celery
# Add an __init__.py file in the crawl_website app directory if it doesn't exist
# Make sure celery.py imports tasks using app.autodiscover_tasks()