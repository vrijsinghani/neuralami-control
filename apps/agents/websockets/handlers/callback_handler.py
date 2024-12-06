from langchain_core.callbacks import BaseCallbackHandler
import logging
import time
import json
from typing import Any, Dict, List
from datetime import datetime

class WebSocketCallbackHandler(BaseCallbackHandler):
    """Enhanced callback handler with timing and comprehensive event tracking"""
    
    def __init__(self, consumer):
        self.consumer = consumer
        self.logger = logging.getLogger(__name__)
        self._last_time = None
        self._records = []
        self._current_chain_id = None
        self._current_tool_id = None

    def _record_timing(self) -> float:
        """Record time delta between events"""
        time_now = time.time()
        time_delta = time_now - self._last_time if self._last_time is not None else 0
        self._last_time = time_now
        return time_delta

    async def _append_record(self, event_type: str, content: Any, metadata: Dict = None):
        """Record an event with timing and metadata"""
        time_delta = self._record_timing()
        record = {
            "event_type": event_type,
            "content": content,
            "metadata": metadata or {},
            "time_delta": time_delta,
            "timestamp": datetime.now().isoformat(),
            "chain_id": self._current_chain_id,
            "tool_id": self._current_tool_id
        }
        self._records.append(record)
        return record

    async def _send_message(self, content: str, message_type: str = None, is_error: bool = False):
        """Send formatted message through websocket"""
        await self.consumer.message_handler.handle_message(
            content,
            is_agent=True,
            error=is_error,
            message_type=message_type
        )

    async def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any):
        """Handle LLM start event"""
        self.logger.debug("LLM Start callback triggered")
        record = await self._append_record("llm_start", {
            "serialized": serialized,
            "prompts": prompts,
            **kwargs
        })
        await self._send_message(
            "Processing your request...",
            message_type="llm_start"
        )

    async def on_llm_new_token(self, token: str, **kwargs: Any):
        """Handle streaming tokens"""
        self.logger.debug(f"New token received: {token[:50]}...")
        record = await self._append_record("llm_token", {
            "token": token,
            **kwargs
        })
        if token and token.strip():
            await self._send_message(
                token,
                message_type="llm_token",
                is_error=False
            )

    async def on_llm_end(self, response, **kwargs: Any):
        """Handle LLM completion"""
        self.logger.debug("LLM End callback triggered")
        record = await self._append_record("llm_end", {
            "response": response,
            **kwargs
        })
        try:
            output = response.generations[0][0].text if response.generations else ""
            if output.strip():
                await self._send_message(
                    output,
                    message_type="llm_end"
                )
        except Exception as e:
            self.logger.error(f"Error in on_llm_end: {str(e)}", exc_info=True)

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

    async def on_chain_start(self, serialized: Dict[str, Any], inputs: Dict[str, Any], **kwargs: Any):
        """Handle chain start"""
        self._current_chain_id = kwargs.get("run_id", None)
        record = await self._append_record("chain_start", {
            "serialized": serialized,
            "inputs": inputs,
            **kwargs
        })

    async def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any):
        """Handle chain completion"""
        record = await self._append_record("chain_end", {
            "outputs": outputs,
            **kwargs
        })
        self._current_chain_id = None

    async def on_chain_error(self, error: str, **kwargs: Any):
        """Handle chain errors"""
        self.logger.error(f"Chain error: {error}")
        record = await self._append_record("chain_error", {
            "error": error,
            **kwargs
        })
        await self._send_message(
            f"Error: {error}",
            message_type="chain_error",
            is_error=True
        )
        self._current_chain_id = None

    async def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any):
        """Handle tool start"""
        self._current_tool_id = kwargs.get("run_id", None)
        record = await self._append_record("tool_start", {
            "serialized": serialized,
            "input": input_str,
            **kwargs
        })
        await self._send_message(
            f"Using tool: {serialized.get('name', 'unknown')}\nInput: {input_str}",
            message_type="tool_start"
        )

    async def on_tool_end(self, output: str, **kwargs: Any):
        """Handle tool completion"""
        record = await self._append_record("tool_end", {
            "output": output,
            **kwargs
        })
        await self._send_message(
            output,
            message_type="tool_output"
        )
        self._current_tool_id = None

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
        self._current_tool_id = None

    async def on_text(self, text: str, **kwargs: Any):
        """Handle text events"""
        record = await self._append_record("text", {
            "text": text,
            **kwargs
        })
        await self._send_message(
            text,
            message_type="text"
        )

    async def on_agent_action(self, action, **kwargs: Any):
        """Handle agent actions"""
        record = await self._append_record("agent_action", {
            "action": action,
            **kwargs
        })
        await self._send_message(
            f"Agent action: {action.tool}\nInput: {action.tool_input}",
            message_type="agent_action"
        )

    async def on_agent_finish(self, finish, **kwargs: Any):
        """Handle agent completion"""
        record = await self._append_record("agent_finish", {
            "finish": finish,
            **kwargs
        })
        if hasattr(finish, 'return_values'):
            await self._send_message(
                str(finish.return_values.get('output', '')),
                message_type="agent_finish"
            )

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