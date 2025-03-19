from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage
from django.core.cache import cache
from typing import List, Optional, Dict, Any
from channels.db import database_sync_to_async
from apps.agents.chat.formatters.tool_formatter import ToolFormatter
from apps.agents.chat.formatters.table_formatter import TableFormatter
from apps.agents.models import ChatMessage, ToolRun
import logging
import json
from django.db import models
import asyncio

logger = logging.getLogger(__name__)

def messages_to_dict(messages: List[BaseMessage]) -> List[Dict]:
    """Convert message objects to dictionary format for storage."""
    return [{
        'type': message.__class__.__name__,
        'content': message.content,
        'additional_kwargs': message.additional_kwargs
    } for message in messages]

def dict_to_messages(messages_dict: List[Dict]) -> List[BaseMessage]:
    """Convert dictionary format back to message objects."""
    message_types = {
        'HumanMessage': HumanMessage,
        'AIMessage': AIMessage,
        'SystemMessage': SystemMessage
    }
    
    return [
        message_types[msg['type']](
            content=msg['content'],
            additional_kwargs=msg.get('additional_kwargs', {})
        ) for msg in messages_dict
    ]

class MessageManager(BaseChatMessageHistory):
    """
    Manages chat message history, storage, and formatting.
    Consolidates message-related functionality from across the codebase.
    """
    
    def __init__(self, 
                 conversation_id: Optional[str] = None,
                 session_id: Optional[str] = None,
                 agent_id: Optional[int] = None,
                 ttl: int = 3600):
        """
        Initialize the MessageManager.
        
        Args:
            conversation_id: Unique identifier for the conversation
            session_id: Unique identifier for the current session
            agent_id: ID of the agent associated with this conversation
            ttl: Time-to-live for cached messages in seconds
        """
        super().__init__()
        self.conversation_id = conversation_id
        self.session_id = session_id
        self.agent_id = agent_id
        self.ttl = ttl
        self.tool_formatter = ToolFormatter()
        self.messages_cache_key = f"messages_{self.session_id}"
        self._messages = []

    @property
    def messages(self) -> List[BaseMessage]:
        """Get all messages in the history. Required by BaseChatMessageHistory."""
        if self.messages_cache_key:
            messages_dict = cache.get(self.messages_cache_key, [])
            return dict_to_messages(messages_dict)
        return self._messages.copy()

    @messages.setter
    def messages(self, messages: List[BaseMessage]) -> None:
        """Set messages in the history. Required by BaseChatMessageHistory."""
        self._messages = messages.copy()
        if self.messages_cache_key:
            messages_dict = messages_to_dict(messages)
            cache.set(self.messages_cache_key, messages_dict, self.ttl)

    async def add_message(self, message: BaseMessage, token_usage: Optional[Dict] = None) -> Optional[ChatMessage]:
        """
        Add a message to the history and persist it.
        This is the central function for all message persistence.
        
        Args:
            message: The message to add
            token_usage: Optional token usage stats
            
        Returns:
            ChatMessage: The created message object, or None if creation failed
        """
        try:
            # For agent finish messages, extract JSON data if present
            if isinstance(message, AIMessage) and message.content:
                # Look for JSON code blocks
                if '```json' in message.content:
                    parts = message.content.split('```json')
                    if len(parts) > 1:
                        text_content = parts[0].strip()
                        json_str = parts[1].split('```')[0].strip()
                        try:
                            # Validate JSON
                            json_data = json.loads(json_str)
                            # Store as separate messages
                            if text_content:
                                await self._store_message_in_db(AIMessage(content=text_content), token_usage)
                            message.content = json.dumps(json_data)
                        except json.JSONDecodeError:
                            # If JSON is invalid, keep original message
                            pass

            # Store in database only if we have a conversation ID
            if self.conversation_id:
                return await self._store_message_in_db(message, token_usage)
            return None
                
        except Exception as e:
            logger.error(f"Error adding message: {str(e)}")
            raise

    async def get_messages(self) -> List[BaseMessage]:
        """Get all non-deleted messages in the history."""
        try:
            if self.conversation_id:
                from apps.agents.models import ChatMessage, ToolRun
                
                # First get non-deleted messages
                query = {
                    'conversation_id': self.conversation_id,
                    'is_deleted': False  # Only get non-deleted messages
                }
                
                logger.debug(f"Retrieving messages for conversation {self.conversation_id}")
                    
                messages = await database_sync_to_async(
                    lambda: list(
                        ChatMessage.objects.filter(**query)
                        .prefetch_related(
                            # Only prefetch tool runs associated with non-deleted messages
                            models.Prefetch(
                                'tool_runs',
                                queryset=ToolRun.objects.filter(
                                    message__is_deleted=False,
                                    is_deleted=False
                                )
                            )
                        )
                        .order_by('timestamp')
                    )
                )()
                
                logger.debug(f"Retrieved {len(messages)} messages from database")

                result = []
                for msg in messages:
                    logger.debug(f"Processing message ID: {msg.id}, Content: {msg.content[:50]}...")
                    
                    # Process the message differently based on type
                    if not msg.is_agent:
                        # Human messages (no tool processing needed)
                        result.append(HumanMessage(
                            content=msg.content,
                            additional_kwargs={'id': str(msg.id)}
                        ))
                    else:
                        # For agent messages, we need to check tool runs
                        additional_kwargs = await self._process_tool_runs(msg) if msg.is_agent else {'id': str(msg.id)}
                        
                        # AI messages
                        result.append(AIMessage(
                            content=msg.content,
                            additional_kwargs=additional_kwargs
                        ))

                # Update the in-memory cache with the loaded messages
                self._messages = result.copy()
                if self.messages_cache_key:
                    messages_dict = messages_to_dict(result)
                    cache.set(self.messages_cache_key, messages_dict, self.ttl)
                
                return result
            return self._messages.copy()
        except Exception as e:
            logger.error(f"Error getting messages: {str(e)}", exc_info=True)
            return []

    @database_sync_to_async
    def _process_tool_runs(self, message):
        """Process tool runs for a message in a synchronous context."""
        additional_kwargs = {'id': str(message.id)}
        
        try:
            if hasattr(message, 'tool_runs'):
                tool_runs = list(message.tool_runs.all())
                logger.debug(f"Message {message.id} has {len(tool_runs)} tool runs")
                
                if tool_runs:
                    # Get the first tool run
                    tool_run = tool_runs[0]
                    tool_name = tool_run.tool.name if tool_run.tool else 'unknown_tool'
                    logger.debug(f"Tool run ID: {tool_run.id}, Tool: {tool_name}")
                    
                    # Parse tool output if it's JSON
                    if tool_run.result and tool_run.result.strip():
                        logger.debug(f"Tool result raw: {tool_run.result[:100]}...")
                        try:
                            tool_output = json.loads(tool_run.result)
                            logger.debug("Successfully parsed tool result as JSON")
                        except json.JSONDecodeError:
                            tool_output = tool_run.result
                            logger.debug("Could not parse tool result as JSON, using raw string")
                        
                        # Add tool data to additional_kwargs
                        additional_kwargs['tool_call'] = {
                            'name': tool_name,
                            'output': tool_output
                        }
                        logger.debug(f"Added tool_call to additional_kwargs for message {message.id}")
        except Exception as e:
            logger.error(f"Error processing tool runs: {str(e)}", exc_info=True)
            
        return additional_kwargs

    async def add_messages(self, messages: List[BaseMessage]) -> None:
        """Add multiple messages to the history."""
        for message in messages:
            await self.add_message(message)

    def clear(self) -> None:
        """Required abstract method: Clear all messages."""
        pass  # No cache to clear anymore

    async def clear_messages(self) -> None:
        """Clear all messages from the history."""
        try:
            if self.conversation_id:
                await database_sync_to_async(ChatMessage.objects.filter(
                    conversation_id=self.conversation_id
                ).delete)()
                
        except Exception as e:
            logger.error(f"Error clearing messages: {str(e)}")
            raise

    @database_sync_to_async
    def _store_message_in_db(self, message: BaseMessage, token_usage: Optional[Dict] = None) -> Optional[ChatMessage]:
        """
        Store a message in the database.
        Centralized database persistence function.
        
        Returns:
            ChatMessage: The created message object, or None if creation failed
        """
        try:
            from apps.agents.models import ChatMessage, Conversation, TokenUsage, ToolRun, Tool
            
            # Get the conversation by session_id
            conversation = Conversation.objects.filter(
                session_id=self.session_id
            ).select_related('user', 'agent').first()
            
            if not conversation:
                logger.error(f"No conversation found with session ID: {self.session_id}")
                return None
                
            # Determine if message is from agent or user
            is_agent = not isinstance(message, HumanMessage)
            
            # Create the message
            chat_message = ChatMessage.objects.create(
                session_id=self.session_id,
                conversation=conversation,
                agent=conversation.agent,
                user=conversation.user,
                content=message.content,
                is_agent=is_agent,
                model=token_usage.get('model', 'unknown') if token_usage else 'unknown'
            )
            
            # Store token usage if provided
            if token_usage:
                TokenUsage.objects.create(
                    conversation=conversation,
                    message=chat_message,
                    prompt_tokens=token_usage.get('prompt_tokens', 0),
                    completion_tokens=token_usage.get('completion_tokens', 0),
                    total_tokens=token_usage.get('total_tokens', 0),
                    model=token_usage.get('model', 'unknown'),
                    metadata={'message_type': message.__class__.__name__}
                )
            
            # Store tool runs if this is a tool-related message
            if message.additional_kwargs.get('tool_call'):
                tool_call = message.additional_kwargs['tool_call']
                tool_name = tool_call.get('name')
                tool_input = tool_call.get('input', {})
                tool_output = tool_call.get('output')
                
                if tool_name:
                    tool = Tool.objects.filter(name=tool_name).first()
                    if tool:
                        # Ensure tool_output is proper JSON
                        try:
                            if isinstance(tool_output, str):
                                # If it's a string, try to parse it to ensure valid JSON
                                output_json = json.loads(tool_output)
                            else:
                                output_json = tool_output
                            # Store as JSON string
                            tool_output = json.dumps(output_json)
                        except:
                            # If not valid JSON, store as string
                            tool_output = str(tool_output)
                            
                        ToolRun.objects.create(
                            tool=tool,
                            conversation=conversation,
                            message=chat_message,
                            status='completed',
                            inputs=tool_input,
                            result=tool_output
                        )
            
            return chat_message
                
        except Exception as e:
            logger.error(f"Error storing message in database: {str(e)}", exc_info=True)
            raise


    async def handle_edit(self, message_id: str) -> None:
        """Handle message editing by marking the message and subsequent messages as deleted."""
        try:
            # Get the message's timestamp
            message = await database_sync_to_async(
                ChatMessage.objects.get
            )(id=message_id)
            
            # Mark this message and all subsequent messages as deleted
            deleted_count = await database_sync_to_async(
                ChatMessage.objects.filter(
                    conversation_id=self.conversation_id,
                    timestamp__gte=message.timestamp
                ).update
            )(is_deleted=True)
            
            # Also mark associated tool runs as deleted
            await database_sync_to_async(
                ToolRun.objects.filter(
                    conversation_id=self.conversation_id,
                    message__timestamp__gte=message.timestamp
                ).update
            )(is_deleted=True)
            
            logger.debug(f"Message timestamp: {message.timestamp}. {deleted_count} messages and their tool runs marked as deleted.")
                    
        except Exception as e:
            logger.error(f"Error handling message edit: {str(e)}")
            raise

    def format_message(self, content: Any, message_type: Optional[str] = None) -> str:
        """Format a message for display."""
        try:
            # If content is a dict, convert to string representation
            if isinstance(content, dict):
                return json.dumps(content, indent=2)
                
            # Handle tool messages
            if message_type and message_type.startswith('tool_'):
                return self.tool_formatter.format_tool_usage(str(content), message_type)
                
            return str(content)
        except Exception as e:
            logger.error(f"Error formatting message: {str(e)}")
            return str(content)

    async def get_conversation_summary(self) -> str:
        """Get a summary of the conversation."""
        messages = await self.get_messages()
        if not messages:
            return "No messages in conversation"
        
        summary_parts = []
        for msg in messages:
            msg_type = msg.__class__.__name__.replace('Message', '')
            summary_parts.append(f"{msg_type}: {msg.content[:100]}...")
        
        return "\n".join(summary_parts) 

    async def get_message_ids(self) -> Dict[str, str]:
        """Get a mapping of message content to message IDs."""
        messages = await ChatMessage.objects.filter(
            conversation_id=self.conversation_id
        ).values('id', 'content')
        return {msg['content']: str(msg['id']) for msg in messages}

    async def add_messages(self, messages: List[BaseMessage]) -> None:
        """Add multiple messages to the history asynchronously."""
        for message in messages:
            await self.add_message(message)

    def add_messages_sync(self, messages: List[BaseMessage]) -> None:
        """Synchronous version of add_messages."""
        from django.db import transaction
        for message in messages:
            self.add_message_sync(message)
            
    def add_message_sync(self, message: BaseMessage, token_usage: Optional[Dict] = None) -> Optional[ChatMessage]:
        """Synchronous version of add_message."""
        try:
            # For agent finish messages, extract JSON data if present
            if isinstance(message, AIMessage) and message.content:
                # Look for JSON code blocks
                if '```json' in message.content:
                    parts = message.content.split('```json')
                    if len(parts) > 1:
                        text_content = parts[0].strip()
                        json_str = parts[1].split('```')[0].strip()
                        try:
                            # Validate JSON
                            json_data = json.loads(json_str)
                            # Store as separate messages
                            if text_content:
                                self._store_message_in_db_sync(AIMessage(content=text_content), token_usage)
                            message.content = json.dumps(json_data)
                        except json.JSONDecodeError:
                            # If JSON is invalid, keep original message
                            pass

            # Store in database only if we have a conversation ID
            if self.conversation_id:
                return self._store_message_in_db_sync(message, token_usage)
            return None
                
        except Exception as e:
            logger.error(f"Error adding message synchronously: {str(e)}")
            raise
    
    def get_messages_sync(self) -> List[BaseMessage]:
        """Synchronous version of get_messages."""
        try:
            if self.conversation_id:
                from apps.agents.models import ChatMessage, ToolRun
                
                # First get non-deleted messages
                query = {
                    'conversation_id': self.conversation_id,
                    'is_deleted': False  # Only get non-deleted messages
                }
                
                logger.debug(f"Retrieving messages synchronously for conversation {self.conversation_id}")
                    
                messages = list(
                    ChatMessage.objects.filter(**query)
                    .prefetch_related(
                        # Only prefetch tool runs associated with non-deleted messages
                        models.Prefetch(
                            'tool_runs',
                            queryset=ToolRun.objects.filter(
                                message__is_deleted=False,
                                is_deleted=False
                            )
                        )
                    )
                    .order_by('timestamp')
                )
                
                logger.debug(f"Retrieved {len(messages)} messages from database (sync)")

                result = []
                for msg in messages:
                    # Process the message differently based on type
                    if not msg.is_agent:
                        # Human messages (no tool processing needed)
                        result.append(HumanMessage(
                            content=msg.content,
                            additional_kwargs={'id': str(msg.id)}
                        ))
                    else:
                        # For agent messages, we need to check tool runs
                        additional_kwargs = self._process_tool_runs_sync(msg) if msg.is_agent else {'id': str(msg.id)}
                        
                        # AI messages
                        result.append(AIMessage(
                            content=msg.content,
                            additional_kwargs=additional_kwargs
                        ))

                # Update the in-memory cache with the loaded messages
                self._messages = result.copy()
                if self.messages_cache_key:
                    messages_dict = messages_to_dict(result)
                    cache.set(self.messages_cache_key, messages_dict, self.ttl)
                
                return result
            return self._messages.copy()
        except Exception as e:
            logger.error(f"Error getting messages synchronously: {str(e)}")
            return []
    
    def _process_tool_runs_sync(self, message):
        """Process tool runs for a message in a synchronous context."""
        additional_kwargs = {'id': str(message.id)}
        
        try:
            if hasattr(message, 'tool_runs'):
                tool_runs = list(message.tool_runs.all())
                
                if tool_runs:
                    # Get the first tool run
                    tool_run = tool_runs[0]
                    tool_name = tool_run.tool.name if tool_run.tool else 'unknown_tool'
                    
                    # Parse tool output if it's JSON
                    if tool_run.result and tool_run.result.strip():
                        try:
                            tool_output = json.loads(tool_run.result)
                        except json.JSONDecodeError:
                            tool_output = tool_run.result
                        
                        # Add tool data to additional_kwargs
                        additional_kwargs['tool_call'] = {
                            'name': tool_name,
                            'output': tool_output
                        }
        except Exception as e:
            logger.error(f"Error processing tool runs synchronously: {str(e)}")
            
        return additional_kwargs
        
    def _store_message_in_db_sync(self, message: BaseMessage, token_usage: Optional[Dict] = None) -> Optional[ChatMessage]:
        """Store a message in the database synchronously."""
        try:
            from apps.agents.models import ChatMessage, Conversation
            
            # Find the conversation
            conversation = Conversation.objects.filter(id=self.conversation_id).first()
            if not conversation:
                logger.error(f"Conversation with ID {self.conversation_id} not found")
                return None
                
            # Default message attributes
            message_attrs = {
                'conversation': conversation,
                'content': message.content or "",
                'is_agent': isinstance(message, AIMessage),
                'is_edited': False
            }
            
            # Add token usage if provided
            if token_usage:
                message_attrs.update({
                    'prompt_tokens': token_usage.get('prompt_tokens', 0),
                    'completion_tokens': token_usage.get('completion_tokens', 0),
                    'total_tokens': token_usage.get('total_tokens', 0)
                })
                
            # Create and save message
            chat_message = ChatMessage.objects.create(**message_attrs)
            
            # Update conversation
            conversation.updated_at = chat_message.timestamp
            conversation.save(update_fields=['updated_at'])
            
            logger.debug(f"Created message {chat_message.id} for conversation {self.conversation_id}")
            return chat_message
            
        except Exception as e:
            logger.error(f"Error storing message in DB: {str(e)}")
            return None