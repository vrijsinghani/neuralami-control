from .base import BaseWebSocketConsumer
from .handlers.message_handler import MessageHandler
from .handlers.agent_handler import AgentHandler
from ..tools.manager import AgentToolManager
from ..clients.manager import ClientDataManager
from ..chat.history import DjangoCacheMessageHistory
from ..models import Conversation
import logging
import uuid
import json
from datetime import datetime
from urllib.parse import parse_qs

logger = logging.getLogger(__name__)

class ChatConsumer(BaseWebSocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tool_manager = AgentToolManager()
        self.client_manager = ClientDataManager()
        self.session_id = None
        self.group_name = None
        self.message_handler = MessageHandler(self)
        self.agent_handler = AgentHandler(self)
        self.is_connected = False
        self.message_history = None

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
                
            self.group_name = f"chat_{self.session_id}"
            self.message_history = DjangoCacheMessageHistory(session_id=self.session_id)
            
            # Get or create conversation
            conversation = await self.get_or_create_conversation()
            if not conversation:
                logger.error("Failed to get/create conversation")
                await self.close()
                return
                
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
            self.is_connected = True
            
            # Send historical messages
            messages = self.message_history.messages
            for msg in messages:
                message_type = 'agent_message' if msg.type == 'ai' else 'user_message'
                message_content = msg.content
                
                # If it's an agent message, check if it's a tool usage
                if message_type == 'agent_message' and (
                    'AgentAction(tool=' in message_content or 
                    'AgentStep(action=' in message_content
                ):
                    # Send as is - the frontend will handle the formatting
                    pass
                
                await self.send_json({
                    'type': message_type,
                    'message': message_content,
                    'timestamp': conversation.updated_at.isoformat() if conversation else None
                })
            
            logger.info(f"WebSocket connected for session {self.session_id}")
            await self.send_json({
                'type': 'system_message',
                'message': 'Connected to chat server',
                'connection_status': 'connected',
                'session_id': self.session_id
            })
            
        except Exception as e:
            logger.error(f"Error in connect: {str(e)}")
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
                    title="..."  # Will be updated with first message
                )
                logger.info(f"Created new conversation: {conversation.id}")
            else:
                logger.info(f"Found existing conversation: {conversation.id}")
            
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
                
                # Update agent and client if provided
                if agent_id:
                    conversation.agent_id = agent_id
                if client_id:
                    conversation.client_id = client_id
                    
                await conversation.asave()
                logger.info(f"Updated conversation: {conversation.id} with title: {conversation.title}")
                
        except Exception as e:
            logger.error(f"Error updating conversation: {str(e)}")

    async def receive(self, text_data=None, bytes_data=None):
        try:
            # Handle binary data if present
            if bytes_data:
                data = await self.handle_binary_message(bytes_data)
            else:
                data = json.loads(text_data)
                if data.get('type') != 'keep_alive':
                    logger.debug(f"📥 Received: {text_data}")

            if data.get('type') == 'keep_alive':
                await self.message_handler.handle_keep_alive()
                return

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
        """Process incoming message data"""
        try:
            message = data.get('message', '').strip()
            agent_id = data.get('agent_id')
            model_name = data.get('model')
            client_id = data.get('client_id')

            if not message or not agent_id:
                await self.message_handler.handle_message(
                    'Missing required fields (message or agent_id)',
                    is_agent=True,
                    error=True
                )
                return

            # Update conversation details before processing
            await self.update_conversation(message, agent_id, client_id if client_id else None)

            # Echo user's message back with proper type
            logger.debug("📤 Sending user message")
            await self.send_json({
                'type': 'user_message',
                'message': message,
                'timestamp': datetime.now().isoformat()
            })

            # Process with agent
            logger.debug("🤖 Processing with agent")
            response = await self.agent_handler.process_response(
                message,
                agent_id,
                model_name,
                client_id if client_id else None
            )

            # Handle error responses
            if isinstance(response, str) and response.startswith('Error:'):
                await self.send_json({
                    'type': 'error',
                    'message': response,
                    'timestamp': datetime.now().isoformat()
                })
                return

            logger.debug("📤 Sending agent response")
            await self.send_json({
                'type': 'agent_message',
                'message': response,
                'timestamp': datetime.now().isoformat()
            })

        except Exception as e:
            logger.error(f"❌ Error: {str(e)}")
            await self.send_json({
                'type': 'error',
                'message': f"Error processing message: {str(e)}",
                'error': True
            })

    async def receive_json(self, content):
        """Handle incoming WebSocket messages"""
        try:
            message_type = content.get('type')
            
            if message_type == 'user_message':
                message = content.get('message')
                is_edit = content.get('is_edit', False)  # Get edit flag
                
                if not message:
                    return
                
                # Send message back to confirm receipt
                await self.send_json({
                    'type': 'user_message',
                    'message': message
                })
                
                # Process message with edit flag
                await self.agent_handler.process_message(
                    message=message,
                    is_edit=is_edit
                )
        except Exception as e:
            logger.error(f"Error in receive_json: {str(e)}")
            await self.send_json({
                'type': 'error',
                'message': f"Error processing message: {str(e)}",
                'error': True
            })