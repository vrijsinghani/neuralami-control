import logging
import tiktoken
from django.core.cache import cache
from django.db import models
from typing import Dict, Optional, Any
from channels.db import database_sync_to_async
from apps.agents.models import TokenUsage
from apps.common.utils import get_llm

logger = logging.getLogger(__name__)

class TokenManager:
    """
    Manages token counting, tracking, and limits for chat conversations.
    Consolidates token-related functionality from across the codebase.
    """
    
    def __init__(self, 
                 conversation_id: Optional[str] = None,
                 session_id: Optional[str] = None,
                 max_token_limit: int = 16384,
                 model_name: str = "gpt-3.5-turbo"):
        """
        Initialize the TokenManager.
        
        Args:
            conversation_id: Unique identifier for the conversation
            session_id: Unique identifier for the current session
            max_token_limit: Maximum number of tokens allowed in conversation history
            model_name: Name of the model to use for tokenization
        """
        self.conversation_id = conversation_id
        self.session_id = session_id
        self.max_token_limit = max_token_limit
        self.model_name = model_name
        # Use the same tokenizer setup as utils.py
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        self.input_tokens = 0
        self.output_tokens = 0
        self.token_callback = None

    def count_tokens(self, text: str) -> int:
        """Count tokens in text using the initialized tokenizer."""
        try:
            return len(self.tokenizer.encode(text, disallowed_special=()))
        except Exception as e:
            logger.error(f"Error counting tokens: {str(e)}")
            return 0

    def set_token_callback(self, callback):
        """Set the token callback from the LLM."""
        self.token_callback = callback

    def track_token_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        """Track token usage for the current session."""
        self.input_tokens += prompt_tokens
        self.output_tokens += completion_tokens
        
        if self.session_id:
            session_cache_key = f"token_totals_{self.session_id}"
            session_totals = cache.get(session_cache_key, {
                'prompt_tokens': 0,
                'completion_tokens': 0,
                'total_tokens': 0
            })
            
            session_totals['prompt_tokens'] += prompt_tokens
            session_totals['completion_tokens'] += completion_tokens
            session_totals['total_tokens'] += (prompt_tokens + completion_tokens)
            
            cache.set(session_cache_key, session_totals, 3600)  # 1 hour expiry

    def get_current_usage(self) -> Dict[str, int]:
        """Get current token usage for the session."""
        if self.token_callback:
            return {
                'prompt_tokens': self.token_callback.input_tokens,
                'completion_tokens': self.token_callback.output_tokens,
                'total_tokens': self.token_callback.input_tokens + self.token_callback.output_tokens,
                'model': self.model_name
            }
        return {
            'prompt_tokens': self.input_tokens,
            'completion_tokens': self.output_tokens,
            'total_tokens': self.input_tokens + self.output_tokens,
            'model': self.model_name
        }

    def reset_tracking(self):
        """Reset token tracking for the current session."""
        self.input_tokens = 0
        self.output_tokens = 0
        if self.token_callback:
            self.token_callback.input_tokens = 0
            self.token_callback.output_tokens = 0

    async def _reset_session_token_totals(self):
        """Reset token totals for the session."""
        if self.session_id:
            cache.delete(f"token_totals_{self.session_id}")

    @database_sync_to_async
    def store_token_usage(self, message_id: str, token_usage: Dict[str, Any]):
        """Store token usage in the database."""
        if not self.conversation_id:
            return

        try:
            TokenUsage.objects.create(
                conversation_id=self.conversation_id,
                message_id=message_id,
                prompt_tokens=token_usage.get('prompt_tokens', 0),
                completion_tokens=token_usage.get('completion_tokens', 0),
                total_tokens=token_usage.get('total_tokens', 0),
                model=token_usage.get('model', ''),
                metadata=token_usage.get('metadata', {})
            )
        except Exception as e:
            logger.error(f"Error storing token usage: {str(e)}")

    @database_sync_to_async
    def get_conversation_token_usage(self) -> Dict[str, int]:
        """Get total token usage for the conversation."""
        if not self.conversation_id:
            return {'total_tokens': 0, 'prompt_tokens': 0, 'completion_tokens': 0}

        try:
            usage = TokenUsage.objects.filter(conversation_id=self.conversation_id).aggregate(
                total_tokens=models.Sum('total_tokens'),
                prompt_tokens=models.Sum('prompt_tokens'),
                completion_tokens=models.Sum('completion_tokens')
            )
            return {
                'total_tokens': usage['total_tokens'] or 0,
                'prompt_tokens': usage['prompt_tokens'] or 0,
                'completion_tokens': usage['completion_tokens'] or 0
            }
        except Exception as e:
            logger.error(f"Error getting conversation token usage: {str(e)}")
            return {'total_tokens': 0, 'prompt_tokens': 0, 'completion_tokens': 0}

    async def track_conversation_tokens(self):
        """Track token usage for the entire conversation."""
        if not self.conversation_id:
            return

        current_usage = self.get_current_usage()
        if current_usage['total_tokens'] > 0:
            await self.store_token_usage(
                message_id=f"conversation_{self.conversation_id}_{len(current_usage)}",
                token_usage=current_usage
            ) 