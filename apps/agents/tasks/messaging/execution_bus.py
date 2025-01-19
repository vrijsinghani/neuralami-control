import logging
from datetime import datetime
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from apps.agents.models import CrewExecution, ChatMessage

logger = logging.getLogger(__name__)
channel_layer = get_channel_layer()

class ExecutionMessageBus:
    """Central message bus for crew execution events and websocket communication"""
    def __init__(self, execution_id):
        self.execution_id = execution_id
        self.execution = CrewExecution.objects.get(id=execution_id)

    def publish(self, event_type, data):
        """Publish event to all relevant interfaces"""
        try:
            logger.debug(f"Publishing event {event_type} with data: {data}")
            
            # Special handling for human input requests
            if data.get('human_input_request'):
                self._send_to_groups('human_input_request', data)
                return
                
            if event_type == 'agent_action':
                self._handle_agent_action(data)
            elif event_type == 'agent_finish':
                self._handle_agent_finish(data)
            elif event_type == 'execution_update':
                self._handle_status_update(data)
        except Exception as e:
            logger.error(f"Error publishing event {event_type}: {str(e)}")

    def _send_to_groups(self, message_type, data):
        """Send message to all relevant websocket groups"""
        try:
            logger.debug(f"Sending message to groups for execution {self.execution_id}")
            groups = []
            if self.execution.crew:
                groups.append(f'crew_{self.execution.crew.id}_kanban')
            if self.execution.conversation:
                groups.append(f'chat_{self.execution.conversation.session_id}')

            # Special handling for human input requests
            if data.get('human_input_request'):
                message = {
                    'type': 'human_input_request',
                    'execution_id': self.execution_id,
                    'prompt': data['human_input_request'],
                    'context': data.get('context', {}),
                    'task_index': data.get('task_index')
                }
            else:
                # Construct message with data first, then override with our fields
                message = {
                    **data,  # Base data first
                    'type': message_type,
                    'execution_id': self.execution_id,
                    'status': self.execution.status,
                    'task_index': data.get('task_index')  # Ensure task_index is last
                }

            logger.debug(f"Sending message: {message}")

            for group in groups:
                try:
                    async_to_sync(channel_layer.group_send)(group, message)
                    logger.debug(f"Sent message to group {group}")
                except Exception as e:
                    logger.error(f"Failed to send to group {group}: {str(e)}")

        except Exception as e:
            logger.error(f"Error in _send_to_groups: {str(e)}")

    def _handle_agent_action(self, data):
        message = {
            **data,  # Include all original data first
            'message': data['log'],
            'agent': data['agent_role'],
            'stage': {
                'stage_type': 'task_action',
                'title': 'Agent Action',
                'content': data['log'],
                'agent': data['agent_role'],
                'status': 'completed'
            }
        }
        
        self._send_to_groups('execution_update', message)
        
        if self.execution.conversation:
            self._store_chat_message(data['log'], data['agent_role'])

    def _handle_status_update(self, data):
        logger.debug(f"Handling status update with task_index: {data.get('task_index')}")
        message = {
            **data,  # Include all original data first
            'message': data.get('message'),
            'stage': {
                'stage_type': 'status_update',
                'title': 'Status Update',
                'content': data.get('message') or f'Status changed to {data["status"]}',
                'status': data['status'].lower(),
                'agent': 'System'
            }
        }
        logger.debug(f"Sending status update with task_index: {message.get('task_index')}")
        self._send_to_groups('execution_update', message)

    def _store_chat_message(self, content, agent_role):
        """Store message in chat history"""
        if self.execution.conversation:
            ChatMessage.objects.create(
                conversation=self.execution.conversation,
                content=content,
                is_agent=True,
                agent_role=agent_role
            )
