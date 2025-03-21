import logging
from typing import Dict, Optional, List, Any
import asyncio
from django.utils import timezone
from django.core.cache import cache
from django.conf import settings
from django.db import models
from functools import partial
from channels.db import database_sync_to_async

from langchain_core.messages import (
    BaseMessage,
    SystemMessage,
    AIMessage,
    HumanMessage
)
from langchain.memory import ConversationSummaryBufferMemory
from pydantic import Field

from apps.common.utils import create_box, get_llm
from apps.agents.chat.managers.token_manager import TokenManager
from apps.agents.chat.managers.message_manager import MessageManager

logger = logging.getLogger(__name__)

class ChatServiceError(Exception):
    """Base exception for chat service errors"""
    pass

class ToolExecutionError(ChatServiceError):
    """Raised when a tool execution fails"""
    pass

class TokenLimitError(ChatServiceError):
    """Raised when token limit is exceeded"""
    pass

class CustomConversationSummaryBufferMemory(ConversationSummaryBufferMemory):
    """
    A version of ConversationSummaryBufferMemory that works with any LLM, including Gemini.
    
    This class overrides the token counting method to use our TokenManager instead of
    relying on the LLM's built-in token counting, which may not be implemented for all models.
    """
    
    token_manager: Optional[TokenManager] = Field(default=None, exclude=True)
    
    def get_num_tokens_from_messages(self, messages: List[BaseMessage]) -> int:
        """Calculate number of tokens used by list of messages."""
        if not self.token_manager:
            # Fall back to a simple approximation if token_manager is not available
            buffer_string = "\n".join([f"{m.type}: {m.content}" for m in messages])
            # Approximation: ~4 chars per token as a rough estimate
            return len(buffer_string) // 4
            
        # Use our token manager's count_tokens method for each message
        total_tokens = 0
        for message in messages:
            # Count tokens in the message content
            content_tokens = self.token_manager.count_tokens(message.content)
            # Add a small overhead for message type and formatting
            total_tokens += content_tokens + 4  # 4 tokens overhead per message
            
        return total_tokens
    
    async def aprune(self) -> None:
        """Prune the memory if it exceeds max token limit, using our custom token counting.
        
        This method completely overrides the base class method to avoid calling
        self.llm.get_num_tokens_from_messages() which fails with non-OpenAI models.
        """
        buffer = self.chat_memory.messages
        if not buffer:
            return None
        
        # Use our own get_num_tokens_from_messages method
        curr_buffer_length = self.get_num_tokens_from_messages(buffer)
        
        # Check if we need to prune
        if curr_buffer_length > self.max_token_limit:
            # Number of messages to keep before summarization
            num_messages_to_keep = max(2, len(buffer) // 2)
            
            # Messages to summarize (oldest messages)
            messages_to_summarize = buffer[:-num_messages_to_keep]
            
            # Messages to keep (most recent messages)
            messages_to_keep = buffer[-num_messages_to_keep:]
            
            if not messages_to_summarize:
                # Nothing to summarize
                return None
            
            # Create a summary of older messages
            new_summary = await self._resample_summary(
                messages_to_summarize, 
                self.moving_summary_buffer
            )
            
            # Update the summary buffer
            self.moving_summary_buffer = new_summary
            
            # Update the chat memory with the summary and recent messages
            self.chat_memory.messages = [
                SystemMessage(content=new_summary)
            ] + messages_to_keep

class BaseChatService:
    """Base class for chat services with common functionality for agent and crew interactions"""
    
    def __init__(self, model_name, session_id=None, conversation_id=None):
        self.model_name = model_name
        self.session_id = session_id
        self.conversation_id = conversation_id or f"conv_{self.session_id}"
        self.llm = None
        self.processing = False
        self.processing_lock = asyncio.Lock()
        self.callback_handler = None
        
        # Initialize managers
        self.token_manager = TokenManager(
            conversation_id=self.conversation_id,
            session_id=self.session_id,
            model_name=model_name
        )
        
        self.message_manager = MessageManager(
            conversation_id=self.conversation_id,
            session_id=self.session_id
        )
        
        self.message_history = self.message_manager
    
    def _create_memory(self) -> CustomConversationSummaryBufferMemory:
        """Create memory with summarization for token efficiency using standard LangChain patterns"""
        try:
            # Get the summarizer LLM using the utility function
            summarizer = get_llm(settings.SUMMARIZER)[0]  # Get just the LLM instance
            
            memory = CustomConversationSummaryBufferMemory(
                memory_key="chat_history",
                return_messages=True,
                output_key="output",
                input_key="input",
                llm=summarizer,  # Use just the LLM instance
                max_token_limit=self.token_manager.max_token_limit // 2,
                token_manager=self.token_manager
            )
            
            # Pre-load existing messages from our message store into the memory
            messages = self.message_manager.get_messages_sync()
            for message in messages:
                if isinstance(message, HumanMessage):
                    memory.chat_memory.add_user_message(message.content)
                elif isinstance(message, AIMessage):
                    memory.chat_memory.add_ai_message(message.content)
            
            return memory
        except Exception as e:
            logger.error(f"Error creating memory: {e}", exc_info=True)
            raise
    
    @database_sync_to_async
    def _create_or_get_conversation(self, **kwargs) -> Any:
        """
        Create or get a conversation record.
        This method should be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement _create_or_get_conversation")
    
    async def _count_previous_messages(self) -> int:
        """Count how many messages exist in this conversation before the current turn."""
        try:
            from apps.agents.models import ChatMessage, Conversation
            from channels.db import database_sync_to_async
            
            @database_sync_to_async
            def count_messages():
                if not self.conversation_id:
                    return 0
                try:
                    # Get conversation by its ID
                    conversation = Conversation.objects.filter(id=self.conversation_id).first()
                    if not conversation:
                        return 0
                    return ChatMessage.objects.filter(conversation=conversation).count()
                except Exception as inner_e:
                    logger.error(f"Error finding conversation: {inner_e}")
                    return 0
            
            return await count_messages()
        except Exception as e:
            logger.error(f"Error counting messages: {e}")
            return 0
    
    async def _handle_error(self, error_msg: str, exception: Exception, unexpected: bool = False) -> None:
        """Handle errors consistently"""
        try:
            # Log the error
            logger.error(f"Error in chat service: {error_msg}", exc_info=True)
            
            # Store error message in message history
            if self.message_manager:
                await self.message_manager.add_message(
                    SystemMessage(content=f"Error: {error_msg}"),
                    token_usage=self.token_manager.get_current_usage()
                )
            
            # Send error through callback handler
            if self.callback_handler and hasattr(self.callback_handler, 'on_llm_error'):
                if asyncio.iscoroutinefunction(self.callback_handler.on_llm_error):
                    await self.callback_handler.on_llm_error(error_msg, run_id=None)
                else:
                    self.callback_handler.on_llm_error(error_msg, run_id=None)
                
            if unexpected:
                raise ChatServiceError(str(exception))
            else:
                raise exception
                
        except Exception as e:
            logger.error(f"Error in error handler: {str(e)}", exc_info=True)
            raise ChatServiceError(str(e))
    
    async def get_conversation_token_usage(self) -> Dict:
        """Get total token usage for the conversation"""
        return await self.token_manager.get_conversation_token_usage()

    async def track_tool_token_usage(self, token_usage: Dict, tool_name: str) -> None:
        """Track token usage for tool execution"""
        await self.token_manager.store_token_usage(
            message_id=f"tool_{tool_name}_{timezone.now().timestamp()}",
            token_usage={
                **token_usage,
                'metadata': {'tool_name': tool_name, 'type': 'tool_execution'}
            }
        )
    
    async def handle_edit(self, message_id: str) -> None:
        """Handle message editing"""
        try:
            await self.message_manager.handle_edit(message_id)
        except Exception as e:
            logger.error(f"Error handling edit: {str(e)}")
            raise ChatServiceError("Failed to handle message edit")
    
    async def initialize(self) -> Any:
        """
        Initialize the chat service.
        This method should be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement initialize")
    
    async def process_message(self, message: str, is_edit: bool = False) -> None:
        """
        Process a message.
        This method should be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement process_message") 