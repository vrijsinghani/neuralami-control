import logging
import time
from datetime import datetime
from apps.agents.models import CrewExecution, ExecutionStage, CrewMessage, Task
from ..messaging.execution_bus import ExecutionMessageBus

logger = logging.getLogger(__name__)

def update_execution_status(execution, status, message=None, task_index=None):
    """Update execution status and notify all UIs"""
    try:
        execution.status = status
        execution.save()
        
        # Create execution stage
        if message:
            ExecutionStage.objects.create(
                execution=execution,
                stage_type='status_update',
                title=status,
                content=message,
                status=status.lower()
            )
        
        # Use message bus for notifications with consistent event type
        message_bus = ExecutionMessageBus(execution.id)
        message_bus.publish('execution_update', {
            'status': status,
            'message': message,
            'task_index': task_index
        })
        
    except Exception as e:
        logger.error(f"Error updating execution status: {str(e)}")

def log_crew_message(execution, content, agent=None, human_input_request=None, crewai_task_id=None, task_index=None):
    """Log crew message and send via websocket"""
    try:
        # Store message in database if there's content
        if content:
            CrewMessage.objects.create(
                execution=execution,
                content=content,
                agent=agent,
                crewai_task_id=crewai_task_id
            )
            #logger.debug(f"Stored message in database: {content[:100]}")
        else:
            logger.warning("Attempted to log an empty message, skipping database storage")

        # Send via message bus
        message_bus = ExecutionMessageBus(execution.id)
        message_bus.publish('execution_update', {
            'status': 'RUNNING',
            'message': content,
            'task_index': task_index,
            'stage': {
                'stage_type': 'agent_action',
                'title': 'Agent Action',
                'content': content,
                'status': 'in_progress',
                'agent': agent or 'System'
            }
        })

    except Exception as e:
        logger.error(f"Error in log_crew_message: {str(e)}")