import logging
from datetime import datetime
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from apps.agents.models import CrewExecution, ChatMessage

logger = logging.getLogger(__name__)
channel_layer = get_channel_layer()

class ExecutionMessageBus:
    """Central message bus for crew execution events"""
    def __init__(self, execution_id):
        self.execution_id = execution_id
        self.execution = CrewExecution.objects.get(id=execution_id)
        self.handlers = []
        
        # Register handlers based on execution type
        if self.execution.conversation:
            self.handlers.append(ChatMessageHandler(self.execution))
        self.handlers.append(KanbanMessageHandler(self.execution))
    
    def publish(self, event_type, data):
        """Publish event to all handlers"""
        for handler in self.handlers:
            try:
                handler.handle(event_type, data)
            except Exception as e:
                logger.error(f"Error in handler {handler.__class__.__name__}: {str(e)}")

class BaseMessageHandler:
    """Base class for execution message handlers"""
    def __init__(self, execution):
        self.execution = execution
    
    def handle(self, event_type, data):
        handler = getattr(self, f"handle_{event_type}", None)
        if handler:
            handler(data)

class ChatMessageHandler(BaseMessageHandler):
    """Handles messages for chat UI"""
    def handle_agent_action(self, data):
        content = f" {data['agent_role']}: {data['log']}"
        self._send_chat_message(content, data['agent_role'], data['task_index'])
    
    def handle_agent_finish(self, data):
        content = f" {data['agent_role']}: {data['output']}"
        self._send_chat_message(content, data['agent_role'], data['task_index'])
    
    def handle_execution_status(self, data):
        content = f" {data['status']}: {data.get('message', '')}"
        self._send_chat_message(content, "System", None)
    
    def _send_chat_message(self, content, agent_role, task_index):
        # Send via websocket
        async_to_sync(channel_layer.group_send)(
            f'chat_{self.execution.conversation.session_id}',
            {
                'type': 'crew_message',
                'message': content,
                'agent': agent_role,
                'task_id': task_index,
                'timestamp': datetime.now().isoformat()
            }
        )
        
        # Store in history
        ChatMessage.objects.create(
            conversation=self.execution.conversation,
            content=content,
            is_agent=True,
            agent_role=agent_role
        )

class KanbanMessageHandler(BaseMessageHandler):
    """Handles messages for kanban UI"""
    def handle_agent_action(self, data):
        if data.get('log'):
            self._send_execution_update('task_action', data['log'], data)
    
    def handle_agent_finish(self, data):
        if data.get('output'):
            self._send_execution_update('task_output', data['output'], data)
    
    def handle_execution_status(self, data):
        # Only send status update if there's a status change or message
        if data.get('message') or data.get('status', self.execution.status) != self.execution.status:
            self._send_execution_update('status_update', data.get('message', ''), {
                'agent_role': 'System',
                'status': data['status']
            })
    
    def _send_execution_update(self, stage_type, content, data):
        event = {
            'type': 'execution_update',
            'execution_id': self.execution.id,
            'status': data.get('status', self.execution.status),
            'stage': {
                'stage_type': stage_type,
                'title': stage_type.replace('_', ' ').title(),
                'content': content,
                'status': 'completed',
                'agent': data.get('agent_role', 'System')
            }
        }
        
        # Send update via websocket
        async_to_sync(channel_layer.group_send)(
            f'kanban_{self.execution.id}',
            event
        )
