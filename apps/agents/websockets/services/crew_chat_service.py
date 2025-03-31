import uuid
from typing import Optional, Any
from django.contrib.auth import get_user_model
from django.conf import settings
from apps.agents.models import (
    Conversation,
    CrewChatSession,
    ChatMessage,
    CrewExecution
)
from apps.agents.chat.managers.message_manager import MessageManager
from apps.agents.chat.managers.crew_manager import CrewManager
from apps.agents.chat.managers.token_manager import TokenManager
from apps.agents.chat.history import DjangoCacheMessageHistory
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain.memory import ConversationSummaryBufferMemory
from apps.common.utils import get_llm
import logging
import json
import re  # Add import for regex
from channels.db import database_sync_to_async
from functools import partial

# Import the base class
from apps.agents.websockets.services.base_chat_service import (
    BaseChatService,
    ChatServiceError,
    CustomConversationSummaryBufferMemory
)

User = get_user_model()
logger = logging.getLogger(__name__)

class CrewChatService(BaseChatService):
    """Service for handling crew chat operations"""
    def __init__(self, user, conversation=None, model_name="gemini/gemini-2.0-flash"):
        self.user = user
        self.conversation = conversation
        
        # Initialize base class with any available session/conversation info
        session_id = conversation.session_id if conversation else None
        conversation_id = conversation.id if conversation else None
        
        super().__init__(
            model_name=model_name,
            session_id=session_id,
            conversation_id=conversation_id
        )
        
        self.websocket_handler = None
        self.crew_manager = CrewManager()
        self.crew_execution = None
        
        # Initialize message history if conversation exists
        if conversation:
            self.message_history = DjangoCacheMessageHistory(
                session_id=conversation.session_id,
                conversation_id=conversation.id
            )
        
        # Initialize memory
        self.memory = None
    
    async def initialize(self, crew_execution):
        """Initialize a new crew chat session"""
        try:
            self.crew_execution = crew_execution
            
            if not self.conversation:
                self.conversation = await self._create_or_get_conversation(
                    user=self.user,
                    crew_execution=crew_execution
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
            
            # Update token manager with conversation
            self.token_manager.conversation_id = self.conversation.id
            self.token_manager.session_id = self.conversation.session_id
            
            # Initialize message history if not already set
            if not self.message_history:
                self.message_history = DjangoCacheMessageHistory(
                    session_id=self.conversation.session_id,
                    conversation_id=self.conversation.id
                )
            
            # Initialize crew manager with execution
            await self.crew_manager.initialize(crew_execution)
            
            # Initialize memory using base class method
            create_memory_async = database_sync_to_async(partial(self._create_memory))
            self.memory = await create_memory_async()
            
            logger.info(f"Initialized crew chat for execution {crew_execution.id}")
            return self.conversation
            
        except Exception as e:
            logger.error(f"Error initializing crew chat: {str(e)}")
            raise
    
    @database_sync_to_async
    def _create_or_get_conversation(self, user=None, crew_execution=None) -> Any:
        """Create or get a conversation record."""
        try:
            if not self.session_id:
                session_id = uuid.uuid4()
            else:
                session_id = self.session_id
                
            # Try to get existing conversation first
            conversation = Conversation.objects.filter(
                session_id=session_id
            ).first()
            
            if not conversation:
                # Create new conversation
                conversation = Conversation.objects.create(
                    session_id=session_id,
                    user=user,
                    participant_type='crew',
                    crew_execution=crew_execution,
                    title="..."  # Add default title to match agent chat behavior
                )
            
            return conversation
            
        except Exception as e:
            logger.error(f"Error creating/getting conversation: {str(e)}")
            raise
    
    async def process_message(self, message: str, is_edit: bool = False) -> None:
        """Handle incoming user message for crew chat"""
        async with self.processing_lock:
            try:
                # Reset token tracking
                self.token_manager.reset_tracking()
                logger.debug(f"Processing user message: {message[:100]}...")
                
                # Get the crew chat session
                session = await CrewChatSession.objects.filter(conversation=self.conversation).afirst()
                if not session:
                    logger.error("No crew chat session found")
                    await self._handle_error("No active crew chat session", Exception("No session found"))
                    return
                
                # Add message to crew context if needed
                if self.crew_manager:
                    await self.crew_manager.add_message_to_context(message)
                
                # Store message in memory if available (for LLM context)
                if self.memory:
                    # Convert to HumanMessage for memory storage
                    human_message = HumanMessage(content=message)
                    
                    # Check if this message already exists in memory to avoid duplication
                    duplicate_found = False
                    if hasattr(self.memory, 'chat_memory') and self.memory.chat_memory:
                        for msg in self.memory.chat_memory.messages:
                            if isinstance(msg, HumanMessage) and msg.content == message:
                                logger.debug(f"Skipping duplicate user message: {message[:50]}...")
                                duplicate_found = True
                                break
                    
                    if not duplicate_found:
                        self.memory.chat_memory.add_message(human_message)
                
                # IMPORTANT: Don't add message to history here - the consumer already did this
                # The following code is commented out to prevent duplicate messages
                # but kept for reference
                """
                existing_messages = await self.message_manager.get_messages()
                duplicate_found = False
                for msg in existing_messages:
                    if isinstance(msg, HumanMessage) and msg.content == message:
                        logger.debug(f"Message already exists in history: {message[:50]}...")
                        duplicate_found = True
                        break
                
                if not duplicate_found:
                    await self.message_manager.add_message(HumanMessage(content=message))
                """
            
            except Exception as e:
                logger.error(f"Error processing message: {str(e)}")
                await self._handle_error(f"Failed to process message: {str(e)}", e)
    
    async def send_crew_message(self, content: str, task_id: Optional[int] = None):
        """Send message from crew to chat"""
        try:
            if not content:
                logger.warning("Empty content in crew message, skipping")
                return

            logger.debug(f"Sending crew message: {content[:100]}...")
            
            # Store in memory if available
            if self.memory:
                # Convert to AIMessage for memory storage
                ai_message = AIMessage(content=content)
                
                # Check if this message already exists in memory to avoid duplication
                duplicate_found = False
                if hasattr(self.memory, 'chat_memory') and self.memory.chat_memory:
                    for msg in self.memory.chat_memory.messages:
                        if isinstance(msg, AIMessage) and msg.content == content:
                            logger.debug(f"Skipping duplicate AI message: {content[:50]}...")
                            duplicate_found = True
                            break
                
                if not duplicate_found:
                    self.memory.chat_memory.add_message(ai_message)
                
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
