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

    async def _send_message(self, content: Any, message_type: str = None, is_error: bool = False):
        """Send formatted message through websocket"""
        try:
            # Format content based on type
            if isinstance(content, dict):
                if 'message_type' in content:
                    # Handle tool messages
                    message_type = content['message_type']
                    formatted_content = content['message']
                elif 'actions' in content:
                    # Handle ReAct agent actions
                    action = content['actions'][0]
                    formatted_content = {
                        'action': action.tool,
                        'action_input': action.tool_input,
                        'log': action.log
                    }
                elif 'steps' in content:
                    # Handle ReAct agent steps
                    step = content['steps'][0]
                    if hasattr(step, 'observation') and step.observation:
                        # If it's a valid observation, send it directly
                        formatted_content = step.observation
                    elif hasattr(step.action, 'tool') and step.action.tool == '_Exception':
                        # Handle error cases gracefully
                        self.logger.error(f"Agent step error: {step.action.tool_input}")
                        formatted_content = {
                            'error': True,
                            'message': step.action.tool_input
                        }
                    else:
                        # Format other step information
                        formatted_content = {
                            'action': step.action.tool if hasattr(step.action, 'tool') else None,
                            'action_input': step.action.tool_input if hasattr(step.action, 'tool_input') else None,
                            'observation': step.observation if hasattr(step, 'observation') else None
                        }
                else:
                    formatted_content = content
            else:
                formatted_content = content

            await self.consumer.message_handler.handle_message(
                formatted_content,
                is_agent=True,
                error=is_error,
                message_type=message_type
            )
        except Exception as e:
            self.logger.error(f"Error in _send_message: {str(e)}")
            await self.consumer.message_handler.handle_message(
                str(content),
                is_agent=True,
                error=True,
                message_type='error'
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
        self.logger.debug(f"New token received: {type(token)}")
        
        # Skip empty tokens
        if token is None:
            return

        try:
            # Handle AgentAction and AgentFinish directly
            if isinstance(token, AgentAction):
                await self._send_message({
                    'type': 'AgentAction',
                    'tool': token.tool,
                    'tool_input': token.tool_input,
                    'log': token.log
                }, message_type="tool")
                return

            if isinstance(token, AgentFinish):
                await self._send_message({
                    'type': 'AgentFinish',
                    'return_values': token.return_values,
                    'log': token.log
                }, message_type="tool")
                return

            # Handle dictionary tokens
            if isinstance(token, dict):
                if 'agent_outcome' in token:
                    agent_outcome = token['agent_outcome']
                    if isinstance(agent_outcome, AgentAction):
                        await self._send_message({
                            'type': 'AgentAction',
                            'tool': agent_outcome.tool,
                            'tool_input': agent_outcome.tool_input,
                            'log': agent_outcome.log
                        }, message_type="tool")
                        return
                    elif isinstance(agent_outcome, AgentFinish):
                        await self._send_message({
                            'type': 'AgentFinish',
                            'return_values': agent_outcome.return_values,
                            'log': agent_outcome.log
                        }, message_type="tool")
                        return

                # Handle other dictionary tokens
                await self._send_message(token, message_type="llm_token")
                return

            # Handle string tokens
            if isinstance(token, str):
                if not token.strip():
                    return
                await self._send_message(token, message_type="llm_token")
                return
                
            # Handle any other type by converting to string
            await self._send_message(str(token), message_type="llm_token")

        except Exception as e:
            self.logger.error(f"Error processing token: {str(e)}", exc_info=True)
            await self._send_message(str(token), message_type="llm_token")

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
        if output and str(output).strip():
            # Try to parse JSON output
            try:
                if isinstance(output, str) and (output.startswith('{') or output.startswith('[')):
                    parsed_output = json.loads(output)
                    await self._send_message(parsed_output, message_type="tool_output")
                else:
                    await self._send_message(output, message_type="tool_output")
            except json.JSONDecodeError:
                await self._send_message(output, message_type="tool_output")
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