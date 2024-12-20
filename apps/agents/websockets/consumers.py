import json
import logging
from django.db import models
from django.db.models import Q
from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from apps.agents.models import Agent, Conversation
from apps.agents.services import ChatService
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        """Handle WebSocket connection"""
        try:
            # Get session and agent IDs from URL route
            self.session_id = self.scope['url_route']['kwargs']['session_id']
            self.agent_id = self.scope['url_route']['kwargs'].get('agent_id')
            self.user = self.scope.get('user')
            
            logger.debug(f"Connecting websocket for user {self.user.id if self.user else 'anonymous'} with session {self.session_id}")
            
            # Get or create conversation
            self.conversation = await self._get_or_create_conversation()
            if self.conversation:
                logger.debug(f"Found conversation {self.conversation.id} with title: {self.conversation.title}")
            
            # Get the agent from the database
            self.agent = await database_sync_to_async(Agent.objects.get)(id=self.agent_id)
            
            # Initialize chat service
            self.chat_service = ChatService(
                agent=self.agent,
                model_name=self.agent.llm,
                client_data=None,  # Will be set based on conversation context
                callback_handler=self,
                session_id=self.session_id
            )
            
            await self.chat_service.initialize()
            
            # Send historical messages
            await self._send_history()
            
            await self.accept()
            
        except Exception as e:
            logger.error(f"Error in connect: {str(e)}", exc_info=True)
            await self.close()

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        pass

    async def receive(self, text_data):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(text_data)
            
            if data.get('type') == 'agent_change':
                # Handle agent change
                new_agent = await database_sync_to_async(Agent.objects.get)(id=data['agent_id'])
                self.chat_service.update_agent(new_agent)
                return
                
            # Process the message
            message = data.get('message', '')
            is_edit = data.get('is_edit', False)
            
            if message.strip():  # Only process non-empty messages
                await self.chat_service.process_message(message, is_edit)
                
        except json.JSONDecodeError:
            logger.error("Invalid JSON received")
        except Exception as e:
            logger.error(f"Error in receive: {str(e)}", exc_info=True)
            await self.send(text_data=json.dumps({
                'error': str(e)
            }))

    async def _get_or_create_conversation(self):
        """Get existing conversation or create new one"""
        try:
            # Try to get existing conversation
            conversation = await database_sync_to_async(Conversation.objects.filter)(
                Q(session_id=self.session_id) | Q(id=self.session_id)
            ).first()
            
            if not conversation and self.user:
                # Create new conversation if none exists
                conversation = await database_sync_to_async(Conversation.objects.create)(
                    user=self.user,
                    session_id=self.session_id,
                    agent_id=self.agent_id,
                    title="..."  # Will be updated with first message
                )
            
            return conversation
            
        except Exception as e:
            logger.error(f"Error getting/creating conversation: {str(e)}", exc_info=True)
            return None

    async def _send_history(self):
        """Send conversation history to the client"""
        try:
            # Get historical messages
            messages = await self.chat_service.message_manager.get_messages()
            logger.debug(f"Retrieved {len(messages)} historical messages")
            
            # Send each message
            for message in messages:
                logger.debug(f"Processing message: {type(message)} | content: {message.content[:100]}...")
                
                if isinstance(message, HumanMessage):
                    await self.send(text_data=json.dumps({
                        'type': 'user_message',
                        'content': message.content
                    }))
                else:
                    await self.send(text_data=json.dumps({
                        'type': 'assistant_message',
                        'content': message.content
                    }))
                    
        except Exception as e:
            logger.error(f"Error sending history: {str(e)}", exc_info=True)