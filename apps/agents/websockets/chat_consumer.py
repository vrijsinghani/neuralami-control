from .base import BaseWebSocketConsumer
from .handlers.agent_handler import AgentHandler
from .services.crew_chat_service import CrewChatService
from ..tools.manager import AgentToolManager
from ..clients.manager import ClientDataManager
from ..chat.history import DjangoCacheMessageHistory
from ..models import Conversation, CrewExecution
import logging
import uuid
import json
from datetime import datetime
from urllib.parse import parse_qs
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import (
    BaseMessage, 
    HumanMessage, 
    AIMessage,
    messages_from_dict, 
    messages_to_dict
)

logger = logging.getLogger(__name__)

class ChatConsumer(BaseWebSocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tool_manager = AgentToolManager()
        self.client_manager = ClientDataManager()
        self.session_id = None
        self.group_name = None
        self.agent_handler = AgentHandler(self)
        self.is_connected = False
        self.message_history = None
        self.crew_chat_service = None  # Will be initialized if this is a crew chat

    async def send_json(self, content):
        """Override to add logging"""
        #logger.debug(f"Sending message: {content}")
        await super().send_json(content)

    async def connect(self):
        if self.is_connected:
            return

        try:
            # Get session ID from query parameters
            query_string = self.scope.get('query_string', b'').decode()
            params = dict(param.split('=') for param in query_string.split('&') if param)
            self.session_id = params.get('session')
            
            if not self.session_id:
                logger.error("No session ID provided")
                await self.close()
                return
                
            self.user = self.scope.get("user")
            if not self.user or not self.user.is_authenticated:
                logger.error("User not authenticated")
                await self.close()
                return
        
            logger.debug(f"Connecting websocket for user {self.user.id} with session {self.session_id}")
                
            # Get or create conversation first
            conversation = await self.get_or_create_conversation()
            if not conversation:
                logger.error("Failed to get/create conversation")
                await self.close()
                return
            
            logger.debug(f"Found conversation {conversation.id} with title: {conversation.title}")
            logger.debug(f"Conversation participant type: {conversation.participant_type}")
                
            self.group_name = f"chat_{self.session_id}"

            # Initialize appropriate service based on participant type
            if conversation.participant_type == 'crew':
                self.crew_chat_service = CrewChatService(self.user, conversation)
                self.crew_chat_service.websocket_handler = self
                if conversation.crew_execution:
                    await self.crew_chat_service.initialize_chat(conversation.crew_execution)
            
            # Initialize message history (used by both agent and crew chats)
            self.message_history = DjangoCacheMessageHistory(
                session_id=self.session_id,
                agent_id=conversation.agent_id if conversation.participant_type == 'agent' else None,
                conversation_id=conversation.id
            )
            
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
            self.is_connected = True
            
            # Send historical messages
            messages = await self.message_history.aget_messages()
            logger.debug(f"Retrieved {len(messages)} historical messages")
            
            for msg in messages:
                message_type = 'agent_message' if isinstance(msg, AIMessage) else 'user_message'
                if conversation.participant_type == 'crew':
                    message_type = 'crew_message' if isinstance(msg, AIMessage) else 'user_message'
                
                await self.send_json({
                    'type': message_type,
                    'message': msg.content,
                    'timestamp': conversation.updated_at.isoformat(),
                    'id': msg.additional_kwargs.get('id')
                })
            
            await self.send_json({
                'type': 'system_message',
                'message': 'Connected to chat server',
                'connection_status': 'connected',
                'session_id': self.session_id,
                'participant_type': conversation.participant_type
            })
            
        except Exception as e:
            logger.error(f"Error in connect: {str(e)}", exc_info=True)
            await self.close()
            return

    async def get_or_create_conversation(self):
        try:
            # Get existing conversation
            conversation = await Conversation.objects.filter(
                session_id=self.session_id,
                user=self.user
            ).afirst()
            
            if not conversation:
                # Create new conversation with placeholder title
                conversation = await Conversation.objects.acreate(
                    session_id=self.session_id,
                    user=self.user,
                    title="...",  # Will be updated with first message
                    participant_type='agent'  # Default to agent chat
                )
            
            return conversation
            
        except Exception as e:
            logger.error(f"Error getting/creating conversation: {str(e)}")
            return None

    async def update_conversation(self, message, agent_id=None, client_id=None):
        try:
            conversation = await Conversation.objects.filter(
                session_id=self.session_id
            ).afirst()
            
            if conversation:
                # Update title if it's still the default
                if conversation.title == "...":
                    # Clean and truncate the message for the title
                    title = message.strip().replace('\n', ' ')[:50]
                    # Add ellipsis if truncated
                    if len(message) > 50:
                        title += "..."
                    conversation.title = title
                
                # Update agent only if this is an agent chat
                if conversation.participant_type == 'agent' and agent_id:
                    conversation.agent_id = agent_id
                
                # Update client if provided
                if client_id:
                    conversation.client_id = client_id
                    
                await conversation.asave()
                #logger.info(f"Updated conversation: {conversation.id} with title: {conversation.title}")
                
        except Exception as e:
            logger.error(f"Error updating conversation: {str(e)}")

    async def execution_update(self, event):
        """Handle execution status updates from crew tasks"""
        try:
            await self.send_json({
                'type': 'execution_update',
                'status': event.get('status'),
                'message': event.get('message'),
                'task_index': event.get('task_index'),
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Error sending execution update: {str(e)}")

    async def receive(self, text_data=None, bytes_data=None):
        try:
            # Handle binary data if present
            if bytes_data:
                data = await self.handle_binary_message(bytes_data)
            else:
                data = json.loads(text_data)

            # Process keep-alive messages
            if data.get('type') == 'keep_alive':
                await self.message_handler.handle_keep_alive()
                return

            # Process message - responses come via callback_handler
            await self.process_message(data)

        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON decode error: {str(e)}")
            await self.message_handler.handle_message(
                'Invalid message format', is_agent=True, error=True
            )
        except Exception as e:
            logger.error(f"❌ Error: {str(e)}")
            await self.message_handler.handle_message(
                'Internal server error', is_agent=True, error=True)

    async def process_message(self, data):
        """Primary entry point for all messages"""
        try:
            # Handle crew start request
            if data.get('type') == 'start_crew':
                crew_id = data.get('crew_id')
                if not crew_id:
                    raise ValueError('Missing crew ID')

                # Get conversation
                conversation = await Conversation.objects.filter(session_id=self.session_id).afirst()
                if not conversation:
                    raise ValueError('No active conversation found')

                # Create crew execution
                execution = await CrewExecution.objects.acreate(
                    crew_id=crew_id,
                    status='PENDING',
                    user=self.scope['user'],
                    conversation=conversation
                )
                
                # Update conversation
                conversation.participant_type = 'crew'
                conversation.crew_execution = execution
                await conversation.asave()

                # Initialize crew chat service
                self.crew_chat_service = CrewChatService(self.scope['user'], conversation)
                self.crew_chat_service.websocket_handler = self
                await self.crew_chat_service.initialize_chat(execution)

                # Start the execution
                from ..tasks import execute_crew
                task = execute_crew.delay(execution.id)
                
                # Update execution with task ID
                execution.task_id = task.id
                await execution.asave()

                # Send confirmation
                await self.send_json({
                    'type': 'system_message',
                    'message': 'Starting crew execution...',
                    'timestamp': datetime.now().isoformat()
                })
                return

            # Extract message data
            message = data.get('message', '').strip()
            agent_id = data.get('agent_id')
            model_name = data.get('model')
            client_id = data.get('client_id')
            is_edit = data.get('type') == 'edit'  # Check for edit type
            message_id = data.get('message_id')  # Get message ID for edits

            logger.debug(f"Processing message: type={data.get('type')}, message_id={message_id}, is_edit={is_edit}")

            if not message and not is_edit:  # Allow empty message for edit
                raise ValueError('Missing required fields')

            # Handle message editing if needed
            if is_edit:
                if not message_id:
                    raise ValueError('Missing message ID for edit')
                logger.debug(f"Handling edit for message {message_id}")
                await self.message_history.handle_edit(message_id)
                return  # Return early for edit messages

            # Get current conversation to check participant type
            conversation = await Conversation.objects.filter(session_id=self.session_id).afirst()
            if not conversation:
                raise ValueError('No active conversation found')

            # Initialize crew chat service if needed
            if conversation.participant_type == 'crew' and not self.crew_chat_service:
                self.crew_chat_service = CrewChatService(self.scope['user'], conversation)
                self.crew_chat_service.websocket_handler = self

            # Update conversation with agent and client info (only for agent chats)
            if conversation.participant_type == 'agent':
                await self.update_conversation(message, agent_id, client_id)
                
                # Ensure message history has correct agent_id
                if not self.message_history or self.message_history.agent_id != agent_id:
                    self.message_history = DjangoCacheMessageHistory(
                        session_id=self.session_id,
                        agent_id=agent_id,
                        conversation_id=conversation.id
                    )

            # Store user message and get the stored message object
            stored_message = await self.message_history.add_message(
                HumanMessage(content=message)
            )

            # Send user message with ID
            await self.send_json({
                'type': 'user_message',
                'message': message,
                'timestamp': datetime.now().isoformat(),
                'id': str(stored_message.id) if stored_message else None
            })
            
            # Handle crew chat messages if this is a crew chat
            if conversation.participant_type == 'crew':
                if not self.crew_chat_service:
                    raise ValueError('Crew chat service not initialized')
                await self.crew_chat_service.handle_message(message)
                return

            # Process with agent - responses come via callback_handler
            await self.agent_handler.process_response(
                message, agent_id, model_name, client_id
            )

        except Exception as e:
            logger.error(f"Error processing message: {str(e)}", exc_info=True)
            await self.send_json({
                'type': 'error',
                'message': f'Error processing message: {str(e)}',
                'timestamp': datetime.now().isoformat()
            })

    async def receive_json(self, content):
        """Disabled in favor of receive() to prevent duplicate message processing"""
        pass