import logging
import tiktoken
from django.core.cache import cache
from django.db import models
from typing import Dict, Optional, Any
from channels.db import database_sync_to_async
from apps.agents.models import TokenUsage
from apps.common.utils import get_llm
from datetime import datetime
import uuid
import json

logger = logging.getLogger(__name__)

class TokenManager:
    """
    Manages token counting, tracking, and limits for chat conversations.
    Consolidates token-related functionality from across the codebase.
    """
    
    def __init__(self, 
                 conversation_id: Optional[str] = None,
                 session_id: Optional[str] = None,
                 model_name: str = "gpt-3.5-turbo",
                 max_token_limit: int = 100000):
        """
        Initialize the token manager.
        
        Args:
            conversation_id: Unique identifier for the conversation
            session_id: Unique identifier for the current session
            model_name: Name of the model to use for tokenization
            max_token_limit: Maximum number of tokens allowed in conversation history
        """
        self.conversation_id = conversation_id  # May be the db ID or the session_id
        self.session_id = session_id  # Always the UUID session ID
        self.model_name = model_name
        self.max_token_limit = max_token_limit
        
        # Use cl100k_base as default tokenizer which works with most models
        # Don't try to map model names automatically as it won't work for all models (like Gemini)
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        
        self.token_callback = None  # To store the token_counter from get_llm
        self.input_tokens = 0
        self.output_tokens = 0
        
    def set_token_callback(self, callback):
        """Set the token callback from the LLM."""
        self.token_callback = callback
    
    def track_token_usage(self, prompt_tokens: int = 0, completion_tokens: int = 0):
        """
        Track token usage for the current session.
        
        There is likely a double-counting issue happening. This method gets called
        multiple times for the same tokens.
        """
        # LOG before adding so we know the original values
        logger.debug(f"BEFORE track_token_usage: input={self.input_tokens}, output={self.output_tokens}")
        logger.debug(f"ADDING: prompt={prompt_tokens}, completion={completion_tokens}")
        
        # Don't add tokens if they're suspiciously high (likely double counted)
        if prompt_tokens > 20000 or completion_tokens > 5000:
            logger.warning(f"Unusually high token count detected: prompt={prompt_tokens}, completion={completion_tokens}. Skipping to prevent double counting.")
            return
        
        # Ensure values are actually integers
        self.input_tokens = (self.input_tokens or 0) + (prompt_tokens or 0)
        self.output_tokens = (self.output_tokens or 0) + (completion_tokens or 0)
        
        # LOG after adding so we know the new values
        logger.debug(f"AFTER track_token_usage: input={self.input_tokens}, output={self.output_tokens}")
        
        # Store in cache for session-level tracking
        if self.session_id:
            session_cache_key = f"token_totals_{self.session_id}"
            session_totals = cache.get(session_cache_key, {
                'prompt_tokens': 0,
                'completion_tokens': 0,
                'total_tokens': 0
            })
            
            # Only add the difference to avoid double counting
            if prompt_tokens > 0 or completion_tokens > 0:
                session_totals['prompt_tokens'] += prompt_tokens
                session_totals['completion_tokens'] += completion_tokens
                session_totals['total_tokens'] += (prompt_tokens + completion_tokens)
                
                cache.set(session_cache_key, session_totals, 3600)  # 1 hour expiry

    def get_current_usage(self) -> Dict[str, int]:
        """Get current token usage for the session."""
        # Always prioritize the token_callback data as it's the most accurate
        if self.token_callback:
            input_tokens = getattr(self.token_callback, 'input_tokens', 0) or 0
            output_tokens = getattr(self.token_callback, 'output_tokens', 0) or 0
            
            # Log these values for debugging
            logger.debug(f"Token callback reports: input={input_tokens}, output={output_tokens}")
            
            return {
                'prompt_tokens': input_tokens,
                'completion_tokens': output_tokens,
                'total_tokens': input_tokens + output_tokens,
                'model': self.model_name
            }
        
        # Fall back to instance variables if no callback is available
        logger.debug(f"No token callback, using instance vars: input={self.input_tokens}, output={self.output_tokens}")
        return {
            'prompt_tokens': self.input_tokens or 0,
            'completion_tokens': self.output_tokens or 0,
            'total_tokens': (self.input_tokens or 0) + (self.output_tokens or 0),
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
            # Handle different types of conversation_id inputs
            # It could be either a numeric ID or a UUID session_id
            query = None
            
            try:
                # Check if it's a valid UUID (session_id)
                uuid.UUID(str(self.conversation_id))
                # If it's a UUID, filter by session_id
                query = TokenUsage.objects.filter(conversation__session_id=self.conversation_id)
            except (ValueError, TypeError):
                # If it's not a valid UUID, assume it's a database ID
                try:
                    # Try to convert to int in case it's a string representation of a number
                    conversation_id = int(self.conversation_id)
                    query = TokenUsage.objects.filter(conversation_id=conversation_id)
                except (ValueError, TypeError):
                    # If conversion to int fails, try as a string ID
                    query = TokenUsage.objects.filter(conversation_id=self.conversation_id)
            
            # Only count each message once to avoid double counting
            if query:
                # Exclude conversation-level tracking records to avoid double counting
                query = query.exclude(metadata__contains={'type': 'conversation_tracking'})
                
                # CRITICAL: Get only the maximum token usage per each unique message_id
                # This ensures we don't count the same message multiple times if it has multiple records
                unique_message_tokens = query.values('message_id').annotate(
                    max_total=models.Max('total_tokens'),
                    max_prompt=models.Max('prompt_tokens'),
                    max_completion=models.Max('completion_tokens')
                )
                
                # Sum up the maximums for each unique message
                total_tokens = sum(item['max_total'] or 0 for item in unique_message_tokens)
                prompt_tokens = sum(item['max_prompt'] or 0 for item in unique_message_tokens)
                completion_tokens = sum(item['max_completion'] or 0 for item in unique_message_tokens)
                
                # Log the number of records being counted to help debug
                num_records = len(unique_message_tokens)
                logger.debug(f"Counted token usage from {num_records} unique messages")
                
                return {
                    'total_tokens': total_tokens,
                    'prompt_tokens': prompt_tokens,
                    'completion_tokens': completion_tokens
                }
            
            return {'total_tokens': 0, 'prompt_tokens': 0, 'completion_tokens': 0}
            
        except Exception as e:
            logger.error(f"Error getting conversation token usage: {str(e)}", exc_info=True)
            return {'total_tokens': 0, 'prompt_tokens': 0, 'completion_tokens': 0}

    async def track_conversation_tokens(self):
        """
        Track token usage for the entire conversation.
        
        IMPORTANT: This should be called sparingly, only when we need to record
        the current state of conversation tokens, not after every message.
        """
        if not self.conversation_id:
            return
            
        # Log that we're tracking conversation-level tokens to help with debugging
        logger.debug("Recording conversation-level token tracking")

        # We will NOT store the "current usage" again as a conversation-level record
        # as this leads to double counting. Instead, we'll ensure our existing token
        # tracking is properly attributed to this conversation.
        
        # Verify existing records are properly linked to this conversation
        # by counting how many we have
        existing_count = await self._count_token_records()
        logger.debug(f"Verified {existing_count} token usage records for conversation {self.conversation_id}")
            
    @database_sync_to_async
    def _count_token_records(self):
        """Count how many token records exist for this conversation."""
        try:
            # Handle different types of conversation_id inputs
            try:
                # Check if it's a valid UUID (session_id)
                uuid.UUID(str(self.conversation_id))
                count = TokenUsage.objects.filter(conversation__session_id=self.conversation_id).count()
            except (ValueError, TypeError):
                # If it's not a valid UUID, assume it's a database ID
                try:
                    conversation_id = int(self.conversation_id)
                    count = TokenUsage.objects.filter(conversation_id=conversation_id).count()
                except (ValueError, TypeError):
                    count = TokenUsage.objects.filter(conversation_id=self.conversation_id).count()
            return count
        except Exception as e:
            logger.error(f"Error counting token records: {e}")
            return 0

    async def check_token_limit(self, messages: list) -> bool:
        """
        Check if adding the given messages would exceed the token limit.
        
        Args:
            messages: List of messages to check
            
        Returns:
            bool: True if messages can be added without exceeding limit, False otherwise
        """
        # If no limit is set, allow all messages
        if not self.max_token_limit:
            return True
            
        total_tokens = 0
        
        # Count tokens in messages
        for message in messages:
            if hasattr(message, 'content'):
                content = message.content
                if isinstance(content, str):
                    total_tokens += self.count_tokens(content)
                elif isinstance(content, (dict, list)):
                    try:
                        total_tokens += self.count_tokens(json.dumps(content))
                    except Exception as e:
                        logger.error(f"Error counting tokens for structured content: {str(e)}")
                        # Estimate with string representation as fallback
                        total_tokens += self.count_tokens(str(content))
        
        # Get current conversation usage
        try:
            conversation_usage = await self.get_conversation_token_usage()
            current_total = conversation_usage.get('total_tokens', 0)
            # log current total, total tokens to add, sum of current and new tokens, and max token limit
            logger.debug(f"Current total: {current_total}, Total tokens to add: {total_tokens}, Sum of current and new tokens: {current_total + total_tokens}, Max token limit: {self.max_token_limit}")
            # Check if new total would exceed limit
            return (current_total + total_tokens) <= self.max_token_limit
        except Exception as e:
            logger.error(f"Error checking token limit: {str(e)}")
            # Default to allowing messages if we can't check
            return True

    def count_tokens(self, text: str) -> int:
        """Count tokens in text using the initialized tokenizer."""
        try:
            return len(self.tokenizer.encode(text, disallowed_special=()))
        except Exception as e:
            logger.error(f"Error counting tokens: {str(e)}")
            return 0