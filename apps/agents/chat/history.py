from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage
from typing import List, Optional, Dict
import logging
from apps.agents.models import ChatMessage

logger = logging.getLogger(__name__)

class DjangoCacheMessageHistory(BaseChatMessageHistory):
    """Message history that uses Django's cache and database for storage."""
    
    def __init__(self, session_id: str, conversation_id: Optional[str] = None, agent_id: Optional[int] = None, ttl: int = 3600):
        """Initialize with session ID and optional conversation ID."""
        # Store these as instance variables since they're used by other parts of the system
        self.session_id = session_id
        self.conversation_id = conversation_id
        self.agent_id = agent_id
        self.ttl = ttl
        
        # Initialize the message manager for all operations
        from apps.agents.chat.managers.message_manager import MessageManager
        self.message_manager = MessageManager(
            conversation_id=conversation_id,
            session_id=session_id,
            agent_id=agent_id,
            ttl=ttl
        )

    async def aget_messages(self) -> List[BaseMessage]:
        """Get messages from the message manager."""
        try:
            return await self.message_manager.get_messages()
        except Exception as e:
            logger.error(f"Error getting messages: {str(e)}")
            return []

    async def add_message(self, message: BaseMessage, token_usage: Optional[Dict] = None) -> Optional[ChatMessage]:
        """
        Add message using the message manager.
        
        Returns:
            ChatMessage: The stored message object, or None if storage failed
        """
        try:
            return await self.message_manager.add_message(message, token_usage)
        except Exception as e:
            logger.error(f"Error adding message: {str(e)}")
            raise

    def clear(self) -> None:
        """Clear message history."""
        try:
            self.message_manager.clear()
        except Exception as e:
            logger.error(f"Error clearing messages: {str(e)}")
            raise

    async def handle_edit(self, message_id: str) -> None:
        """Handle message editing by marking messages as deleted."""
        try:
            if self.conversation_id:
                await self.message_manager.handle_edit(message_id)
        except Exception as e:
            logger.error(f"Error handling edit: {str(e)}")
            raise