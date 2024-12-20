from langchain_core.callbacks import BaseCallbackHandler
import logging
import json
from typing import Any, Dict, List
from datetime import datetime
from langchain_core.agents import  AgentFinish
import asyncio
import textwrap
import uuid
from channels.db import database_sync_to_async
from apps.agents.chat.formatters.table_formatter import TableFormatter
from apps.agents.chat.formatters.output_formatter import OutputFormatter
from langchain.schema import SystemMessage, AIMessage

logger = logging.getLogger(__name__)

class UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return str(obj)
        return super().default(obj)

def create_box(title: str, content: str) -> str:
    """Create a boxed debug message with wrapped content using Unicode box characters."""
    # Box drawing characters
    TOP_LEFT = "┌"
    TOP_RIGHT = "┐"
    BOTTOM_LEFT = "└"
    BOTTOM_RIGHT = "┘"
    HORIZONTAL = "─"
    VERTICAL = "│"
    
    # Wrap content to 80 chars
    wrapped_content = textwrap.fill(str(content), width=80)
    width = max(max(len(line) for line in wrapped_content.split('\n')), len(title)) + 4
    
    # Create box components
    top = f"{TOP_LEFT}{HORIZONTAL * (width-2)}{TOP_RIGHT}"
    title_line = f"{VERTICAL} {title.center(width-4)} {VERTICAL}"
    separator = f"{HORIZONTAL * width}"
    content_lines = [f"{VERTICAL} {line:<{width-4}} {VERTICAL}" for line in wrapped_content.split('\n')]
    bottom = f"{BOTTOM_LEFT}{HORIZONTAL * (width-2)}{BOTTOM_RIGHT}"
    
    return f"\n{top}\n{title_line}\n{separator}\n{chr(10).join(content_lines)}\n{bottom}\n"

class WebSocketCallbackHandler(BaseCallbackHandler):
    """Callback handler that sends only essential messages to the WebSocket."""
    
    def __init__(self, consumer, message_manager=None, token_manager=None):
        """Initialize the handler with a WebSocket consumer and managers"""
        super().__init__()
        self.consumer = consumer
        self.logger = logging.getLogger(__name__)
        self._message_lock = asyncio.Lock()
        self.message_history = []
        self._last_agent_finish = None  # Track last agent finish message
        self.message_manager = message_manager
        self.token_manager = token_manager

    def _log_message(self, title: str, content: Any):
        """Log a message with proper JSON serialization."""
        try:
            if isinstance(content, dict):
                content_str = json.dumps(content, indent=2, cls=UUIDEncoder)
            else:
                content_str = str(content)
            self.logger.debug(create_box(title, content_str))
        except Exception as e:
            self.logger.error(f"Error logging message: {str(e)}")

    async def _send_message(self, message_data):
        """Send message to WebSocket and store in history."""
        try:
            # Store message in history
            self.message_history.append({
                'timestamp': datetime.now().isoformat(),
                'type': message_data.get('type'),
                'content': message_data
            })
            
            # Format message if it's a tool message
            if message_data.get('type', '').startswith('tool_') and self.message_manager:
                message_data['message'] = self.message_manager.format_message(
                    message_data['message'],
                    message_data['type']
                )
            
            # Ensure message is stored in MessageManager
            if self.message_manager and not message_data.get('type') == 'agent_finish':
                content = message_data.get('message', '')
                if isinstance(content, dict):
                    content = json.dumps(content, cls=UUIDEncoder)
                await self.message_manager.add_message(
                    SystemMessage(content=f"{message_data.get('type', 'system')}: {content}"),
                    token_usage=message_data.get('token_usage', {})
                )
            
            async with self._message_lock:
                await self.consumer.send_json(message_data)
                
        except Exception as e:
            self.logger.error(create_box("ERROR IN SEND MESSAGE", str(e)), exc_info=True)

    async def on_agent_finish(self, finish: AgentFinish, **kwargs: Any):
        """Handle agent completion - send final answer and save to database."""
        try:
            # Get token usage and track it
            token_usage = kwargs.get('token_usage', {})
            if self.token_manager:
                self.token_manager.track_token_usage(
                    token_usage.get('prompt_tokens', 0),
                    token_usage.get('completion_tokens', 0)
                )
                await self.token_manager.track_conversation_tokens()
            
            if hasattr(finish, 'return_values'):
                output = finish.return_values.get('output', '')
                
                # Check if this is a duplicate message
                if self._last_agent_finish == output:
                    self.logger.debug("Skipping duplicate agent finish message")
                    return
                
                self._last_agent_finish = output
                
                debug_info = {
                    'output': output,
                    'token_usage': token_usage
                }
                self._log_message("AGENT FINISH EVENT RECEIVED", debug_info)
                
                message = {
                    'type': 'agent_finish',
                    'message': output,
                    'timestamp': datetime.now().isoformat(),
                    'token_usage': token_usage
                }
                
                # Store message using message manager
                if self.message_manager:
                    await self.message_manager.add_message(
                        AIMessage(content=output),
                        token_usage=token_usage
                    )
                
                # Send message to websocket
                await self._send_message(message)
                
        except Exception as e:
            self.logger.error(create_box("ERROR IN AGENT FINISH", str(e)), exc_info=True)

    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any) -> None:
        """Synchronous handler for tool start - required by LangChain."""
        self._log_message("TOOL START (SYNC)", {
            'tool': serialized.get('name', 'Unknown Tool'),
            'input': input_str,
            'kwargs': kwargs
        })

    def on_tool_end(self, output: str, **kwargs: Any) -> None:
        """Synchronous handler for tool end - required by LangChain."""
        self._log_message("TOOL END (SYNC)", {
            'output': output,
            'kwargs': kwargs
        })

    async def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any):
        """Handle tool start - send tool name and input."""
        try:
            # Skip internal exceptions
            if serialized.get('name') == '_Exception':
                return
                
            # Get token usage and track it
            token_usage = kwargs.get('token_usage', {})
            if self.token_manager:
                self.token_manager.track_token_usage(
                    token_usage.get('prompt_tokens', 0),
                    token_usage.get('completion_tokens', 0)
                )
            
            debug_info = {
                'tool': serialized.get('name', 'Unknown Tool'),
                'input': input_str,
                'token_usage': token_usage
            }
            self._log_message("TOOL START EVENT RECEIVED", debug_info)
            
            # Store tool start in message history if manager available
            if self.message_manager:
                await self.message_manager.add_message(
                    SystemMessage(content=f"Tool Start: {serialized.get('name')} - {input_str}"),
                    token_usage=token_usage
                )
            
            # Then send message to websocket
            message = {
                'type': 'tool_start',
                'message': {
                    'name': serialized.get('name', 'Unknown Tool'),
                    'input': input_str,
                    'timestamp': datetime.now().isoformat(),
                    'token_usage': token_usage
                }
            }
            await self._send_message(message)
                
        except Exception as e:
            logger.error(create_box("ERROR IN TOOL START", str(e)), exc_info=True)
            await self.on_tool_error(str(e), **kwargs)

    async def on_tool_end(self, output: str, **kwargs: Any):
        """Handle tool completion - send formatted output."""
        try:
            # Check if this is an error response
            if isinstance(output, dict) and output.get('error'):
                await self.on_tool_error(output['error'], **kwargs)
                return
            
            # Format the output using message manager if available
            formatted_output = output
            if self.message_manager:
                formatted_output = self.message_manager.format_message(output, 'tool_end')
            
            debug_info = {
                'output': formatted_output,
                'token_usage': {}  # Tools don't typically use tokens
            }
            self._log_message("TOOL END EVENT RECEIVED", debug_info)
            
            message = {
                'type': 'tool_end',
                'message': {
                    'output': formatted_output,
                    'timestamp': datetime.now().isoformat(),
                    'token_usage': {}  # Tools don't typically use tokens
                }
            }
            await self._send_message(message)
            
            # Store tool end in message history if manager available
            if self.message_manager:
                await self.message_manager.add_message(
                    SystemMessage(content=f"Tool Result: {formatted_output}"),
                    token_usage={}  # Tools don't typically use tokens
                )
                
        except Exception as e:
            self.logger.error(create_box("ERROR IN TOOL END", str(e)), exc_info=True)
            await self.on_tool_error(str(e), **kwargs)

    async def on_tool_error(self, error: str, **kwargs: Any):
        """Handle tool errors"""
        try:
            # Get token usage from kwargs if available
            token_usage = kwargs.get('token_usage', {})
            if self.token_manager:
                self.token_manager.track_token_usage(
                    token_usage.get('prompt_tokens', 0),
                    token_usage.get('completion_tokens', 0)
                )
            
            error_info = {
                'error': error,
                'token_usage': token_usage
            }
            self._log_message("TOOL ERROR EVENT RECEIVED", error_info)
            
            message = {
                'type': 'tool_error',
                'message': {
                    'error': error,
                    'timestamp': datetime.now().isoformat(),
                    'token_usage': token_usage
                }
            }
            await self._send_message(message)
            
            # Store error in message history if manager available
            if self.message_manager:
                await self.message_manager.add_message(
                    SystemMessage(content=f"Tool Error: {error}"),
                    token_usage=token_usage
                )
                
        except Exception as e:
            self.logger.error(create_box("ERROR IN TOOL ERROR HANDLER", str(e)), exc_info=True)