import logging
import time
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from apps.agents.models import CrewMessage, CrewExecution, Task
from ..handlers.websocket import send_message_to_websocket

logger = logging.getLogger(__name__)
channel_layer = get_channel_layer()

def log_crew_message(execution, content, agent=None, human_input_request=None, crewai_task_id=None):
    try:
        max_retries = 3
        retry_delay = 1  # seconds
        
        # Get target groups to send to
        target_groups = [f"crew_execution_{execution.id}"]
        
        # If this is a chat execution, also send to the chat group
        if execution.inputs and isinstance(execution.inputs, dict):
            chat_context = execution.inputs.get('chat_context', {})
            if isinstance(chat_context, dict):
                session_id = chat_context.get('session_id')
                if session_id:
                    target_groups.append(f"chat_{session_id}")
            # Also check top-level session_id
            elif 'session_id' in execution.inputs:
                session_id = execution.inputs['session_id']
                if session_id:
                    target_groups.append(f"chat_{session_id}")
        
        # Send to all target groups
        for group in target_groups:
            for attempt in range(max_retries):
                try:
                    if group.startswith('chat_'):
                        # Chat format
                        message_data = {
                            "type": "crew_message",
                            "message": content,
                            "metadata": {
                                "agent": agent or "System",
                                "status": "running",
                                "message_type": "log"
                            }
                        }
                    else:
                        # Kanban format (original)
                        message_data = {
                            "type": "crew_execution_update",
                            "status": execution.status,
                            "messages": [{"agent": agent or "System", "content": content}],
                            "human_input_request": human_input_request,
                            "crewai_task_id": crewai_task_id
                        }
                    
                    async_to_sync(channel_layer.group_send)(
                        group,
                        message_data
                    )
                    logger.debug(f"Sent message to group {group}")
                    break
                except Exception as e:
                    if attempt == max_retries - 1:
                        logger.error(f"Failed to send WebSocket message to {group} after {max_retries} attempts: {str(e)}")
                    else:
                        logger.warning(f"WebSocket send attempt {attempt + 1} to {group} failed, retrying in {retry_delay}s: {str(e)}")
                        time.sleep(retry_delay)
        
        # Log message to database
        if content:  # Only create a message if there's content
            message = CrewMessage.objects.create(
                execution=execution, 
                content=content, 
                agent=agent,
                crewai_task_id=crewai_task_id
            )
            logger.debug(f"Sent message to WebSocket: {content[:100]}")
        else:
            logger.warning("Attempted to log an empty message, skipping.")
    except Exception as e:
        logger.error(f"Error in log_crew_message: {str(e)}")

def update_execution_status(execution, status, message=None):
    """Update execution status and send WebSocket message"""
    execution.status = status
    execution.save()
    
    # Create properly formatted event
    event = {
        'type': 'execution_update',
        'execution_id': execution.id,
        'status': status,
        'message': message,
        'stage': {
            'stage_type': 'status_update',
            'title': 'Status Update',
            'content': message or f'Status changed to {status}',
            'status': status.lower(),
            'agent': 'System'
        }
    }
    
    # Send WebSocket message with proper format
    send_message_to_websocket(event) 