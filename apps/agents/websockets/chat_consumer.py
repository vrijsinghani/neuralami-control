from .base import BaseWebSocketConsumer
from .handlers.agent_handler import AgentHandler
from .services.crew_chat_service import CrewChatService
from ..tools.manager import AgentToolManager
from ..clients.manager import ClientDataManager
from ..chat.history import DjangoCacheMessageHistory
from ..models import Conversation, CrewExecution, ChatMessage
from django.core.cache import cache
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
from channels.db import database_sync_to_async

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

    @database_sync_to_async
    def get_crew_execution(self, conversation):
        """Safely get crew execution in async context"""
        try:
            return conversation.crew_execution
        except Exception as e:
            logger.error(f"Error getting crew execution: {str(e)}")
            return None

    @database_sync_to_async
    def get_crew(self, crew_execution):
        """Safely get crew in sync context"""
        try:
            return crew_execution.crew
        except Exception as e:
            logger.error(f"Error getting crew: {str(e)}")
            return None

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
            
            # Set organization context from session
            await super().connect()
                
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
                crew_execution = await self.get_crew_execution(conversation)
                if crew_execution:
                    await self.crew_chat_service.initialize_chat(crew_execution)
            
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

    async def disconnect(self, close_code):
        """Override to clean up resources"""
        # Clear organization context
        await super().disconnect(close_code)
        
        # Clear group membership
        if self.group_name:
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
        
        # Set connected flag to false
        self.is_connected = False
        
        logger.debug(f"WebSocket disconnected with code {close_code}")

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

    @database_sync_to_async
    def set_cache_value(self, key, value):
        """Safely set cache value in async context"""
        cache.set(key, value)

    @database_sync_to_async
    def get_conversation_details(self, conversation):
        """Get conversation details in sync context"""
        details = {
            'participant_type': conversation.participant_type,
            'has_crew_execution': hasattr(conversation, 'crew_execution'),
            'title': conversation.title
        }
        
        # Get crew name if this is a crew chat
        if conversation.participant_type == 'crew' and conversation.crew_execution:
            details['crew_name'] = conversation.crew_execution.crew.name
        
        return details

    async def update_conversation(self, message, agent_id=None, client_id=None):
        """Update conversation details"""
        try:
            conversation = await Conversation.objects.filter(
                session_id=self.session_id
            ).afirst()
            
            if conversation:
                # Get conversation details in sync context
                details = await self.get_conversation_details(conversation)
                
                # Update title if it's still the default and we have a message
                if details['title'] == "..." and message:
                    # Format the message part of the title
                    title_message = message.strip().replace('\n', ' ')[:50]
                    if len(message) > 50:
                        title_message += "..."
                    
                    # Set title to just the message - participant name is shown separately in UI
                    conversation.title = title_message
                
                # Update agent/crew info based on participant type
                if details['participant_type'] == 'agent' and agent_id:
                    conversation.agent_id = agent_id
                
                # Update client if provided
                if client_id:
                    conversation.client_id = client_id
                    
                await conversation.asave()
                
        except Exception as e:
            logger.error(f"Error updating conversation: {str(e)}")
            raise

    async def execution_update(self, event):
        """Handle execution status updates from crew tasks"""
        try:
            status = event.get('status')
            message = event.get('message')
            task_index = event.get('task_index')
            
            # Only send status update - no message content
            await self.send_json({
                'type': 'execution_update',
                'status': status,
                'task_index': task_index,
                'timestamp': datetime.now().isoformat()
            })

            # If there's a message, send it as a crew message
            if message and self.crew_chat_service:
                await self.crew_chat_service.send_crew_message(
                    content=message,
                    task_id=task_index
                )

        except Exception as e:
            logger.error(f"Error sending execution update: {str(e)}")

    async def crew_message(self, event):
        """Handle crew messages from tasks"""
        try:
            if self.crew_chat_service:
                await self.crew_chat_service.send_crew_message(
                    content=event.get('message'),
                    task_id=event.get('task_id')
                )
        except Exception as e:
            logger.error(f"Error handling crew message: {str(e)}")

    async def receive(self, text_data=None, bytes_data=None):
        try:
            # Handle binary data if present
            if bytes_data:
                data = await self.handle_binary_message(bytes_data)
            else:
                # Handle text data
                if isinstance(text_data, dict):
                    # Already parsed JSON (from websocket_receive)
                    data = text_data
                else:
                    try:
                        data = json.loads(text_data)
                    except (json.JSONDecodeError, TypeError):
                        # If not JSON or None, treat as plain text message
                        data = {
                            'type': 'user_message',
                            'message': text_data or ''
                        }

            logger.debug(f"Received data: {data}")

            # Process keep-alive messages
            if data.get('type') == 'keep_alive':
                return

            # Process message
            await self.process_message(data)

        except Exception as e:
            logger.error(f"❌ Error: {str(e)}", exc_info=True)
            await self.send_json({
                'type': 'error',
                'message': f'Error processing message: {str(e)}',
                'timestamp': datetime.now().isoformat()
            })

    async def process_message(self, data):
        """Primary entry point for all messages"""
        try:
            # Handle human input response
            if data.get('context', {}).get('is_human_input'):
                context = data.get('context', {})
                message = data.get('message')
                
                # Store response in cache
                input_key = f"execution_{context.get('execution_id')}_task_{context.get('task_index')}_input"
                logger.debug(f"Storing human input response in cache with key: {input_key}")
                await self.set_cache_value(input_key, message)
                
                # Send user message back to show in chat
                await self.send_json({
                    'type': 'user_message',
                    'message': message,
                    'timestamp': datetime.now().isoformat()
                })
                return

            # Handle crew start request
            if data.get('type') == 'start_crew':
                crew_id = data.get('crew_id')
                client_id = data.get('client_id')
                if not crew_id:
                    raise ValueError('Missing crew ID')
                
                # Get client if client_id is provided
                client = None
                if client_id:
                    from apps.seo_manager.models import Client
                    try:
                        client = await database_sync_to_async(Client.objects.get)(id=client_id)
                    except Client.DoesNotExist:
                        logger.warning(f"Client with ID {client_id} not found")
                    except Exception as e:
                        logger.warning(f"Error retrieving client with ID {client_id}: {str(e)}")

                # Get conversation
                conversation = await Conversation.objects.filter(session_id=self.session_id).afirst()
                if not conversation:
                    raise ValueError('No active conversation found')

                # Create crew execution
                execution = await CrewExecution.objects.acreate(
                    crew_id=crew_id,
                    status='PENDING',
                    user=self.scope['user'],
                    conversation=conversation,
                    client=client,  # Set the client
                    inputs={
                        'client_id': client_id if client_id else None
                    }
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

            #logger.debug(f"Processing message: type={data.get('type')}, message_id={message_id}, is_edit={is_edit}")

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

            # Get conversation details in sync context
            details = await self.get_conversation_details(conversation)

            # Initialize crew chat service if needed
            if details['participant_type'] == 'crew' and not self.crew_chat_service:
                self.crew_chat_service = CrewChatService(self.scope['user'], conversation)
                self.crew_chat_service.websocket_handler = self
                self.crew_chat_service.message_history = self.message_history  # Share the same message history

            # Update conversation with agent and client info
            await self.update_conversation(message, agent_id, client_id)

            # Store user message in history and database
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
            if details['participant_type'] == 'crew':
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

    async def human_input_request(self, event):
        """Handle human input request from crew tasks"""
        try:
            # Extract prompt from event - it could be in different fields
            prompt = event.get('human_input_request') or event.get('prompt') or event.get('message', 'Input required')
            
            # Send as a crew message
            await self.send_json({
                'type': 'crew_message',
                'message': str(prompt),  # Ensure it's a string
                'context': {  # Include context for handling the response
                    'is_human_input': True,
                    'execution_id': event.get('context', {}).get('execution_id'),
                    'task_index': event.get('task_index')
                },
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Error sending human input request: {str(e)}")