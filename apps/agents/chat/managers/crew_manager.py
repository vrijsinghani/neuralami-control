import logging
from typing import Optional, Dict, Any
from django.core.cache import cache
from django.utils import timezone
from apps.agents.models import CrewExecution

logger = logging.getLogger(__name__)

class CrewManager:
    """Manages message context for crew chats"""
    
    def __init__(self):
        self.execution = None
        self.context_key = None
    
    async def initialize(self, execution: CrewExecution):
        """Initialize message context for crew execution"""
        self.execution = execution
        self.context_key = f"crew_chat_context_{execution.id}"
        
        # Initialize context in cache if not exists
        if not cache.get(self.context_key):
            # Create base context
            context = {
                'messages': [],
                'task_outputs': {},
                'current_task': None,
                'execution_id': execution.id,
                'current_date': timezone.now().strftime("%Y-%m-%d")
            }
            
            cache.set(self.context_key, context, timeout=3600)  # 1 hour timeout
    
    async def add_message_to_context(self, message: str):
        """Add a message to the crew chat context"""
        if not self.context_key:
            raise ValueError("Context not initialized")
            
        try:
            context = cache.get(self.context_key, {})
            messages = context.get('messages', [])
            
            # Add message to context
            messages.append({
                'content': message,
                'timestamp': str(timezone.now()),
                'is_human': True
            })
            
            # Keep only last 50 messages
            if len(messages) > 50:
                messages = messages[-50:]
            
            context['messages'] = messages
            cache.set(self.context_key, context, timeout=3600)
            
        except Exception as e:
            logger.error(f"Error adding message to context: {str(e)}")
            raise
    
    async def add_task_output(self, task_id: int, output: Dict[str, Any]):
        """Add task output to context"""
        if not self.context_key:
            raise ValueError("Context not initialized")
            
        try:
            context = cache.get(self.context_key, {})
            task_outputs = context.get('task_outputs', {})
            
            # Add task output
            task_outputs[str(task_id)] = output
            context['task_outputs'] = task_outputs
            
            cache.set(self.context_key, context, timeout=3600)
            
        except Exception as e:
            logger.error(f"Error adding task output: {str(e)}")
            raise
    
    async def get_context(self) -> Dict[str, Any]:
        """Get current crew chat context"""
        if not self.context_key:
            raise ValueError("Context not initialized")
            
        return cache.get(self.context_key, {})
    
    async def update_current_task(self, task_id: Optional[int]):
        """Update current task in context"""
        if not self.context_key:
            raise ValueError("Context not initialized")
            
        try:
            context = cache.get(self.context_key, {})
            context['current_task'] = task_id
            cache.set(self.context_key, context, timeout=3600)
            
        except Exception as e:
            logger.error(f"Error updating current task: {str(e)}")
            raise 