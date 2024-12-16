from langchain_core.callbacks import BaseCallbackHandler
import logging
import time
import json
from typing import Any, Dict, List
from datetime import datetime
from langchain_core.agents import AgentAction, AgentFinish

class WebSocketCallbackHandler(BaseCallbackHandler):
    """Enhanced callback handler with timing and comprehensive event tracking"""
    
    def __init__(self, consumer):
        """Initialize the handler with a WebSocket consumer"""
        self.consumer = consumer
        self.logger = logging.getLogger(__name__)
        self._records = []
        self._current_tool_id = None

    async def _append_record(self, event_type: str, data: Dict) -> Dict:
        """Append a record to the history"""
        record = {
            "event": event_type,
            "timestamp": datetime.now().isoformat(),
            "data": data
        }
        self._records.append(record)
        return record

    async def _send_message(self, message, message_type="agent_message", is_error=False):
        """Send a message through the WebSocket"""
        try:
            # Skip null or empty messages
            if message is None:
                return
                
            # Skip empty strings
            if isinstance(message, str) and not message.strip():
                return

            await self.consumer.send_json({
                "type": message_type,
                "message": message,
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            self.logger.error(f"Error sending message: {str(e)}")

    async def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any):
        """Handle LLM start"""
        record = await self._append_record("llm_start", {
            "prompts": prompts,
            **kwargs
        })

    async def on_llm_new_token(self, token: str, **kwargs: Any):
        """Handle new tokens from LLM"""
        try:
            # Handle AgentAction and AgentFinish directly
            if isinstance(token, AgentAction):
                await self._send_message({
                    'message_type': 'tool',
                    'message': {
                        'type': 'AgentAction',
                        'tool': token.tool,
                        'tool_input': token.tool_input,
                        'log': token.log
                    }
                })
                return

            if isinstance(token, AgentFinish):
                await self._send_message({
                    'message_type': 'tool',
                    'message': {
                        'type': 'AgentFinish',
                        'return_values': token.return_values,
                        'log': token.log
                    }
                })
                return

            # Handle structured tool messages
            if isinstance(token, dict) and 'message_type' in token:
                if token['message_type'] == 'tool':
                    await self._send_message(token)
                    return

            # Handle regular text tokens
            if token and isinstance(token, str):
                await self._send_message(token)

        except Exception as e:
            self.logger.error(f"Error in on_llm_new_token: {str(e)}", exc_info=True)

    async def on_llm_end(self, response, **kwargs: Any):
        """Handle LLM completion"""
        record = await self._append_record("llm_end", {
            "response": response,
            **kwargs
        })

    async def on_llm_error(self, error: str, **kwargs: Any):
        """Handle LLM errors"""
        self.logger.error(f"LLM Error: {error}")
        record = await self._append_record("llm_error", {
            "error": error,
            **kwargs
        })
        await self._send_message(
            f"Error: {error}",
            message_type="llm_error",
            is_error=True
        )

    async def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any):
        """Handle tool start"""
        record = await self._append_record("tool_start", {
            "input": input_str,
            **kwargs
        })

    async def on_tool_end(self, output: str, **kwargs: Any):
        """Handle tool completion"""
        record = await self._append_record("tool_end", {
            "output": output,
            **kwargs
        })

    async def on_tool_error(self, error: str, **kwargs: Any):
        """Handle tool errors"""
        self.logger.error(f"Tool error: {error}")
        record = await self._append_record("tool_error", {
            "error": error,
            **kwargs
        })
        await self._send_message(
            f"Tool error: {error}",
            message_type="tool_error",
            is_error=True
        )

    async def on_text(self, text: str, **kwargs: Any):
        """Handle text events"""
        record = await self._append_record("text", {
            "text": text,
            **kwargs
        })
        await self._send_message(text, message_type="text")

    async def on_agent_action(self, action, **kwargs: Any):
        """Handle agent actions"""
        record = await self._append_record("agent_action", {
            "action": action,
            **kwargs
        })
        await self._send_message({
            'message_type': 'tool',
            'message': {
                'type': 'AgentAction',
                'tool': action.tool,
                'tool_input': action.tool_input,
                'log': action.log if hasattr(action, 'log') else None
            }
        })

    async def on_agent_finish(self, finish, **kwargs: Any):
        """Handle agent completion"""
        record = await self._append_record("agent_finish", {
            "finish": finish,
            **kwargs
        })
        await self._send_message({
            'message_type': 'tool',
            'message': {
                'type': 'AgentFinish',
                'return_values': finish.return_values,
                'log': finish.log if hasattr(finish, 'log') else None
            }
        })

    def get_records(self) -> List[Dict]:
        """Get all recorded events"""
        return self._records

    async def save_records(self, session_id: str):
        """Save records to Django cache"""
        try:
            from django.core.cache import cache
            cache_key = f"callback_records_{session_id}"
            cache.set(cache_key, self._records, timeout=3600)  # 1 hour timeout
        except Exception as e:
            self.logger.error(f"Error saving callback records: {str(e)}", exc_info=True)