import logging
import time
from django.core.cache import cache
from apps.agents.models import CrewExecution
from ..messaging.execution_bus import ExecutionMessageBus

logger = logging.getLogger(__name__)

def human_input_handler(prompt, execution_id):
    """Handle human input requests via websocket."""
    logger.debug(f"human_input_handler called with prompt: {prompt}, execution_id: {execution_id}")
    execution = CrewExecution.objects.get(id=execution_id)
    message_bus = ExecutionMessageBus(execution_id)
    
    # Get current task index from execution state
    current_task = getattr(human_input_handler, 'current_task_index', 0)
    
    # Use consistent cache key format
    input_key = f"execution_{execution_id}_task_{current_task}_input"
    logger.debug(f"Using cache key: {input_key}")
    
    # Clear any existing value for this key
    cache.delete(input_key)
    
    # Send the human input request
    message_bus.publish('human_input_request', {
        'human_input_request': prompt,
        'task_index': current_task,
        'context': {
            'execution_id': execution_id,
            'task_index': current_task
        }
    })
    
    # Wait for input
    max_wait_time = 3600  # 1 hour
    start_time = time.time()
    
    while time.time() - start_time < max_wait_time:
        response = cache.get(input_key)
        
        if response:
            logger.debug(f"Received human input: {response}")
            # Send status update
            # message_bus.publish('execution_update', {
            #     'status': 'RUNNING',
            #     'message': f"Received human input: {response}",
            #     'task_index': current_task
            # })
            return str(response)
            
        time.sleep(1)
    
    logger.warning("No human input received within timeout period")
    return "APPROVED."