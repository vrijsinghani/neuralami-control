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
    execution = CrewExecution.objects.get(id=execution_id)
    update_execution_status(execution, 'WAITING_FOR_HUMAN_INPUT', task_id=None)
    log_crew_message(execution, f"Human input required: {prompt}", agent='Human Input Requested', human_input_request=prompt)
    
    input_key = f"human_input_{execution_id}_{prompt[:20]}"
    cache.set(input_key, prompt, timeout=3600)  # 1 hour timeout
    
    async_to_sync(channel_layer.group_send)(
        f"crew_execution_{execution_id}",
        {
            "type": "crew_execution_update",
            "status": "WAITING_FOR_HUMAN_INPUT",
            "human_input_request": prompt
        }
    )
    
    max_wait_time = 3600  # 1 hour
    start_time = time.time()
    while time.time() - start_time < max_wait_time:
        response = cache.get(f"{input_key}_response")
        if response:
            cache.delete(input_key)
            cache.delete(f"{input_key}_response")
            return response
        time.sleep(1)
    
    return "No human input received within the specified time."

def custom_input_handler(prompt, execution_id):
    logger.debug(f"Custom input handler called for execution {execution_id} with prompt: {prompt}")
    execution = CrewExecution.objects.get(id=execution_id)
    update_execution_status(execution, 'WAITING_FOR_HUMAN_INPUT', task_id=None)
    log_crew_message(execution, prompt or "Input required", agent='Human Input Requested', human_input_request=prompt or "Input required")
    
    input_key = f'human_input_request_{execution_id}'
    response_key = f"{input_key}_response"
    cache.set(input_key, prompt or "Input required", timeout=3600)
    
    async_to_sync(channel_layer.group_send)(
        f"crew_execution_{execution_id}",
        {
            "type": "crew_execution_update",
            "status": "WAITING_FOR_HUMAN_INPUT",
            "human_input_request": prompt or "Input required"
        }
    )
    
    # Wait for the input (with a timeout)
    timeout = 300  # 5 minutes timeout
    poll_interval = 1  # Check every second
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        user_input = cache.get(response_key)
        
        if user_input is not None:
            # Clear the cache
            cache.delete(input_key)
            cache.delete(response_key)
            
            log_crew_message(execution, f"Received human input: {user_input}", agent='Human')
            update_execution_status(execution, 'RUNNING', task_id=None)
            
            return user_input
       
        time.sleep(poll_interval)
    
    logger.warning(f"Timeout waiting for human input in execution {execution_id}")
    raise TimeoutError("No user input received within the timeout period") 