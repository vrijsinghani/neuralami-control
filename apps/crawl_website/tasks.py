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
# Removed import for AnyHttpUrl as it's no longer needed

# Import the export utilities
from .export_utils import generate_text_content, generate_csv_content, save_crawl_results


# Import tools and utilities (adjust paths as necessary)
from apps.agents.tools.crawl_website_tool.crawl_website_tool import CrawlWebsiteTool
# Removed import for sitemap_crawler as it's now consolidated into web_crawler_tool
from apps.agents.tools.web_crawler_tool.web_crawler_tool import WebCrawlerTool, CrawlOutputFormat, CrawlMode
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
            'type': 'crawl_update', # Corresponds to the consumer method name
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

@shared_task(bind=True, base=AbortableTask, time_limit=1800, soft_time_limit=1620)
def crawl_website_task(self, task_id, website_url, user_id, max_pages=100, max_depth=3,
                     include_patterns=None, exclude_patterns=None, output_format="text",
                     save_file=False, save_as_csv=False, mode="auto", delay_seconds=1.0): # Added delay_seconds parameter
    """Celery task for website crawl, sending progress via WebSockets."""
    logger.info(f"Starting crawl task {task_id} for {website_url}, user_id={user_id}, mode={mode}, delay_seconds={delay_seconds}")

    # Initialize counters for tracking cumulative progress
    # These variables are in the task function scope and can be accessed by inner functions
    pages_visited_counter = 0
    links_found_counter = 0

    def progress_reporter(progress, total, message, **kwargs):
        """Callback function to send progress updates via WebSocket."""
        nonlocal pages_visited_counter

        # Update cumulative counter if progress is greater
        if progress > pages_visited_counter:
            pages_visited_counter = progress

        # Ensure progress is between 0 and 100
        percent_complete = min(100, max(0, int((pages_visited_counter / total) * 100) if total > 0 else 0))

        update_data = {
            'status': 'in_progress',
            'message': message,
            'progress': percent_complete,
            'current_step': pages_visited_counter,
            'total_steps': total,
            'current_url': kwargs.get('url', None), # Tool might pass current URL
            'links_visited': pages_visited_counter, # Use cumulative count
        }
        send_crawl_update(task_id, 'progress', update_data)

    try:
        # Send initial update
        progress_reporter(0, max_pages, "Starting crawl", url=website_url)

        # Also send a direct progress update to ensure the progress bar is initialized correctly
        send_crawl_update(task_id, 'progress', {
            'status': 'in_progress',
            'message': 'Starting crawl',
            'progress': 0,
            'current_step': 0,
            'total_steps': max_pages,
            'current_url': website_url,
            'links_visited': 0
        })

        # Check if task has been aborted - try multiple methods
        is_aborted = False

        # Method 1: Use the AbortableTask.is_aborted method
        try:
            if self.is_aborted():
                is_aborted = True
                logger.info(f"Task {task_id} was aborted before starting (is_aborted method)")
        except Exception as e:
            logger.error(f"Error checking if task is aborted: {e}")

        # Method 2: Check if the task has been revoked
        from celery import current_app
        try:
            # Get the list of revoked tasks
            inspect = current_app.control.inspect()
            revoked_tasks = inspect.revoked() or {}
            all_revoked = []
            for worker_name, tasks in revoked_tasks.items():
                all_revoked.extend(tasks)
            if task_id in all_revoked:
                is_aborted = True
                logger.info(f"Task {task_id} was aborted before starting (revoked check)")
        except Exception as e:
            logger.error(f"Error checking if task is revoked: {e}")

        if is_aborted:
            logger.info(f"Task {task_id} was aborted before starting")
            send_crawl_update(task_id, 'event', {
                'type': 'event',
                'event_name': 'crawl_cancelled',
                'message': 'Crawl was cancelled before starting.'
            })
            return {'status': 'cancelled', 'message': 'Crawl was cancelled before starting.'}

        # Initialize the tool - use WebCrawlerTool instead of CrawlWebsiteTool
        tool = WebCrawlerTool()

        # Parse output_format if it's a comma-separated string
        output_formats = output_format.split(',') if isinstance(output_format, str) and ',' in output_format else output_format

        # Prepare parameters for the WebCrawlerTool
        # Convert include_patterns and exclude_patterns to the format expected by WebCrawlerTool
        tool_include_patterns = include_patterns if include_patterns else None
        tool_exclude_patterns = exclude_patterns if exclude_patterns else None

        # Create a callback function to send progress updates and check for abortion
        def progress_callback(pages_visited, links_found, current_url):
            # Access the counters from the outer function
            nonlocal pages_visited_counter, links_found_counter

            # Update cumulative counters
            # For sitemap strategy, pages_visited is the current index (1-based)
            # For discovery strategy, pages_visited is the total visited so far
            # We need to handle both cases
            if pages_visited > pages_visited_counter:
                # Discovery strategy or first page in sitemap
                pages_visited_counter = pages_visited
            else:
                # Sitemap strategy - increment counter
                pages_visited_counter += 1

            # Update links counter if provided
            if links_found > links_found_counter:
                links_found_counter = links_found

            logger.info(f"Progress update: pages_visited={pages_visited}, cumulative={pages_visited_counter}, current_url={current_url}")

            # Check if task has been aborted - try multiple methods
            is_aborted = False

            # Method 1: Use the AbortableTask.is_aborted method
            try:
                if self.is_aborted():
                    is_aborted = True
                    logger.info(f"Task {task_id} was aborted during crawl (is_aborted method)")
            except Exception as e:
                logger.error(f"Error checking if task is aborted: {e}")

            # Method 2: Check if the task has been revoked
            from celery import current_app
            try:
                # Get the list of revoked tasks
                inspect = current_app.control.inspect()
                revoked_tasks = inspect.revoked() or {}
                all_revoked = []
                for worker_name, tasks in revoked_tasks.items():
                    all_revoked.extend(tasks)
                if task_id in all_revoked:
                    is_aborted = True
                    logger.info(f"Task {task_id} was aborted during crawl (revoked check)")
            except Exception as e:
                logger.error(f"Error checking if task is revoked: {e}")

            # If the task has been aborted, raise an exception to stop the crawl
            if is_aborted:
                send_crawl_update(task_id, 'event', {
                    'type': 'event',
                    'event_name': 'crawl_cancelled',
                    'message': 'Crawl was cancelled during execution.'
                })
                # Raise an exception to stop the crawl
                raise Exception("Task aborted")

            # Calculate progress percentage
            percent_complete = min(100, max(0, int((pages_visited_counter / max_pages) * 100) if max_pages > 0 else 0))

            # Send an event update for individual elements
            send_crawl_update(task_id, 'event', {
                'type': 'event',
                'event_name': 'crawl_progress',
                'pages_visited': pages_visited_counter,
                'links_found': links_found_counter,
                'current_url': current_url,
                'max_pages': max_pages  # Pass max_pages to calculate progress percentage
            })

            # Also send a progress update to update the entire progress bar
            send_crawl_update(task_id, 'progress', {
                'status': 'in_progress',
                'message': f'Crawling page {pages_visited_counter} of {max_pages}',
                'progress': percent_complete,
                'current_step': pages_visited_counter,
                'total_steps': max_pages,
                'current_url': current_url,
                'links_visited': pages_visited_counter
            })

        # Call the WebCrawlerTool with the appropriate parameters
        result = tool._run(
            start_url=website_url,
            max_pages=max_pages,
            max_depth=max_depth,
            output_format=output_formats,
            include_patterns=tool_include_patterns,
            exclude_patterns=tool_exclude_patterns,
            stay_within_domain=True,  # Default to staying within the same domain
            device="desktop",  # Default to desktop device
            delay_seconds=delay_seconds,  # Use the delay_seconds parameter from the task
            batch_size=5,  # Default batch size
            max_retries=3,  # Default max retries
            timeout=60000,  # Default timeout in milliseconds
            stealth=True,  # Default to stealth mode
            mode=mode,  # Pass the mode parameter
            progress_callback=progress_callback  # Pass the progress callback
        )

        # Handle both dictionary and string results
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse result as JSON: {e}")
                raise

        if result.get('status') == 'success' or ('results' in result and result['results']):
            file_url = None
            csv_url = None
            if save_file:
                # Add file/CSV saving logic here using crawl_storage and sanitize_url_for_filename
                # (Copied and adapted from original view logic)
                # Use the common utility function to save the results
                file_url, csv_url = save_crawl_results(
                    results=result.get('results', []),
                    url=website_url,
                    user_id=user_id,
                    output_format=output_format,
                    storage=crawl_storage,
                    save_as_csv=save_as_csv
                )

                # Log the file URLs
                if file_url:
                    logger.info(f"Output file saved for task {task_id}: {file_url}")
                if csv_url:
                    logger.info(f"CSV file saved for task {task_id}: {csv_url}")

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

        return json.dumps(result)

    except Exception as e:
        # Check if this was an abort exception
        if str(e) == "Task aborted" or "abort" in str(e).lower() or "revoked" in str(e).lower() or "terminated" in str(e).lower():
            logger.info(f"Task {task_id} was aborted: {str(e)}")

            # Send cancelled notification
            final_data = {'status': 'cancelled', 'message': 'Crawl was cancelled.'}
            send_crawl_update(task_id, 'event', {
                'type': 'event',
                'event_name': 'crawl_cancelled',
                'message': 'Crawl was cancelled.'
            })

            # Return cancelled result without reraising
            return json.dumps({
                'status': 'cancelled',
                'message': 'Crawl was cancelled.'
            })
        else:
            # Handle other exceptions
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
    """Celery task wrapper for sitemap crawling using the unified WebCrawlerTool with mode='sitemap', sending progress via WebSockets."""
    logger.info(f"Starting sitemap crawl task {task_id} for {url}, user_id={user_id}, using unified crawler with mode=sitemap")

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

        # Send progress update for the progress bar
        progress_data = {
            'status': 'in_progress',
            'message': message,
            'progress': percent_complete,
            'current_step': progress,
            'total_steps': total,
            'current_url': kwargs.get('url', None), # Sitemap tool provides current_url
            'links_visited': progress, # Approximation for sitemap processing
            'is_heartbeat': False  # Regular progress update
        }
        send_crawl_update(task_id, 'progress', progress_data)

        # Also send an event update for the stats cards
        event_data = {
            'update_type': 'event',
            'event_name': 'crawl_progress',
            'pages_visited': progress,
            'links_found': kwargs.get('links_count', 0),  # Use links_count if provided, otherwise 0
            'current_url': kwargs.get('url', 'Processing...')
        }
        send_crawl_update(task_id, 'event', event_data)

        # Check for final update

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

                # --- File Saving Logic ---
                if save_file and final_result_data.get('results'):
                    # Use the common utility function to save the results
                    file_url, csv_url = save_crawl_results(
                        results=final_result_data.get('results', []),
                        url=url,
                        user_id=user_id,
                        output_format=output_format,
                        storage=crawl_storage,
                        save_as_csv=save_as_csv
                    )

                    # Log the file URLs
                    if file_url:
                        logger.info(f"Output file saved for task {task_id}: {file_url}")
                    if csv_url:
                        logger.info(f"CSV file saved for task {task_id}: {csv_url}")

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
        tool = WebCrawlerTool()
        # Run the tool, passing the progress reporter callback
        result = tool._run(
            start_url=url,
            max_pages=max_sitemap_urls_to_process,
            max_depth=1,  # Sitemap crawling doesn't use depth
            output_format=output_format,
            stay_within_domain=True,
            delay_seconds=1.0 / requests_per_second if requests_per_second > 0 else 0.2,
            timeout=timeout,
            mode="sitemap",  # Use sitemap mode
            progress_callback=progress_reporter  # Pass the callback here
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
                 # Result is already a dictionary, no need to parse it
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

        return json.dumps(result) # Return the result as a JSON string

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