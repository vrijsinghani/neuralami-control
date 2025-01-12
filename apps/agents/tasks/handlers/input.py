import logging
import time
from django.core.cache import cache
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from apps.agents.models import CrewExecution
from ..utils.logging import log_crew_message, update_execution_status

logger = logging.getLogger(__name__)
channel_layer = get_channel_layer()

def human_input_handler(prompt, execution_id):
    """Handle human input requests via websocket.
    
    Args:
        prompt: The prompt to show to the human
        execution_id: The ID of the crew execution
        
    Returns:
        The human's response or a timeout message
    """
    logger.debug(f"human_input_handler called with prompt: {prompt}, execution_id: {execution_id}")
    execution = CrewExecution.objects.get(id=execution_id)
    
    # Send the execution update with the human input request
    logger.debug("Sending execution update with human input request")
    async_to_sync(channel_layer.group_send)(
        f"crew_{execution.crew_id}_kanban",
        {
            "type": "execution_update",
            "execution_id": execution_id,
            "status": "WAITING_FOR_HUMAN_INPUT",
            "message": None,
            "stage": {
                "stage_type": "human_input_request",
                "title": "Human Input Required",
                "content": prompt,
                "status": "waiting_for_human_input",
                "agent": "System",
                "type": "message",
                "completed": False,
                "chat_message_prompts": [
                    {
                        "role": "system",
                        "content": prompt
                    }
                ]
            }
        }
    )
    
    # Then update the execution status
    logger.debug("Updating execution status")
    update_execution_status(execution, 'WAITING_FOR_HUMAN_INPUT')
    
    # Log the request
    logger.debug("Logging crew message")
    log_crew_message(execution, f"Human input required: {prompt}", agent='Human Input Requested', human_input_request=prompt)
    
    # Wait for human input
    input_key = f"human_input_{execution_id}_{prompt[:20]}"
    cache.set(input_key, prompt, timeout=3600)  # 1 hour timeout
    
    max_wait_time = 3600  # 1 hour
    start_time = time.time()
    while time.time() - start_time < max_wait_time:
        response = cache.get(f"{input_key}_response")
        if response:
            cache.delete(input_key)
            cache.delete(f"{input_key}_response")
            log_crew_message(execution, f"Received human input: {response}", agent='Human')
            update_execution_status(execution, 'RUNNING')
            return response
        time.sleep(1)
    
    return "No human input received within the specified time."