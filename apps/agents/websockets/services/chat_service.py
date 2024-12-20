from langchain.agents import AgentExecutor, create_structured_chat_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.memory import ConversationBufferMemory
from langchain_core.messages import (
    BaseMessage,
    HumanMessage, 
    AIMessage,
    messages_from_dict,
    messages_to_dict
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
        
        # Initialize managers
        self.token_manager = TokenManager(
            conversation_id=None,  # Will be set after message_manager initialization
            session_id=self.session_id,
            max_token_limit=64000,
            model_name=model_name
        )
        
        self.message_manager = MessageManager(
            conversation_id=None,  # Will be set during initialization
            session_id=self.session_id
        )
        
        self.tool_manager = ToolManager()
        self.prompt_manager = PromptManager()
        
        # Set up message history with token management
        self.message_history = self.message_manager
        
        # Update token manager with conversation ID once available
        if hasattr(self.message_history, 'conversation_id'):
            self.token_manager.conversation_id = self.message_history.conversation_id
            self.message_manager.conversation_id = self.message_history.conversation_id

    async def initialize(self) -> Optional[AgentExecutor]:
        """Initialize the chat service with LLM and agent"""
        try:
            # Validate client_id if present
            if self.client_data and self.client_data.get('client_id'):
                from apps.seo_manager.models import Client
                try:
                    client = await database_sync_to_async(Client.objects.get)(id=self.client_data['client_id'])
                except Client.DoesNotExist:
                    logger.error(f"Client not found with ID: {self.client_data['client_id']}")
                    raise ValueError(f"Client not found with ID: {self.client_data['client_id']}")

            # Get LLM with token tracking
            self.llm, token_callback = get_llm(
                model_name=self.model_name,
                temperature=0.7,
            )
            
            # Set up token tracking
            self.llm.callbacks = [token_callback]
            self.token_manager.set_token_callback(token_callback)

            # Initialize memory
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

            # Get chat history for prompt
            chat_history = await self.message_manager.get_messages()
            
            # Create prompt using prompt manager
            prompt = self.prompt_manager.create_chat_prompt(
                system_prompt=await self._create_agent_prompt(),
                additional_context={
                    "tools": "\n".join(tool_descriptions),
                    "tool_names": ", ".join(tool_names),
                    "agent_scratchpad": "{agent_scratchpad}",
                    "chat_history": str(chat_history)
                }
            )

            # Create the agent
            agent = create_structured_chat_agent(
                llm=self.llm,
                tools=tools,
                prompt=prompt
            )

            # Create agent executor with simpler config like testagent.py
            self.agent_executor = AgentExecutor(
                agent=agent,
                tools=tools,
                memory=memory,
                verbose=True,
                max_iterations=5,  
                handle_parsing_errors=True,
            )

            # Reset session token totals
            await self.token_manager._reset_session_token_totals()

            return self.agent_executor

        except Exception as e:
            logger.error(f"Error initializing chat service: {str(e)}", exc_info=True)
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

    @database_sync_to_async
    def _create_agent_prompt(self):
        """Create the system prompt for the agent"""
        try:
            if self.client_data and self.client_data.get('client_id'):
                # Get client synchronously since we're already in a sync context due to decorator
                client = Client.objects.select_related().get(id=self.client_data['client_id'])
                client_data = {'client': client}
            else:
                client_data = None
                
            return self.prompt_manager.create_agent_prompt(self.agent, client_data)
            
        except Client.DoesNotExist:
            logger.error(f"Client not found with ID: {self.client_data.get('client_id')}")
            return self.prompt_manager.create_agent_prompt(self.agent)
        except Exception as e:
            logger.error(f"Error creating agent prompt: {str(e)}", exc_info=True)
            return self.prompt_manager.create_agent_prompt(self.agent)

    def _create_default_prompt(self) -> str:
        """Create a default system prompt when client context is unavailable"""
        return f"""You are {self.agent.name}, an AI assistant.

Role: {self.agent.role}

Goal: {self.agent.goal if hasattr(self.agent, 'goal') else 'Help users accomplish their tasks effectively.'}

Current Context:
- Current Date: {timezone.now().strftime('%Y-%m-%d')}
"""

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
                await self.callback_handler.on_llm_error(error=str(e), run_id=None)

    async def _handle_response(self, response: str) -> None:
        """Handle successful response"""
        try:
            # Add message using message manager for memory/history
            await self.message_manager.add_message(
                AIMessage(content=response),
                token_usage=self.token_manager.get_current_usage()
            )
            
            # Also save through callback handler to ensure DB persistence
            await self.callback_handler.on_agent_finish(
                AgentFinish(
                    return_values={'output': response},
                    log='',
                ),
                token_usage=self.token_manager.get_current_usage()
            )
        except Exception as e:
            logger.error(f"Error handling response: {str(e)}", exc_info=True)
            raise ChatServiceError("Failed to handle response")

    async def _handle_error(self, error_msg: str, exception: Exception, unexpected: bool = False) -> None:
        """Handle errors consistently"""
        await self.callback_handler.on_llm_error(error_msg)
        if unexpected:
            logger.error(f"Unexpected error: {str(exception)}", exc_info=True)
            raise ChatServiceError(str(exception))
        else:
            logger.warning(f"Known error: {str(exception)}")
            raise exception

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