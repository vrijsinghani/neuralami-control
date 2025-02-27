import uuid
from typing import Optional
from django.contrib.auth import get_user_model
from apps.agents.models import (
    Conversation,
    CrewChatSession,
    ChatMessage,
    CrewExecution
)
from apps.agents.chat.managers.message_manager import MessageManager
from apps.agents.chat.managers.crew_manager import CrewManager
from apps.agents.chat.history import DjangoCacheMessageHistory
from langchain_core.messages import HumanMessage, AIMessage
import logging
import json
import re  # Add import for regex

User = get_user_model()
logger = logging.getLogger(__name__)

class CrewChatService:
    """Service for handling crew chat operations"""
    def __init__(self, user, conversation=None):
        self.user = user
        self.conversation = conversation
        self.websocket_handler = None
        self.message_manager = MessageManager(
            conversation_id=conversation.id if conversation else None,
            session_id=conversation.session_id if conversation else None
        )
        self.crew_manager = CrewManager()
        self.crew_execution = None
        self.message_history = None  # Will be initialized in initialize_chat
    
    async def initialize_chat(self, crew_execution):
        """Initialize a new crew chat session"""
        try:
            self.crew_execution = crew_execution
            
            if not self.conversation:
                self.conversation = await Conversation.objects.acreate(
                    session_id=uuid.uuid4(),
                    user=self.user,
                    participant_type='crew',
                    crew_execution=crew_execution,
                    title="..."  # Add default title to match agent chat behavior
                )
            
            # Get or create chat session
            session = await CrewChatSession.objects.filter(
                conversation=self.conversation,
                crew_execution=crew_execution
            ).afirst()
            
            if not session:
                session = await CrewChatSession.objects.acreate(
                    conversation=self.conversation,
                    crew_execution=crew_execution,
                    status='active'
                )
            
            # Initialize message manager with conversation
            self.message_manager.conversation_id = self.conversation.id
            self.message_manager.session_id = self.conversation.session_id
            
            # Initialize message history if not already set
            if not self.message_history:
                self.message_history = DjangoCacheMessageHistory(
                    session_id=self.conversation.session_id,
                    conversation_id=self.conversation.id
                )
            
            # Initialize crew manager with execution
            await self.crew_manager.initialize(crew_execution)
            
            logger.info(f"Initialized crew chat for execution {crew_execution.id}")
            return self.conversation
            
        except Exception as e:
            logger.error(f"Error initializing crew chat: {str(e)}")
            raise
    
    async def handle_message(self, message):
        """Handle incoming message for crew chat"""
        try:
            # Get the crew chat session
            session = await CrewChatSession.objects.filter(conversation=self.conversation).afirst()
            if not session:
                logger.error("No crew chat session found")
                return
            
            # Add message to crew context if needed
            if self.crew_manager:
                await self.crew_manager.add_message_to_context(message)
            
        except Exception as e:
            logger.error(f"Error handling crew message: {str(e)}")
            raise
    
    async def send_crew_message(self, content: str, task_id: Optional[int] = None):
        """Send message from crew to chat"""
        try:
            if not content:
                logger.warning("Empty content in crew message, skipping")
                return

            logger.debug(f"Sending crew message: {content[:100]}...")
                
            # Save message in history first
            if not self.message_history:
                logger.error("Message history not initialized")
                return
                
            stored_message = await self.message_history.add_message(
                AIMessage(content=content)
            )
            
            # Save in database
            message = await ChatMessage.objects.acreate(
                conversation=self.conversation,
                content=content,
                user=self.user,
                is_agent=True,
                task_id=task_id
            )
            
            if self.websocket_handler:
                message_data = {
                    'task_id': task_id,
                    'timestamp': message.timestamp.isoformat(),
                    'id': str(stored_message.id) if stored_message else str(message.id)
                }

                # Format message based on content type
                if content.startswith(('Using tool:', 'Tool Start:')):
                    # Extract tool name and input
                    tool_match = re.search(r'^(?:Using tool:|Tool Start:)\s*(.*?)(?:\s*-\s*|\n)(.*)$', content)
                    if tool_match:
                        tool_name = tool_match.group(1).strip()
                        tool_input = tool_match.group(2).strip()
                        message_data.update({
                            'type': 'tool_start',
                            'content': {
                                'tool': tool_name,
                                'input': tool_input
                            }
                        })
                    else:
                        # Fallback if parsing fails
                        message_data.update({
                            'type': 'crew_message',
                            'message': content
                        })

                elif content.startswith(('Tool Result:', 'Tool result:')):
                    try:
                        # Extract and parse JSON result
                        result_content = re.sub(r'^(?:Tool Result:|Tool result:)', '', content, 1).strip()
                        json_data = json.loads(result_content)
                        message_data.update({
                            'type': 'tool_result',
                            'content': json_data
                        })
                    except json.JSONDecodeError:
                        # Fallback if JSON parsing fails
                        message_data.update({
                            'type': 'tool_result',
                            'content': {
                                'type': 'text',
                                'data': result_content
                            }
                        })

                elif content.startswith('Tool Error:'):
                    error_message = content.replace('Tool Error:', '', 1).strip()
                    message_data.update({
                        'type': 'error',
                        'content': {
                            'error': error_message
                        }
                    })

                else:
                    # Regular crew message
                    message_data.update({
                        'type': 'crew_message',
                        'message': content
                    })

                # Send formatted message
                await self.websocket_handler.send_json(message_data)
            
            logger.debug(f"Crew message saved successfully with ID: {message.id}")
            return message
            
        except Exception as e:
            logger.error(f"Error sending crew message: {str(e)}")
            raise
