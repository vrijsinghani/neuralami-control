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
        # get first 250 characters of content 
        content_str = str(content)[:250] + "..." if len(str(content)) > 250 else str(content)
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

    async def on_agent_finish(self, finish: AgentFinish, **kwargs: Any) -> None:
        """Handle agent completion - send final answer and save to database."""
        try:
            if hasattr(finish, 'return_values'):
                output = finish.return_values.get('output', '')
                
                # Check if this is a duplicate message
                if self._last_agent_finish == output:
                    self.logger.debug("Skipping duplicate agent finish message")
                    return
                
                self._last_agent_finish = output
                
                # Extract token usage from kwargs
                token_usage = kwargs.get('token_usage', {})
                turn_tokens = token_usage.get('turn', {})
                
                # If we have nested structure, use it properly
                if 'turn' in token_usage and 'conversation' in token_usage:
                    # Use the 'turn' part for logging in this method
                    token_usage = turn_tokens
                
                # Make sure we always have token usage data to show
                if not token_usage or len(token_usage) == 0:
                    if self.token_manager:
                        token_usage = self.token_manager.get_current_usage()
                
                # Track tokens if we have a token manager
                if self.token_manager:
                    # Use the existing token usage rather than recounting
                    if 'prompt_tokens' in token_usage and 'completion_tokens' in token_usage:
                        pass  # already counted by LLM callback
                    else:
                        # Fall back to token manager tracking
                        self.token_manager.track_token_usage(
                            token_usage.get('prompt_tokens', 0),
                            token_usage.get('completion_tokens', 0)
                        )
                    
                    # Track conversation tokens AFTER tracking the current usage
                    await self.token_manager.track_conversation_tokens()
                
                debug_info = {
                    'output': output,
                    'token_usage': token_usage
                }
                self._log_message("AGENT FINISH EVENT RECEIVED", debug_info)
                # Convert dictionary output to string if necessary
                message_content = (
                    json.dumps(output, indent=2)
                    if isinstance(output, dict)
                    else str(output)
                )
                # Store message using message manager and get the message ID
                stored_message = None
                if self.message_manager:
                    stored_message = await self.message_manager.add_message(
                        AIMessage(content=message_content),
                        token_usage=token_usage
                    )
                
                message = {
                    'type': 'agent_finish',
                    'message': message_content,
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
            
            # Enhanced debugging: log detailed information about tool calls
            try:
                tool_input = input_str
                if isinstance(tool_input, str):
                    # Try to parse if it's a JSON string
                    try:
                        input_obj = json.loads(tool_input)
                        logger.info(f"TOOL PARAMETERS FOR {tool_name}: {json.dumps(input_obj, indent=2)}")
                    except json.JSONDecodeError:
                        logger.info(f"TOOL INPUT FOR {tool_name} (raw string): {tool_input}")
                else:
                    logger.info(f"TOOL INPUT FOR {tool_name} (non-string): {type(tool_input)}")
            except Exception as e:
                logger.error(f"Error during tool input logging: {str(e)}")
            
            # Store in message history if manager available
            stored_message = None
            if self.message_manager:
                stored_message = await self.message_manager.add_message(
                    SystemMessage(content=f"Tool Start: {tool_name}"),
                    token_usage=token_usage
                )
            
            # Send message to websocket
            message = {
                'type': 'tool_start',
                'content': {
                    'tool': tool_name
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
            # Get token usage from kwargs (current operation)
            token_usage = kwargs.get('token_usage', {})
            
            # Track tokens if we have a token manager
            if self.token_manager:
                # Track the token usage from this operation
                self.token_manager.track_token_usage(
                    token_usage.get('prompt_tokens', 0),
                    token_usage.get('completion_tokens', 0)
                )
                
                # Always ensure we have a valid token_usage to report
                # If the kwargs didn't include token usage, get the current usage
                if not token_usage or not token_usage.get('total_tokens'):
                    token_usage = self.token_manager.get_current_usage()

            # Log the output with token usage
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

            # Get tool name if available
            tool_name = kwargs.get('name', 'unknown_tool')
            
            # Store in message history if manager available
            stored_message = None
            if self.message_manager:
                # Create a SystemMessage with tool data in additional_kwargs
                tool_message = SystemMessage(
                    content="Tool Result",
                    additional_kwargs={
                        'tool_call': {
                            'name': tool_name,
                            'output': data
                        }
                    }
                )
                stored_message = await self.message_manager.add_message(
                    tool_message,
                    token_usage=token_usage
                )

            # Send message to websocket
            message = {
                'type': 'tool_result',
                'content': data,
                'timestamp': datetime.now().isoformat(),
                'token_usage': token_usage,
                'id': str(stored_message.id) if stored_message else None,
                'additional_kwargs': {
                    'tool_call': {
                        'name': tool_name,
                        'output': data
                    }
                }
            }
            await self.consumer.send_json(message)
                
        except Exception as e:
            self.logger.error(create_box("ERROR IN TOOL END", str(e)), exc_info=True)

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
            
            # Get tool name if available
            tool_name = kwargs.get('name', 'unknown_tool')
            
            # Store error in message history if manager available
            stored_message = None
            if self.message_manager:
                # Create a SystemMessage with tool error data in additional_kwargs
                error_message = SystemMessage(
                    content=f"Tool Error: {error}",
                    additional_kwargs={
                        'tool_call': {
                            'name': tool_name,
                            'output': {'error': error}
                        }
                    }
                )
                stored_message = await self.message_manager.add_message(
                    error_message,
                    token_usage=token_usage
                )
            
            # Send error message to websocket
            message = {
                'type': 'tool_result',
                'content': {'error': error},
                'timestamp': datetime.now().isoformat(),
                'token_usage': token_usage,
                'id': str(stored_message.id) if stored_message else None,
                'additional_kwargs': {
                    'tool_call': {
                        'name': tool_name,
                        'output': {'error': error}
                    }
                }
            }
            await self.consumer.send_json(message)
                
        except Exception as e:
            self.logger.error(create_box("ERROR IN TOOL ERROR HANDLER", str(e)), exc_info=True)

    def _handle_tool_end(self, data):
        try:
            logger.debug("Processing tool end event")
            output = data.get('output')
            
            if not output:
                logger.error("Tool end event received with no output")
                return {"output": "No output received", "token_usage": {}}
            
            # Validate output structure
            if isinstance(output, dict):
                # Log successful processing with truncated preview
                output_preview = str(output)[:250] + "..." if len(str(output)) > 250 else str(output)
                logger.debug(f"Successfully processed tool output: {type(output)}, preview: {output_preview}")
                return data
            elif isinstance(output, str):
                # Handle string output with truncation
                output_preview = output[:250] + "..." if len(output) > 250 else output
                logger.debug(f"Received string output from tool: {output_preview}")
                return data
            else:
                logger.error(f"Unexpected output type: {type(output)}")
                return {"output": f"Unexpected output type: {type(output)}", "token_usage": {}}
            
        except Exception as e:
            logger.error(f"Error processing tool end event: {str(e)}", exc_info=True)
            return {"output": "Error processing tool output", "token_usage": {}}