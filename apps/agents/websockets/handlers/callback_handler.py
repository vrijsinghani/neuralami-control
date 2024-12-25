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
from apps.common.utils import create_box
from langchain.schema import SystemMessage, AIMessage
from django.utils import timezone

logger = logging.getLogger(__name__)

class UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return str(obj)
        return super().default(obj)


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
            
            # Add message ID if this is a message that was stored in DB
            if hasattr(self, '_last_message_id') and self._last_message_id:
                message_data['id'] = self._last_message_id
                self._last_message_id = None  # Clear it after use
            
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
                
                # Store message using message manager and get the message ID
                stored_message = None
                if self.message_manager:
                    stored_message = await self.message_manager.add_message(
                        AIMessage(content=output),
                        token_usage=token_usage
                    )
                
                message = {
                    'type': 'agent_finish',
                    'message': output,
                    'timestamp': datetime.now().isoformat(),
                    'token_usage': token_usage,
                    'id': str(stored_message.id) if stored_message else None
                }
                
                # Send message to websocket
                await self._send_message(message)
                
        except Exception as e:
            self.logger.error(create_box("ERROR IN AGENT FINISH", str(e)), exc_info=True)

    def on_tool_start_sync(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any) -> None:
        """Synchronous handler for tool start - required by LangChain."""
        self._log_message("TOOL START (SYNC)", {
            'tool': serialized.get('name', 'Unknown Tool'),
            'input': input_str,
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
            
            tool_name = serialized.get('name', 'Unknown Tool')
            
            # Store in message history if manager available
            stored_message = None
            if self.message_manager:
                stored_message = await self.message_manager.add_message(
                    SystemMessage(content=f"Tool Start: {tool_name} - {input_str}"),
                    token_usage=token_usage
                )
            
            # Send message to websocket
            message = {
                'type': 'tool_start',
                'content': {
                    'tool': tool_name,
                    'input': input_str
                },
                'timestamp': datetime.now().isoformat(),
                'token_usage': token_usage,
                'id': str(stored_message.id) if stored_message else None
            }
            await self.consumer.send_json(message)
                
        except Exception as e:
            logger.error(create_box("ERROR IN TOOL START", str(e)), exc_info=True)
            await self.on_tool_error(str(e), **kwargs)

    async def on_tool_end(self, output: str, **kwargs: Any) -> None:
        """Handle tool completion."""
        try:
            # Get token usage
            token_usage = kwargs.get('token_usage', {})
            if self.token_manager:
                self.token_manager.track_token_usage(
                    token_usage.get('prompt_tokens', 0),
                    token_usage.get('completion_tokens', 0)
                )

            # Log the output
            self._log_message("TOOL END EVENT RECEIVED", {
                "output": output,
                "token_usage": token_usage
            })

            # Parse output
            if isinstance(output, str):
                try:
                    data = json.loads(output)
                except json.JSONDecodeError:
                    data = {"text": output}
            else:
                data = output

            # Store in message history if manager available
            stored_message = None
            if self.message_manager:
                content = json.dumps(data, indent=2) if isinstance(data, dict) else str(data)
                stored_message = await self.message_manager.add_message(
                    SystemMessage(content=f"Tool Result: {content}"),
                    token_usage=token_usage
                )

            # Send message to websocket
            message = {
                'type': 'tool_result',
                'content': data,
                'timestamp': datetime.now().isoformat(),
                'token_usage': token_usage,
                'id': str(stored_message.id) if stored_message else None
            }
            await self.consumer.send_json(message)

        except Exception as e:
            logger.error(f"Error in on_tool_end: {str(e)}", exc_info=True)

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
            
            # Store error in message history if manager available
            stored_message = None
            if self.message_manager:
                stored_message = await self.message_manager.add_message(
                    SystemMessage(content=f"Tool Error: {error}"),
                    token_usage=token_usage
                )
            
            # Send error message to websocket
            message = {
                'type': 'tool_result',
                'content': {'error': error},
                'timestamp': datetime.now().isoformat(),
                'token_usage': token_usage,
                'id': str(stored_message.id) if stored_message else None
            }
            await self.consumer.send_json(message)
                
        except Exception as e:
            self.logger.error(create_box("ERROR IN TOOL ERROR HANDLER", str(e)), exc_info=True)