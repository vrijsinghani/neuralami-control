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
    """Handle human input requests via websocket."""
    logger.debug(f"human_input_handler called with prompt: {prompt}, execution_id: {execution_id}")
    execution = CrewExecution.objects.get(id=execution_id)
    
    # Get current task index from execution state
    current_task = getattr(human_input_handler, 'current_task_index', 0)
    
    # Use consistent cache key format
    input_key = f"execution_{execution_id}_task_{current_task}_input"
    logger.debug(f"Using cache key: {input_key}")
    
    # Clear any existing value for this key
    cache.delete(input_key)
    
    # Send the execution update with the human input request
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
    
    # Update execution status
    update_execution_status(execution, 'WAITING_FOR_HUMAN_INPUT')
    
    # Log the request
    log_crew_message(execution, f"Human input required: {prompt}", agent='Human Input Requested', human_input_request=prompt)
    
    # Wait for input
    max_wait_time = 3600  # 1 hour
    start_time = time.time()
    logger.debug("Starting wait loop for input")
    
    while time.time() - start_time < max_wait_time:
        response = cache.get(input_key)
        logger.debug(f"Checking cache key {input_key}, got: {response}")
        
        if response:
            logger.debug(f"Breaking loop - received response: {response}")
            update_execution_status(execution, 'RUNNING')
            log_crew_message(execution, f"Received human input: {response}", agent='Human')
            return response
            
        time.sleep(1)
    
    return "No human input received within the specified time."