from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage, messages_from_dict, messages_to_dict
from django.core.cache import cache
from typing import List
import logging

logger = logging.getLogger(__name__)

class DjangoCacheMessageHistory(BaseChatMessageHistory):
    """Message history that uses Django's cache backend"""
    
    def __init__(self, session_id: str, ttl: int = 3600):
        self.session_id = session_id
        self.ttl = ttl
        self.key = f"chat_history_{session_id}"

    @property
    def messages(self) -> List[BaseMessage]:
        """Retrieve the messages from cache"""
        messages_dict = cache.get(self.key, [])
        return messages_from_dict(messages_dict) if messages_dict else []

    @messages.setter 
    def messages(self, messages: List[BaseMessage]) -> None:
        """Set the messages in cache"""
        cache.set(self.key, messages_to_dict(messages), timeout=self.ttl)

    def add_message(self, message: BaseMessage) -> None:
        """Append the message to the history in cache"""
        messages = self.messages
        messages.append(message)
        cache.set(self.key, messages_to_dict(messages), timeout=self.ttl)

    def clear(self) -> None:
        """Clear message history from cache"""
        cache.delete(self.key)