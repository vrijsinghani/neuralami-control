from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage, messages_from_dict, messages_to_dict
from django.core.cache import cache
from typing import List
import hashlib

class DjangoCacheMessageHistory(BaseChatMessageHistory):
    """Message history that uses Django's cache backend"""
    
    def __init__(self, session_id: str, ttl: int = 3600):
        self.session_id = session_id
        self.ttl = ttl
        self.key = f"chat_history_{session_id}"
        self._message_hashes = set()

    def _get_message_hash(self, message: BaseMessage) -> str:
        """Generate a hash for a message to detect duplicates"""
        content = str(message.content)
        return hashlib.md5(content.encode()).hexdigest()

    def add_message(self, message: BaseMessage) -> None:
        """Append the message to the history in cache if not duplicate"""
        message_hash = self._get_message_hash(message)
        
        if message_hash not in self._message_hashes:
            self._message_hashes.add(message_hash)
            messages = self.messages
            messages.append(message)
            cache.set(
                self.key,
                messages_to_dict(messages),
                timeout=self.ttl
            )

    @property
    def messages(self) -> List[BaseMessage]:
        """Retrieve the messages from cache"""
        messages_dict = cache.get(self.key, [])
        messages = messages_from_dict(messages_dict) if messages_dict else []
        
        # Rebuild message hashes set
        self._message_hashes = {self._get_message_hash(msg) for msg in messages}
        return messages

    def clear(self) -> None:
        """Clear message history from cache"""
        cache.delete(self.key)