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
    
    def __init__(self, consumer):
        """Initialize the handler with a WebSocket consumer"""
        super().__init__()
        self.consumer = consumer
        self.logger = logging.getLogger(__name__)
        self._message_lock = asyncio.Lock()
        self.message_history = []
        self._last_agent_finish = None  # Track last agent finish message

    @database_sync_to_async
    def _save_message_to_db(self, content: str, is_agent: bool = True):
        """Save message to database."""
        from apps.agents.models import ChatMessage, Conversation
        try:
            # Get the conversation to get the agent_id
            conversation = Conversation.objects.filter(
                session_id=self.consumer.session_id
            ).first()
            
            if not conversation or not conversation.agent_id:
                self.logger.error("No conversation or agent_id found for session")
                return None
                
            chat_message = ChatMessage.objects.create(
                session_id=self.consumer.session_id,
                content=content,
                is_agent=is_agent,
                agent_id=conversation.agent_id,  # Get agent_id from conversation
                user_id=1,  # Default user ID
            )
            return chat_message
        except Exception as e:
            self.logger.error(f"Error saving message to database: {str(e)}", exc_info=True)
            raise

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
            #self._log_message("SENDING WEBSOCKET MESSAGE", message_data)
            
            # Store message in history
            self.message_history.append({
                'timestamp': datetime.now().isoformat(),
                'type': message_data.get('type'),
                'content': message_data
            })
            
            async with self._message_lock:
                await self.consumer.send_json(message_data)
                
            #self._log_message("MESSAGE HISTORY", self.message_history)
        except Exception as e:
            self.logger.error(create_box("ERROR IN SEND MESSAGE", str(e)), exc_info=True)

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
            # Get token usage from kwargs if available
            token_usage = kwargs.get('token_usage', {})
            input_tokens = token_usage.get('prompt_tokens', 0)
            output_tokens = token_usage.get('completion_tokens', 0)
            total_tokens = token_usage.get('total_tokens', 0)
            
            debug_info = {
                'tool': serialized.get('name', 'Unknown Tool'),
                'input': input_str,
                'token_usage': {
                    'input_tokens': input_tokens,
                    'output_tokens': output_tokens,
                    'total_tokens': total_tokens
                },
                'serialized': serialized,
                'kwargs': kwargs
            }
            debug_abbreviated = {
                'tool': serialized.get('name', 'Unknown Tool'),
                'input': input_str,
                'token_usage': {
                    'input_tokens': input_tokens,
                    'output_tokens': output_tokens,
                    'total_tokens': total_tokens
                }
            }
            self._log_message("TOOL START EVENT RECEIVED", debug_abbreviated)
            
            message = {
                    'type': 'tool_start',
                    'message': {
                    'name': serialized.get('name', 'Unknown Tool'),
                    'input': input_str,
                    'timestamp': datetime.now().isoformat(),
                    'token_usage': {
                        'input_tokens': input_tokens,
                        'output_tokens': output_tokens,
                        'total_tokens': total_tokens
                    }
                }
            }
            await self._send_message(message)
        except Exception as e:
            self.logger.error(create_box("ERROR IN TOOL START", str(e)), exc_info=True)

    async def on_tool_end(self, output: str, **kwargs: Any):
        """Handle tool completion - send formatted output."""
        try:
            # Get token usage from kwargs if available
            token_usage = kwargs.get('token_usage', {})
            input_tokens = token_usage.get('prompt_tokens', 0)
            output_tokens = token_usage.get('completion_tokens', 0)
            total_tokens = token_usage.get('total_tokens', 0)
            
            # Format the output using OutputFormatter
            formatted_output = OutputFormatter.format_response({'output': output})
            
            debug_info = {
                'output': formatted_output,
                'token_usage': {
                    'input_tokens': input_tokens,
                    'output_tokens': output_tokens,
                    'total_tokens': total_tokens
                },
                'kwargs': kwargs
            }
            self._log_message("TOOL END EVENT RECEIVED", debug_info)
            
            message = {
                'type': 'tool_end',
                'message': {
                    'output': formatted_output,
                    'timestamp': datetime.now().isoformat(),
                    'token_usage': {
                        'input_tokens': input_tokens,
                        'output_tokens': output_tokens,
                        'total_tokens': total_tokens
                    }
                }
            }
            await self._send_message(message)
        except Exception as e:
            self.logger.error(create_box("ERROR IN TOOL END", str(e)), exc_info=True)

    async def on_agent_finish(self, finish: AgentFinish, **kwargs: Any):
        """Handle agent completion - send final answer and save to database."""
        try:
            # Get token usage from kwargs if available
            token_usage = kwargs.get('token_usage', {})
            input_tokens = token_usage.get('prompt_tokens', 0)
            output_tokens = token_usage.get('completion_tokens', 0)
            total_tokens = token_usage.get('total_tokens', 0)
            
            if hasattr(finish, 'return_values'):
                output = finish.return_values.get('output', '')
                
                # Check if this is a duplicate message
                if self._last_agent_finish == output:
                    self.logger.debug("Skipping duplicate agent finish message")
                    return
                
                self._last_agent_finish = output
                
                debug_info = {
                    'output': output,
                    'token_usage': {
                        'input_tokens': input_tokens,
                        'output_tokens': output_tokens,
                        'total_tokens': total_tokens
                    },
                    'kwargs': kwargs
                }
                self._log_message("AGENT FINISH EVENT RECEIVED", debug_info)
                
                message = {
                    'type': 'agent_finish',
                    'message': output,
                    'timestamp': datetime.now().isoformat(),
                    'token_usage': {
                        'input_tokens': input_tokens,
                        'output_tokens': output_tokens,
                        'total_tokens': total_tokens
                    }
                }
                
                # Save message to database
                await self._save_message_to_db(content=output, is_agent=True)
                
                # Send message to websocket
                await self._send_message(message)
        except Exception as e:
            self.logger.error(create_box("ERROR IN AGENT FINISH", str(e)), exc_info=True)