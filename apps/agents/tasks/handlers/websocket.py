import logging
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from apps.agents.models import CrewExecution

logger = logging.getLogger(__name__)
channel_layer = get_channel_layer()

def send_message_to_websocket(message):
    """Send message to websocket"""
    try:
        # Get execution ID from message
        execution_id = message.get('execution_id')
        if not execution_id:
            logger.error("No execution_id in message")
            return

        # Get crew ID from execution
        try:
            execution = CrewExecution.objects.get(id=execution_id)
            crew_id = execution.crew.id
        except CrewExecution.DoesNotExist:
            logger.error(f"No execution found for ID {execution_id}")
            return

        # Add status if not present
        if 'status' not in message:
            message['status'] = execution.status

        # Send message to websocket group
        group_name = f'crew_{crew_id}_kanban'
        async_to_sync(channel_layer.group_send)(
            group_name,
            message
        )
        #logger.debug(f"Sent WebSocket message to group {group_name}: {message}")
    except Exception as e:
        logger.error(f"Error sending WebSocket message: {str(e)}") 