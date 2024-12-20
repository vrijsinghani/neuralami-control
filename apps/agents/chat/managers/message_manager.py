from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage
from django.core.cache import cache
from typing import List, Optional, Dict, Any
from channels.db import database_sync_to_async
from apps.agents.chat.formatters.tool_formatter import ToolFormatter
from apps.agents.chat.formatters.table_formatter import TableFormatter
from apps.agents.models import ChatMessage
import logging
import json

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

    async def add_message(self, message: BaseMessage, token_usage: Optional[Dict] = None) -> None:
        """Add a message to the history."""
        try:
            # Get current messages
            messages = await self.get_messages()
            messages.append(message)
            
            # Update cache
            if self.messages_cache_key:
                messages_dict = messages_to_dict(messages)
                cache.set(self.messages_cache_key, messages_dict, self.ttl)
            
            # Store in database if conversation_id is provided
            if self.conversation_id:
                await self._store_message(message, token_usage)
                
        except Exception as e:
            logger.error(f"Error adding message: {str(e)}")
            raise

    async def get_messages(self) -> List[BaseMessage]:
        """Get all messages in the history."""
        try:
            if self.messages_cache_key:
                messages_dict = cache.get(self.messages_cache_key, [])
                return dict_to_messages(messages_dict)
            return []
        except Exception as e:
            logger.error(f"Error getting messages: {str(e)}")
            return []

    def add_messages(self, messages: List[BaseMessage]) -> None:
        """Add multiple messages to the history."""
        for message in messages:
            self.add_message(message)

    def clear(self) -> None:
        """Required abstract method: Clear all messages."""
        if self.messages_cache_key:
            cache.delete(self.messages_cache_key)

    async def clear_messages(self) -> None:
        """Clear all messages from the history."""
        try:
            if self.messages_cache_key:
                cache.delete(self.messages_cache_key)
            
            if self.conversation_id:
                await database_sync_to_async(ChatMessage.objects.filter(
                    conversation_id=self.conversation_id
                ).delete)()
                
        except Exception as e:
            logger.error(f"Error clearing messages: {str(e)}")
            raise

    @database_sync_to_async
    def _store_message(self, message: BaseMessage, token_usage: Optional[Dict] = None) -> None:
        """Store a message in the database."""
        try:
            ChatMessage.objects.create(
                conversation_id=self.conversation_id,
                message_type=message.__class__.__name__.lower().replace('message', ''),
                content=message.content,
                token_usage=token_usage or {},
                metadata=message.additional_kwargs
            )
        except Exception as e:
            logger.error(f"Error storing message: {str(e)}")
            raise

    async def handle_edit(self) -> None:
        """Handle message editing by removing the edited message and subsequent messages."""
        try:
            messages = await self.get_messages()
            
            # Find the last human message index
            last_human_idx = None
            for i in range(len(messages) - 1, -1, -1):
                if isinstance(messages[i], HumanMessage):
                    last_human_idx = i
                    break

            if last_human_idx is not None:
                # Keep messages up to the last human message
                messages = messages[:last_human_idx]
                
                # Update cache
                if self.messages_cache_key:
                    messages_dict = messages_to_dict(messages)
                    cache.set(self.messages_cache_key, messages_dict, self.ttl)
                
                # Update database
                if self.conversation_id:
                    await self._delete_subsequent_messages(last_human_idx)
                    
        except Exception as e:
            logger.error(f"Error handling message edit: {str(e)}")
            raise

    @database_sync_to_async
    def _delete_subsequent_messages(self, from_index: int) -> None:
        """Delete messages after the specified index from the database."""
        try:
            if self.conversation_id:
                messages = ChatMessage.objects.filter(conversation_id=self.conversation_id).order_by('created_at')
                messages_to_delete = messages[from_index:]
                messages_to_delete.delete()
        except Exception as e:
            logger.error(f"Error deleting subsequent messages: {str(e)}")
            raise

    def format_message(self, content: Any, message_type: Optional[str] = None) -> str:
        """Format a message for display."""
        if message_type and message_type.startswith('tool_'):
            return self.tool_formatter.format_tool_usage(content, message_type)
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