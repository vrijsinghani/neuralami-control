import uuid
from typing import Optional, Dict, Any
from django.contrib.auth import get_user_model
from apps.agents.models import (
    Conversation,
    CrewChatSession,
    ChatMessage,
    CrewExecution,
    ExecutionStage
)
from apps.agents.chat.managers.message_manager import MessageManager
from apps.agents.chat.managers.crew_manager import CrewManager
from apps.agents.chat.history import DjangoCacheMessageHistory
from langchain_core.messages import HumanMessage, AIMessage
from ..handlers.callback_handler import WebSocketCallbackHandler
from apps.agents.tasks.core.crew import initialize_crew, run_crew, get_client_data
import logging
import json
from channels.db import database_sync_to_async
from django.utils import timezone
import re
from django.core.cache import cache

User = get_user_model()
logger = logging.getLogger(__name__)

class CrewChatService:
    """Service for handling crew chat operations and context"""
    def __init__(self, user, conversation=None):
        self.user = user
        self.conversation = conversation
        self.websocket_handler = None
        self.message_manager = MessageManager(
            conversation_id=conversation.id if conversation else None,
            session_id=conversation.session_id if conversation else None
        )
        self.crew_execution = None
        self.message_history = None  # Will be initialized in initialize_chat
        self.callback_handler = None  # Will be set during initialization
        self.context_key = None  # Will be set during initialization

    @database_sync_to_async
    def _get_conversation_history(self) -> list:
        """Get formatted conversation history for crew execution"""
        if not self.message_history:
            return []
        
        messages = self.message_history.messages
        return [
            {
                'role': 'assistant' if isinstance(msg, AIMessage) else 'user',
                'content': msg.content
            }
            for msg in messages
        ]

    async def start_crew_execution(self, crew_id: int, client_id: Optional[int] = None):
        """Start a new crew execution"""
        try:
            # Create crew execution
            execution = await CrewExecution.objects.acreate(
                crew_id=crew_id,
                status='PENDING',
                user=self.user,
                conversation=self.conversation,
                client_id=client_id
            )
            
            # Update conversation
            self.conversation.participant_type = 'crew'
            self.conversation.crew_execution = execution
            if client_id:
                self.conversation.client_id = client_id
            await self.conversation.asave()

            # Initialize chat session
            await self.initialize_chat(execution)

            # Start crew execution in background task
            from apps.agents.tasks import execute_crew
            task = execute_crew.delay(execution.id)
            
            # Update execution with task ID
            execution.task_id = task.id
            await execution.asave()

            return execution
        except Exception as e:
            logger.error(f"Error starting crew execution: {str(e)}")
            raise
    
    async def initialize_chat(self, crew_execution):
        """Initialize chat session for crew execution"""
        try:
            self.crew_execution = crew_execution
            self.context_key = f"crew_chat_context_{crew_execution.id}"
            
            logger.debug(f"Initializing crew chat for execution {crew_execution.id}")
            
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
            
            # Set up callback handler for websocket communication
            self.callback_handler = WebSocketCallbackHandler(
                consumer=self.websocket_handler,
                message_manager=self.message_manager
            )

            # Initialize context in cache
            if not cache.get(self.context_key):
                context = {
                    'messages': [],
                    'task_outputs': {},
                    'current_task': None,
                    'execution_id': crew_execution.id,
                    'current_date': timezone.now().strftime("%Y-%m-%d")
                }
                cache.set(self.context_key, context, timeout=3600)
            
            logger.info(f"Chat session initialized for execution {crew_execution.id}")
            return self.conversation
            
        except Exception as e:
            logger.error(f"Error initializing crew chat: {str(e)}")
            raise
    
    async def handle_human_input(self, message: str, task_index: Optional[int] = None):
        """Handle human input for crew execution"""
        try:
            if not self.crew_execution:
                raise ValueError("Crew execution not initialized")
            
            if task_index is None:
                raise ValueError("Task index is required for human input")

            # Get current context
            context = await self.get_context()
            current_task = context.get('current_task')
            
            # Validate task index matches current task
            if current_task is not None and current_task != task_index:
                logger.warning(f"Task index mismatch. Expected {current_task}, got {task_index}")
            
            # Add message to context with task metadata
            await self.add_message_to_context(message, is_human_input=True, task_index=task_index)
            
            # Update execution status
            self.crew_execution.status = 'PROCESSING'
            await self.crew_execution.asave()
            
            # Store human input in cache with proper key format matching crew.py
            input_key = f"execution_{self.crew_execution.id}_task_{task_index}_input"
            cache.set(input_key, message, timeout=3600)
            
            # Update context to track human input state
            context['human_input_state'] = {
                'task_index': task_index,
                'timestamp': str(timezone.now()),
                'status': 'provided'
            }
            cache.set(self.context_key, context, timeout=3600)
            
            logger.debug(f"Stored human input for task {task_index} with key: {input_key}")
            
            # Send acknowledgment through websocket
            if self.websocket_handler:
                await self.websocket_handler.send_json({
                    'type': 'human_input_received',
                    'task_index': task_index,
                    'timestamp': timezone.now().isoformat()
                })
            
        except Exception as e:
            logger.error(f"Error handling human input: {str(e)}")
            raise

    async def add_message_to_context(self, message: str, is_human_input: bool = False, task_index: Optional[int] = None):
        """Add a message to the crew chat context"""
        if not self.context_key:
            raise ValueError("Context not initialized")
            
        try:
            context = cache.get(self.context_key, {})
            messages = context.get('messages', [])
            
            # Add message to context with metadata
            message_data = {
                'content': message,
                'timestamp': str(timezone.now()),
                'is_human': True
            }
            
            # Add task metadata if this is human input
            if is_human_input and task_index is not None:
                message_data.update({
                    'is_human_input': True,
                    'task_index': task_index
                })
            
            messages.append(message_data)
            
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

    async def handle_message(self, message: str):
        """Handle incoming message for crew chat"""
        try:
            # Add message to context
            await self.add_message_to_context(message)
            
            # Store message in history
            stored_message = await self.message_history.add_message(HumanMessage(content=message))
            
            # Send user message confirmation
            if self.websocket_handler:
                await self.websocket_handler.send_json({
                    'type': 'user_message',
                    'content': {
                        'type': 'text',
                        'message': message
                    },
                    'id': str(stored_message.id) if stored_message else None,
                    'timestamp': timezone.now().isoformat()
                })
            
            # If this is during a human input task, check if we need to handle it
            context = await self.get_context()
            current_task = context.get('current_task')
            human_input_state = context.get('human_input_state', {})
            
            if human_input_state.get('status') == 'waiting' and current_task is not None:
                # This might be a response to a human input request
                await self.handle_human_input(message, task_index=current_task)
            
        except Exception as e:
            logger.error(f"Error handling crew message: {str(e)}")
            # Send error message through websocket
            if self.websocket_handler:
                await self.websocket_handler.send_json({
                    'type': 'error',
                    'content': {
                        'error': str(e)
                    },
                    'timestamp': timezone.now().isoformat()
                })
            raise
    
    async def send_crew_message(self, content: str, task_id: Optional[int] = None):
        """Send message from crew to chat"""
        try:
            if not content:
                logger.warning("Empty content in crew message, skipping")
                return

            logger.debug(f"Sending crew message: {content[:100]}...")
                
            # Save message in history
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
                # Base message data
                message_data = {
                    'id': str(stored_message.id) if stored_message else str(message.id),
                    'timestamp': message.timestamp.isoformat(),
                    'task_id': task_id
                }

                # Parse and format different message types
                if content.startswith(('Using tool:', 'Tool Start:')):
                    # Extract tool name and input
                    tool_match = re.match(r'^(?:Using tool:|Tool Start:)\s*(.*?)(?:\s*-\s*|\n)(.*)$', content)
                    if tool_match:
                        tool_name = tool_match.group(1).strip()
                        tool_input = tool_match.group(2).strip()
                        message_data.update({
                            'type': 'tool_start',
                            'content': {
                                'tool': tool_name,
                                'input': tool_input
                            },
                            'timestamp': message.timestamp.isoformat()
                        })
                    else:
                        # Fallback for unparseable tool messages
                        message_data.update({
                            'type': 'crew_message',
                            'content': content,
                            'timestamp': message.timestamp.isoformat()
                        })

                elif content.startswith(('Tool Result:', 'Tool result:')):
                    try:
                        # Extract result content
                        result_content = re.sub(r'^(?:Tool Result:|Tool result:)', '', content, 1).strip()
                        
                        # Parse output
                        if isinstance(result_content, str):
                            try:
                                data = json.loads(result_content)
                            except json.JSONDecodeError:
                                data = {"text": result_content}
                        else:
                            data = result_content

                        # Send message to websocket matching callback handler format
                        message_data.update({
                            'type': 'tool_result',
                            'content': data,  # Direct data object like callback handler
                            'timestamp': message.timestamp.isoformat()
                        })

                    except Exception as e:
                        logger.error(f"Error processing tool result: {str(e)}")
                        message_data.update({
                            'type': 'tool_result',
                            'content': {'error': str(e)},
                            'timestamp': message.timestamp.isoformat()
                        })

                elif content.startswith('Tool Error:'):
                    error_message = content.replace('Tool Error:', '', 1).strip()
                    message_data.update({
                        'type': 'error',
                        'message': error_message
                    })

                else:
                    # Regular crew message
                    message_data.update({
                        'type': 'crew_message',
                        'content': content,
                        'timestamp': message.timestamp.isoformat()
                    })

                # Send formatted message
                await self.websocket_handler.send_json(message_data)
            
            logger.debug(f"Crew message saved successfully with ID: {message.id}")
            return message
            
        except Exception as e:
            logger.error(f"Error sending crew message: {str(e)}")
            raise

    async def send_system_message(self, content: str, status: Optional[str] = None):
        """Send system message through websocket"""
        if self.websocket_handler:
            message_data = {
                'type': 'system_message',
                'message': content
            }
            if status:
                message_data['status'] = status
            message_data['timestamp'] = timezone.now().isoformat()
            await self.websocket_handler.send_json(message_data)

    async def send_execution_update(self, status: str, task_index: Optional[int] = None, message: Optional[str] = None):
        """Send execution status update"""
        if self.websocket_handler:
            update_data = {
                'type': 'execution_update',
                'status': status,
                'task_index': task_index
            }
            if message:
                update_data['message'] = message
            update_data['timestamp'] = timezone.now().isoformat()
            await self.websocket_handler.send_json(update_data)
