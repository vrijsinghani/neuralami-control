from langchain.agents import AgentExecutor, create_structured_chat_agent
from langchain.memory import ConversationSummaryBufferMemory
from langchain_core.messages import (
    BaseMessage,
    SystemMessage,
    AIMessage,
    HumanMessage
)
from channels.db import database_sync_to_async
from apps.common.utils import create_box
import logging
from django.utils import timezone
from apps.common.utils import get_llm
from django.core.cache import cache
from typing import Optional, List, Any, Dict
import asyncio
from apps.seo_manager.models import Client
from django.db import models
from pydantic import ValidationError, Field
from langchain_core.agents import AgentFinish
import re
from apps.common.utils import create_box
import json
from django.conf import settings

# Import our new managers
from apps.agents.chat.managers.token_manager import TokenManager
from apps.agents.chat.managers.tool_manager import ToolManager
from apps.agents.chat.managers.prompt_manager import PromptManager
from apps.agents.chat.managers.message_manager import MessageManager
from apps.agents.websockets.handlers.callback_handler import WebSocketCallbackHandler

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

class ChatService:
    def __init__(self, agent, model_name, client_data, callback_handler, session_id=None):
        self.agent = agent
        self.model_name = model_name
        self.client_data = client_data
        self.callback_handler = callback_handler
        self.llm = None
        self.agent_executor = None
        self.processing = False
        self.tool_cache = {}  # Cache for tool results
        self.session_id = session_id or f"{agent.id}_{client_data['client_id'] if client_data else 'no_client'}"
        self.processing_lock = asyncio.Lock()
        
        # Create conversation ID from session ID if not provided
        self.conversation_id = f"conv_{self.session_id}"
        
        # Initialize managers with conversation ID
        self.token_manager = TokenManager(
            conversation_id=self.conversation_id,
            session_id=self.session_id,
            model_name=model_name
        )
        
        self.message_manager = MessageManager(
            conversation_id=self.conversation_id,
            session_id=self.session_id
        )
        
        self.tool_manager = ToolManager()
        self.prompt_manager = PromptManager()
        
        # Set up message history with token management
        self.message_history = self.message_manager
        
        # Update callback handler with managers
        if isinstance(self.callback_handler, WebSocketCallbackHandler):
            self.callback_handler.message_manager = self.message_manager
            self.callback_handler.token_manager = self.token_manager
            
    def _create_memory(self) -> CustomConversationSummaryBufferMemory:
        """Create memory with summarization for token efficiency using standard LangChain patterns"""
        try:
            # Create standard CustomConversationSummaryBufferMemory
            memory = CustomConversationSummaryBufferMemory(
                memory_key="chat_history",
                return_messages=True,
                output_key="output",
                input_key="input",
                llm=self.llm,
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

    async def initialize(self) -> Optional[AgentExecutor]:
        """Initialize the chat service with LLM and agent"""
        try:
            # Get client if needed for conversation, but preserve original client_data
            client = None
            if self.client_data and self.client_data.get('client_id'):
                try:
                    client = await database_sync_to_async(Client.objects.get)(id=self.client_data['client_id'])
                except Client.DoesNotExist:
                    logger.error(f"Client not found with ID: {self.client_data['client_id']}")
                    raise ValueError(f"Client not found with ID: {self.client_data['client_id']}")

            # Create or get conversation - pass the client object directly, not in a dict
            conversation = await self._create_or_get_conversation(client)
            
            # Update managers with conversation ID
            self.conversation_id = str(conversation.id)
            self.token_manager.conversation_id = self.conversation_id
            self.message_manager.conversation_id = self.conversation_id

            # Get LLM with token tracking
            self.llm, token_callback = get_llm(
                model_name=self.model_name,
                temperature=0.7,
            )
            
            # Set up token tracking
            self.llm.callbacks = [token_callback]
            logger.debug(f"Setting up token tracking with callback: {token_callback}")
            self.token_manager.set_token_callback(token_callback)

            # Initialize memory with proper message handling
            # Need to use sync_to_async here since _create_memory makes sync DB calls
            create_memory_async = database_sync_to_async(self._create_memory)
            memory = await create_memory_async()
            
            # Get chat history for the agent executor
            chat_history = await self.message_manager.get_messages()

            # Load tools using tool manager
            tools = await self.tool_manager.load_tools(self.agent)
            
            # Create the agent-specific system prompt with client context using prompt manager
            system_prompt = self.prompt_manager.create_agent_prompt(self.agent, self.client_data)
            
            # Create prompt using prompt manager - pass raw data
            prompt = self.prompt_manager.create_chat_prompt(
                system_prompt=system_prompt,
                tools=tools,
                chat_history=chat_history
            )

            # Create the agent
            agent = create_structured_chat_agent(
                llm=self.llm,
                tools=tools,
                prompt=prompt
            )

            # Create agent executor with memory
            self.agent_executor = AgentExecutor.from_agent_and_tools(
                agent=agent,
                tools=tools,
                memory=memory,
                verbose=True,
                max_iterations=25,
                handle_parsing_errors=True,
                return_intermediate_steps=True,
                callbacks=[self.callback_handler, token_callback]
            )
            logger.debug(f"Created agent executor with callbacks: {[self.callback_handler, token_callback]}")

            # Reset session token totals
            await self.token_manager._reset_session_token_totals()

            return self.agent_executor

        except Exception as e:
            logger.error(f"Error initializing chat service: {str(e)}", exc_info=True)
            raise
            
    @database_sync_to_async
    def _create_or_get_conversation(self, client=None) -> Any:
        """Create or get a conversation record."""
        try:
            from apps.agents.models import Conversation
            
            # Try to get existing conversation
            conversation = Conversation.objects.filter(
                session_id=self.session_id
            ).first()
            
            if not conversation:
                # Create new conversation
                conversation = Conversation.objects.create(
                    session_id=self.session_id,
                    agent_id=self.agent.id,
                    client=client,
                    user_id=self.client_data.get('user_id') if self.client_data else None
                )
            
            return conversation
            
        except Exception as e:
            logger.error(f"Error creating/getting conversation: {str(e)}", exc_info=True)
            raise

    async def process_message(self, message: str, is_edit: bool = False) -> None:
        async with self.processing_lock:
            try:
                # Reset token tracking
                self.token_manager.reset_tracking()
                logger.debug(create_box("Reset token tracking", ""))

                # Get chat history
                chat_history = await self.message_manager.get_messages()

                # Ensure chat history is a list of BaseMessage objects
                if not all(isinstance(msg, BaseMessage) for msg in chat_history):
                    logger.warning("Chat history contains non-BaseMessage objects")
                    chat_history = []

                logger.debug(create_box("Invoking agent with callbacks", f"{[self.callback_handler, self.llm.callbacks[0]]}"))
                # Get agent response
                response = await self.agent_executor.ainvoke(
                    {
                        "input": message,
                        "chat_history": chat_history
                    },
                    {"callbacks": [self.callback_handler, self.llm.callbacks[0]]}
                )
                
                # Log response safely by extracting output string
                response_str = response.get('output', str(response))
                if isinstance(response_str, str):
                    logger.debug(create_box("Agent response received", f"{response_str[-250:] if len(response_str) > 250 else response_str}"))
                else:
                    logger.debug(create_box("Agent response received", str(response)))
                    
                # Save the agent's response
                if isinstance(response, dict) and 'output' in response:
                    await self._handle_response(response['output'])
                    
                    # Also save message to our message manager
                    await self.message_manager.add_message(HumanMessage(content=message))
                    await self.message_manager.add_message(AIMessage(content=response['output']))

            except Exception as e:
                logger.error(f"Error in process_message: {str(e)}", exc_info=True)
                await self._handle_error(str(e), e, unexpected=True)

    async def _handle_response(self, response: str) -> None:
        """Handle successful response"""
        try:
            # Get current token usage for this turn (this includes all tools + agent response)
            turn_token_usage = self.token_manager.get_current_usage()
                
            # For a brand new conversation, don't try to get previous conversation tokens
            # This fixes the bug where it shows 58k tokens for a first turn
            conversation_token_usage = {'total_tokens': 0, 'prompt_tokens': 0, 'completion_tokens': 0}
            
            # Check if this is actually a continuing conversation with previous turns
            message_count = await self._count_previous_messages()
            if message_count > 0:
                try:
                    # Only get previous conversation tokens if we have prior messages
                    conversation_token_usage = await self.token_manager.get_conversation_token_usage()
                    logger.debug(f"Found {message_count} previous messages in this conversation")
                except Exception as e:
                    logger.error(f"Error getting conversation token usage: {str(e)}")
            else:
                logger.debug("This is a new conversation with no previous turns")
            
            # Clear logging with just the essential information
            logger.debug(create_box("THIS TURN'S TOKENS", f"{turn_token_usage.get('total_tokens', 0)} tokens"))
            if message_count > 0:
                logger.debug(create_box("PREVIOUS TURNS' TOKENS", f"{conversation_token_usage.get('total_tokens', 0)} tokens"))
            
            # Send through callback handler for WebSocket communication
            await self.callback_handler.on_agent_finish(
                AgentFinish(
                    return_values={'output': response},
                    log='',
                ),
                token_usage=turn_token_usage  # Just pass the current turn usage
            )
        except Exception as e:
            logger.error(f"Error handling response: {str(e)}", exc_info=True)
            await self._handle_error("Failed to handle response", e)

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

    async def handle_edit(self, message_id: str) -> None:
        """Handle message editing"""
        try:
            await self.message_manager.handle_edit(message_id)
        except Exception as e:
            logger.error(f"Error handling edit: {str(e)}")
            raise ChatServiceError("Failed to handle message edit")

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