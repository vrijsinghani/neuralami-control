from langchain.agents import AgentExecutor, create_structured_chat_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.memory import ConversationBufferMemory
from langchain_core.messages import (
    BaseMessage,
    HumanMessage, 
    AIMessage,

    SystemMessage
)
from channels.db import database_sync_to_async
import json
import logging
from django.utils import timezone
from apps.common.utils import get_llm
from django.core.cache import cache
from typing import Optional, List, Any, Dict
import asyncio
from apps.seo_manager.models import Client
from django.db import models
from pydantic import ValidationError
from langchain_core.agents import AgentFinish
import re

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
            max_token_limit=64000,
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

    async def initialize(self) -> Optional[AgentExecutor]:
        """Initialize the chat service with LLM and agent"""
        try:
            # Validate and get client if present
            client_data = None
            if self.client_data and self.client_data.get('client_id'):
                try:
                    client = await database_sync_to_async(Client.objects.get)(id=self.client_data['client_id'])
                    client_data = {'client': client}
                except Client.DoesNotExist:
                    logger.error(f"Client not found with ID: {self.client_data['client_id']}")
                    raise ValueError(f"Client not found with ID: {self.client_data['client_id']}")

            # Create or get conversation
            conversation = await self._create_or_get_conversation(client_data['client'] if client_data else None)
            
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
            self.token_manager.set_token_callback(token_callback)

            # Initialize memory with proper message handling
            memory = ConversationBufferMemory(
                memory_key="chat_history",
                return_messages=True,
                chat_memory=self.message_manager,
                output_key="output",
                input_key="input"
            )

            # Load tools using tool manager
            tools = await self.tool_manager.load_tools(self.agent)

            # Get tool names and descriptions
            tool_names = [tool.name for tool in tools]
            tool_descriptions = [f"{tool.name}: {tool.description}" for tool in tools]

            # Get chat history and ensure it's a list of BaseMessage objects
            chat_history = await self.message_manager.get_messages()
            if not isinstance(chat_history, list):
                chat_history = []
            
            # Create the agent-specific system prompt with client context using prompt manager
            system_prompt = self.prompt_manager.create_agent_prompt(self.agent, client_data)
            
            # Create prompt using prompt manager
            prompt = self.prompt_manager.create_chat_prompt(
                system_prompt=system_prompt,
                additional_context={
                    "tools": "\n".join(tool_descriptions),
                    "tool_names": ", ".join(tool_names),
                    "agent_scratchpad": "{agent_scratchpad}",
                    "chat_history": chat_history,  # Pass the raw messages, let prompt manager format them
                    "client_data": client_data
                }
            )

            # Create the agent
            agent = create_structured_chat_agent(
                llm=self.llm,
                tools=tools,
                prompt=prompt
            )

            # Create agent executor with memory
            self.agent_executor = AgentExecutor(
                agent=agent,
                tools=tools,
                memory=memory,
                verbose=True,
                max_iterations=25,  
                handle_parsing_errors=True,
            )

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

    def _create_token_aware_memory(self) -> ConversationBufferMemory:
        """Create memory with token limit enforcement"""
        memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True,
            chat_memory=self.message_manager,
            output_key="output",
            input_key="input"
        )

        # Wrap the add_message methods to check token counts
        original_add_message = self.message_manager.add_message

        async def wrapped_add_message(message: BaseMessage, **kwargs) -> None:
            """Async wrapper for add_message that handles token usage"""
            try:
                # Check token limit before adding message
                if not await self.token_manager.check_token_limit([message]):
                    raise TokenLimitError("Message would exceed token limit")
                    
                # Pass through any additional kwargs (including token_usage)
                await original_add_message(message, **kwargs)
            except Exception as e:
                logger.error(f"Error in wrapped_add_message: {str(e)}")
                raise

        # Replace the add_message method with our wrapped version
        self.message_manager.add_message = wrapped_add_message

        return memory

    def _create_box(self, content: str, title: str = "", width: int = 80) -> str:
        """Create a pretty ASCII box with content for logging"""
        lines = []
        
        # Top border with title
        if title:
            title = f" {title} "
            padding = (width - len(title)) // 2
            lines.append("╔" + "═" * padding + title + "═" * (width - padding - len(title)) + "╗")
        else:
            lines.append("╔" + "═" * width + "╗")
            
        # Content
        for line in content.split('\n'):
            # Split long lines
            while len(line) > width:
                split_at = line[:width].rfind(' ')
                if split_at == -1:
                    split_at = width
                lines.append("║ " + line[:split_at].ljust(width-2) + " ║")
                line = line[split_at:].lstrip()
            lines.append("║ " + line.ljust(width-2) + " ║")
            
        # Bottom border
        lines.append("╚" + "═" * width + "╝")
        
        return "\n".join(lines)

    async def process_message(self, message: str, is_edit: bool = False) -> None:
        """Handles all LLM/tool interactions"""
        async with self.processing_lock:
            try:
                # Reset token tracking
                self.token_manager.reset_tracking()

                # Log user input
                logger.info(f"Processing message: {message}")
                
                # Store user message in message history
                await self.message_manager.add_message(
                    HumanMessage(content=message),
                    token_usage=self.token_manager.get_current_usage()
                )

                # Get agent response with preprocessing - just like testagent.py main()
                response = await self.agent_executor.ainvoke(
                    {
                        "input": message,
                        "chat_history": await self.message_manager.get_messages()
                    },
                    {"callbacks": [self.callback_handler, self.llm.callbacks[0]]}  # Use the token_callback from llm
                )

                # Save the agent's response to the database
                if isinstance(response, dict) and 'output' in response:
                    await self._handle_response(response['output'])

            except Exception as e:
                logger.error(f"Error in process_message: {str(e)}")
                # Pass run_id=None since we're in an error state
                await self._handle_error(str(e), e, unexpected=True)

    async def _handle_response(self, response: str) -> None:
        """Handle successful response"""
        try:
            # Get current token usage
            token_usage = self.token_manager.get_current_usage()
            
            # Add message using message manager for memory/history
            await self.message_manager.add_message(
                AIMessage(content=response),
                token_usage=token_usage
            )
            
            # Send through callback handler for WebSocket communication
            await self.callback_handler.on_agent_finish(
                AgentFinish(
                    return_values={'output': response},
                    log='',
                ),
                token_usage=token_usage
            )
        except Exception as e:
            logger.error(f"Error handling response: {str(e)}", exc_info=True)
            await self._handle_error("Failed to handle response", e)

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
            await self.callback_handler.on_llm_error(error_msg)
            
            if unexpected:
                raise ChatServiceError(str(exception))
            else:
                raise exception
                
        except Exception as e:
            logger.error(f"Error in error handler: {str(e)}", exc_info=True)
            raise ChatServiceError(str(e))

    async def handle_edit(self) -> None:
        """Handle message editing"""
        try:
            await self.message_manager.handle_edit()
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