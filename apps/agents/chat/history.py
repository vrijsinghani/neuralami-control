from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import (
    BaseMessage, 
    HumanMessage, 
    AIMessage,
    messages_from_dict, 
    messages_to_dict
)
from django.core.cache import cache
from channels.db import database_sync_to_async
from typing import List, Optional, Dict
import logging
from ..models import TokenUsage

logger = logging.getLogger(__name__)

class DjangoCacheMessageHistory(BaseChatMessageHistory):
    """Message history that uses Django's cache backend"""
    
    def __init__(self, session_id: str, agent_id: int = None, ttl: int = 3600, conversation_id: Optional[int] = None):
        super().__init__()
        self.session_id = session_id
        self.agent_id = agent_id
        self.ttl = ttl
        self.key = f"chat_history_{session_id}"
        self.conversation_id = conversation_id

    @property
    def messages(self) -> List[BaseMessage]:
        """Synchronous method to retrieve messages from cache"""
        try:
            messages_dict = cache.get(self.key, [])
            #logger.debug(f"Cache lookup for {self.key}: found {len(messages_dict)} messages")
            
            if not messages_dict:
                #logger.debug("No messages in cache")
                return []
                
            messages = messages_from_dict(messages_dict)
            #logger.debug(f"Converted {len(messages)} messages from dict to BaseMessage objects")
            return messages
            
        except Exception as e:
            logger.error(f"Error retrieving messages: {str(e)}", exc_info=True)
            return []

    async def aget_messages(self) -> List[BaseMessage]:
        """Async method to retrieve messages from cache and database"""
        try:
            messages_dict = cache.get(self.key, [])
            #logger.debug(f"Cache lookup for {self.key}: found {len(messages_dict)} messages")
            
            if not messages_dict:
                #logger.debug("No messages in cache, checking database...")
                messages_dict = await self._get_db_messages()
                
                if messages_dict:
                    logger.debug(f"Caching {len(messages_dict)} messages from database")
                    cache.set(self.key, messages_dict, self.ttl)
                
            messages = messages_from_dict(messages_dict)
            #logger.debug(f"Converted {len(messages)} messages from dict to BaseMessage objects")
            return messages
            
        except Exception as e:
            logger.error(f"Error retrieving messages: {str(e)}", exc_info=True)
            return []

    async def add_message(self, message: BaseMessage, token_usage: Optional[Dict] = None) -> None:
        """Append the message to history and track token usage"""
        try:
            messages = await self.aget_messages()
            messages.append(message)
            messages_dict = messages_to_dict(messages)
            cache.set(self.key, messages_dict, self.ttl)
            
            # Save message and token usage together
            await self._add_db_message(message, token_usage)
                
        except Exception as e:
            logger.error(f"Error adding message with token tracking: {str(e)}", exc_info=True)
            raise

    def clear(self) -> None:
        """Clear message history from cache"""
        cache.delete(self.key)

    @database_sync_to_async
    def _get_db_messages(self):
        """Get messages from database synchronously"""
        from apps.agents.models import ChatMessage
        try:
            # Log the query we're about to make
            #logger.debug(f"Fetching messages for session {self.session_id}")
            
            db_messages = ChatMessage.objects.filter(
                session_id=self.session_id
            ).order_by('timestamp')
            
            # Log how many messages we found
            message_count = db_messages.count()
            #logger.debug(f"Found {message_count} messages in database for session {self.session_id}")
            
            messages_dict = []
            for msg in db_messages:
                logger.debug(f"Processing message: {msg.id} | is_agent: {msg.is_agent} | content: {msg.content[:50]}...")
                message_dict = {
                    'type': 'ai' if msg.is_agent else 'human',
                    'data': {'content': msg.content}
                }
                messages_dict.append(message_dict)
            
            #logger.debug(f"Processed {len(messages_dict)} messages into dictionary format")
            return messages_dict
            
        except Exception as e:
            logger.error(f"Error in _get_db_messages: {str(e)}", exc_info=True)
            raise

    @database_sync_to_async
    def _add_db_message(self, message: BaseMessage, token_usage: Optional[Dict] = None):
        """Add message to database synchronously"""
        from apps.agents.models import ChatMessage
        try:
            chat_message = ChatMessage.objects.create(
                session_id=self.session_id,
                content=message.content,
                is_agent=isinstance(message, AIMessage),
                agent_id=self.agent_id,
                user_id=1,  # You'll need to get the actual user ID
                model=token_usage.get('model', '') if token_usage else '',
            )
            
            # If we have token usage, create the token usage record
            if token_usage and self.conversation_id:
                from apps.agents.models import TokenUsage
                TokenUsage.objects.create(
                    conversation_id=self.conversation_id,
                    message=chat_message,
                    prompt_tokens=token_usage.get('prompt_tokens', 0),
                    completion_tokens=token_usage.get('completion_tokens', 0),
                    total_tokens=token_usage.get('total_tokens', 0),
                    model=token_usage.get('model', ''),
                    metadata={
                        'type': 'message',
                        'is_agent': isinstance(message, AIMessage)
                    }
                )
            
            return chat_message
            
        except Exception as e:
            logger.error(f"Error creating ChatMessage: {str(e)}", exc_info=True)
            raise

    @database_sync_to_async
    def _track_token_usage(self, chat_message, token_usage: Dict):
        """Track token usage in database"""
        try:
            TokenUsage.objects.create(
                conversation_id=self.conversation_id,
                message=chat_message,
                prompt_tokens=token_usage.get('prompt_tokens', 0),
                completion_tokens=token_usage.get('completion_tokens', 0),
                total_tokens=token_usage.get('total_tokens', 0),
                model=token_usage.get('model', ''),
                metadata=token_usage.get('metadata', {})
            )
        except Exception as e:
            logger.error(f"Error tracking token usage: {str(e)}")