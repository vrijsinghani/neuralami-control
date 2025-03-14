import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from apps.common.websockets.organization_consumer import OrganizationAwareConsumer
from celery.result import AsyncResult
import asyncio
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)

class MetaTagsTaskConsumer(OrganizationAwareConsumer):
    """WebSocket consumer for meta tags extraction task updates with organization context support."""
    
    async def connect(self):
        """Handle WebSocket connection with organization context."""
        # Set organization context first
        await super().connect()
        
        self.task_id = self.scope['url_route']['kwargs']['task_id']
        self.group_name = f"metatags_task_{self.task_id}"
        
        # Join the group for this task
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        await self.accept()
        logger.info(f"WebSocket connection established for meta tags task: {self.task_id}")
        
        # Start the background task to check task status periodically
        self.check_task_status_task = asyncio.create_task(self.check_task_status_periodically())
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        # Leave the group
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )
        
        # Cancel the background task if it's running
        if hasattr(self, 'check_task_status_task'):
            self.check_task_status_task.cancel()
            
        logger.info(f"WebSocket connection closed for meta tags task: {self.task_id}")
        
        # Clear organization context
        await super().disconnect(close_code)
    
    async def receive(self, text_data):
        """Handle incoming WebSocket messages."""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'check_status':
                # Client is requesting a status update
                await self.check_task_status()
            
        except Exception as e:
            logger.error(f"Error processing WebSocket message: {str(e)}")
    
    async def check_task_status_periodically(self):
        """Periodically check Celery task status and send updates."""
        try:
            while True:
                await self.check_task_status()
                # Wait for 2 seconds before checking again
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            # Task was cancelled, this is normal during disconnect
            pass
        except Exception as e:
            logger.error(f"Error in periodic task status check: {str(e)}")
    
    @sync_to_async
    def get_task_status(self, task_id):
        """Get Celery task status in a synchronous context."""
        try:
            result = AsyncResult(task_id)
            
            if result.ready():
                if result.successful():
                    task_result = result.get()
                    # Extract file path from result for the client to use
                    file_path = task_result.get('file_path', '')
                    success = task_result.get('success', False)
                    
                    return {
                        'ready': True,
                        'successful': True,
                        'task_result': task_result,
                        'file_path': file_path,
                        'success': success,
                        'url': task_result.get('url', '')
                    }
                else:
                    error = str(result.result) if result.result else "Unknown error"
                    return {
                        'ready': True,
                        'successful': False,
                        'error': error
                    }
            else:
                # Task is still pending
                return {
                    'ready': False,
                    'state': result.state
                }
        except Exception as e:
            logger.error(f"Error in get_task_status: {str(e)}")
            return {
                'ready': True,
                'successful': False,
                'error': str(e)
            }
    
    async def check_task_status(self):
        """Check the status of the Celery task and send an update."""
        try:
            # Get task status in a way safe for async context
            result_info = await self.get_task_status(self.task_id)
            
            # Prepare the status update based on result_info
            if result_info['ready']:
                if result_info['successful']:
                    status_update = {
                        'type': 'status_update',
                        'status': 'complete',
                        'result': {
                            'success': result_info['success'],
                            'file_path': result_info['file_path'],
                            'url': result_info['url']
                        },
                        'message': "Meta tags snapshot completed successfully."
                    }
                    logger.info(f"Task {self.task_id} completed successfully: {result_info['file_path']}")
                else:
                    status_update = {
                        'type': 'status_update',
                        'status': 'failed',
                        'error': result_info['error'],
                        'message': f"Meta tags snapshot failed: {result_info['error']}"
                    }
                    logger.error(f"Task {self.task_id} failed: {result_info['error']}")
            else:
                # Task is still pending
                status_update = {
                    'type': 'status_update',
                    'status': 'pending',
                    'message': "Meta tags snapshot is still processing."
                }
            
            # Send the status update to the group
            await self.channel_layer.group_send(
                self.group_name,
                status_update
            )
        except Exception as e:
            logger.error(f"Error checking task status: {str(e)}")
            
    async def progress_update(self, event):
        """Handle progress updates and send them to the WebSocket."""
        try:
            # Log the incoming progress event
            logger.debug(f"Received progress_update event: {event}")
            
            # Send progress data directly without the type field
            message = {
                'progress': event['progress']
            }
            logger.debug(f"Sending progress message to WebSocket: {message}")
            await self.send(text_data=json.dumps(message))
        except Exception as e:
            logger.error(f"Error sending progress update: {str(e)}")
    
    async def status_update(self, event):
        """Handle status updates and send them to the WebSocket."""
        try:
            # Log the incoming status event
            logger.debug(f"Received status_update event: {event}")
            
            # Remove type field as it's used internally by channels
            data = {k: v for k, v in event.items() if k != 'type'}
            
            logger.debug(f"Sending status message to WebSocket: {data}")
            # Send the status update to the WebSocket - send directly as expected by client
            await self.send(text_data=json.dumps(data))
        except Exception as e:
            logger.error(f"Error sending status update: {str(e)}") 