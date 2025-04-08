import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

class CrawlConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.task_id = self.scope['url_route']['kwargs']['task_id']
        self.group_name = f"crawl_{self.task_id}"

        # Check if task_id is valid (optional, maybe check against a model or cache)
        if not self.task_id or self.task_id == 'initial': # Reject connection if task_id isn't set yet
            logger.warning(f"WebSocket connection rejected: Invalid task_id '{self.task_id}'.")
            await self.close()
            return

        #logger.info(f"WebSocket connecting for crawl task: {self.task_id}")
        # Join room group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()
        #logger.info(f"WebSocket connected and added to group: {self.group_name}")

    async def disconnect(self, close_code):
        logger.info(f"WebSocket disconnecting from group: {self.group_name}")
        # Leave room group
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )
        logger.info("WebSocket disconnected.")

    # Receive message from WebSocket (if needed for client->server communication)
    # async def receive(self, text_data):
    #     pass

    # Receive message from room group (sent by Celery task)
    async def crawl_update(self, event):
        """Handles messages sent from the Celery task via channel_layer.group_send."""
        data = event['data']
        update_type = data.get('update_type')
        #logger.debug(f"Received crawl_update for {self.group_name}, type: {update_type}")

        # Special handling for heartbeat messages
        if update_type == 'heartbeat':
            # For heartbeats, just send a minimal JSON message to keep the connection alive
            # No need to render templates or trigger UI updates
            await self.send(text_data=json.dumps({
                'type': 'heartbeat',
                'count': data.get('heartbeat_count', 0)
            }))
            #logger.debug(f"Sent heartbeat #{data.get('heartbeat_count', 0)} to {self.group_name}")
            return

        # Special handling for event messages (like crawl_progress)
        if update_type == 'event' and data.get('event_name') == 'crawl_progress':
            # For crawl_progress events, render HTML updates for the stats cards
            pages_visited = data.get('pages_visited', 0)
            links_found = data.get('links_found', 0)
            current_url = data.get('current_url', '')

            # Calculate progress percentage based on max_pages
            max_pages = data.get('max_pages', 100)  # Default to 100 if not provided
            progress_percent = min(100, int((pages_visited / max_pages) * 100)) if max_pages > 0 else 0

            logger.info(f"Progress update: pages_visited={pages_visited}, max_pages={max_pages}, progress_percent={progress_percent}%")

            # Create HTML updates for the stats cards and progress bar
            html = f"""
            <div id="pages-visited-count" hx-swap-oob="true">{pages_visited}</div>
            <div id="links-found-count" hx-swap-oob="true">{links_found}</div>
            <div id="current-page-url" hx-swap-oob="true">{current_url}</div>
            <span id="links-visited-count" hx-swap-oob="true">{pages_visited}</span>
            <div id="current-url-display" hx-swap-oob="true">Current URL: <code>{current_url}</code></div>
            <div id="crawl-progress-bar" class="progress-bar" role="progressbar" style="width: {progress_percent}%" aria-valuenow="{progress_percent}" aria-valuemin="0" aria-valuemax="100" hx-swap-oob="true"></div>
            <span id="progress-percent-display" hx-swap-oob="true">{progress_percent}%</span>
            """

            await self.send(text_data=html)
            #logger.debug(f"Sent HTML updates for crawl_progress to {self.group_name}")
            return
        elif update_type == 'event':
            # For other event types, forward the event data directly to the client
            event_data = json.dumps(data)
            await self.send(text_data=event_data)
            logger.debug(f"Forwarded event message to {self.group_name}: {data.get('event_name')}")
            return

        html = ""

        try:
            if update_type == 'progress':
                # Render the status/progress partial
                context = {
                    'status': data.get('status', 'in_progress'),
                    'message': data.get('message', 'Processing...'),
                    'progress': data.get('progress', 0),
                    'links_visited': data.get('links_visited', 0),
                    'current_url': data.get('current_url', 'N/A')
                }
                html = render_to_string('crawl_website/partials/_crawl_status_progress.html', context)
                # Target the outer div for replacement
                target_id = '#crawl-status-progress'
                # Wrap the HTML with OOB swap instruction targeting the specific container
                html = f'<div id="{target_id[1:]}" hx-swap-oob="true">{html}</div>'

            elif update_type == 'completion' or update_type == 'cancelled':
                # Render the results partial
                # Prepare the context with all necessary data
                context = {
                    'status': 'completed' if update_type == 'completion' else 'cancelled',
                    'results': data.get('results', []), # Pass the actual results data
                    'output_format': data.get('output_format', 'text'),
                    # Add file_url, csv_url if saving is implemented and passed from task
                    'file_url': data.get('file_url'),
                    'csv_url': data.get('csv_url'),
                    'message': data.get('message', 'Crawl completed successfully.')
                }

                # Log the results for debugging
                logger.debug(f"Results data for {self.task_id}: {context['results'][:100] if isinstance(context['results'], str) else len(context['results']) if isinstance(context['results'], list) else type(context['results'])}")
                results_html = render_to_string('crawl_website/partials/_crawl_results.html', context)
                # Target the results div for replacement
                target_id_results = '#crawl-results'
                # Also update progress to 100%
                progress_context = {'status': 'completed', 'progress': 100, 'message': 'Completed successfully.'}
                progress_html = render_to_string('crawl_website/partials/_crawl_status_progress.html', progress_context)

                # Update the crawling status title and hide spinner
                status_title = 'Crawl Completed' if update_type == 'completion' else 'Crawl Cancelled'

                # Wrap fragments with OOB swap instructions
                wrapped_results = f'<div id="{target_id_results[1:]}" hx-swap-oob="true">{results_html}</div>'
                wrapped_progress = f'<div id="crawl-status-progress" hx-swap-oob="true">{progress_html}</div>'
                wrapped_title = f'<h6 id="crawling-status-title" hx-swap-oob="true">{status_title}</h6>'
                wrapped_spinner = f'<div id="progress-spinner" class="crawling-spinner me-3" style="display: none;" hx-swap-oob="true"></div>'
                wrapped_results_section = f'<div id="crawl-results-section" style="display: block;" hx-swap-oob="true">{render_to_string("crawl_website/partials/_crawl_results_section.html", context)}</div>'

                # Combine all updates
                html = wrapped_results + wrapped_progress + wrapped_title + wrapped_spinner + wrapped_results_section

                # Additionally, send a structured message for JS listeners (e.g., dialogs, charts)
                event_data = {
                    'type': 'event',
                    'event_name': 'crawl_complete' if update_type == 'completion' else 'crawl_cancelled',
                    'message': progress_context['message'], # Use the completion message
                    'success': update_type == 'completion',
                    # Include URLs only if the task completed successfully
                    'file_url': data.get('file_url') if update_type == 'completion' else None,
                    'csv_url': data.get('csv_url') if update_type == 'completion' else None,
                    'task_id': self.task_id,  # Include the task ID
                    'results': data.get('results')  # Include the results data
                }
                await self.send(text_data=json.dumps(event_data))
                logger.debug(f"Sent JSON event ({update_type}) to {self.group_name}")

            elif update_type == 'failed':
                # Render the results partial with error state
                context = {
                    'status': 'failed',
                    'error_message': data.get('error_message', 'An unknown error occurred.')
                }
                results_html = render_to_string('crawl_website/partials/_crawl_results.html', context)
                # Target the results div for replacement
                target_id_results = '#crawl-results'
                # Also update progress to show failure
                progress_context = {'status': 'failed', 'progress': 0, 'message': context['error_message']}
                progress_html = render_to_string('crawl_website/partials/_crawl_status_progress.html', progress_context)

                # Update the crawling status title and hide spinner
                status_title = 'Crawl Failed'

                # Wrap fragments with OOB swap instructions
                wrapped_results = f'<div id="{target_id_results[1:]}" hx-swap-oob="true">{results_html}</div>'
                wrapped_progress = f'<div id="crawl-status-progress" hx-swap-oob="true">{progress_html}</div>'
                wrapped_title = f'<h6 id="crawling-status-title" hx-swap-oob="true">{status_title}</h6>'
                wrapped_spinner = f'<div id="progress-spinner" class="crawling-spinner me-3" style="display: none;" hx-swap-oob="true"></div>'
                wrapped_results_section = f'<div id="crawl-results-section" style="display: block;" hx-swap-oob="true">{render_to_string("crawl_website/partials/_crawl_results_section.html", context)}</div>'

                # Combine all updates
                html = wrapped_results + wrapped_progress + wrapped_title + wrapped_spinner + wrapped_results_section

                # Additionally, send a structured message for JS listeners
                error_event_data = {
                    'type': 'event',
                    'event_name': 'crawl_error', # Consistent event name
                    'message': context['error_message'], # Use the error message
                    'success': False
                }
                await self.send(text_data=json.dumps(error_event_data))
                logger.debug(f"Sent JSON event (crawl_error) to {self.group_name}")

            else:
                logger.warning(f"Received unknown crawl_update type: {update_type}")
                return

            # Send HTML fragment to WebSocket with OOB swap instruction
            await self.send(text_data=html)
            #logger.debug(f"Sent HTML update (OOB) to {self.group_name} for type {update_type}")

        except Exception as e:
            logger.error(f"Error processing crawl_update for {self.group_name}: {e}", exc_info=True)
            # Optionally send an error message back to the client
            await self.send(text_data=json.dumps({'error': 'Failed to process update.'}))