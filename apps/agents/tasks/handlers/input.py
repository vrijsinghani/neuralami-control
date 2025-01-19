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
    
    # Send the human input request via message bus
    message_bus.publish('execution_update', {
        'status': 'WAITING_FOR_HUMAN_INPUT',
        'message': prompt,
        'stage': {
            'stage_type': 'human_input_request',
            'title': 'Human Input Required',
            'content': prompt,
            'status': 'waiting_for_human_input',
            'agent': 'System',
            'type': 'message',
            'completed': False,
            'chat_message_prompts': [
                {
                    'role': 'system',
                    'content': prompt
                }
            ]
        }
    })
    
    # Log the request via message bus
    message_bus.publish('agent_action', {
        'agent_role': 'Human Input Requested',
        'log': f"Human input required: {prompt}",
        'human_input_request': prompt
    })
    
    # Wait for input
    max_wait_time = 3600  # 1 hour
    start_time = time.time()
    logger.debug("Starting wait loop for input")
    
    while time.time() - start_time < max_wait_time:
        response = cache.get(input_key)
        logger.debug(f"Checking cache key {input_key}, got: {response}")
        
        if response:
            logger.debug(f"Breaking loop - received response: {response}")
            # Send status update via message bus
            message_bus.publish('execution_update', {
                'status': 'RUNNING',
                'message': f"Received human input: {response}"
            })
            
            # Log the received input via message bus
            message_bus.publish('agent_action', {
                'agent_role': 'Human',
                'log': f"Received human input: {response}"
            })
            
            return response
            
        time.sleep(1)
    
    return "No human input received within the specified time."