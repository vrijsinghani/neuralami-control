import pytest
import asyncio
from unittest.mock import Mock, patch
from datetime import datetime
from langchain_core.agents import AgentFinish
from apps.agents.websockets.handlers.callback_handler import WebSocketCallbackHandler

@pytest.fixture
def mock_consumer():
    consumer = Mock()
    consumer.session_id = "test_session"
    consumer.send_json = Mock()
    return consumer

@pytest.fixture
def callback_handler(mock_consumer):
    return WebSocketCallbackHandler(consumer=mock_consumer)

@pytest.mark.asyncio
async def test_send_message(callback_handler, mock_consumer):
    test_message = {
        'type': 'test_message',
        'content': 'test content'
    }
    await callback_handler._send_message(test_message)
    mock_consumer.send_json.assert_called_once()

@pytest.mark.asyncio
async def test_tool_start(callback_handler, mock_consumer):
    serialized = {'name': 'test_tool'}
    input_str = 'test input'
    await callback_handler.on_tool_start(serialized, input_str)
    mock_consumer.send_json.assert_called_once()

@pytest.mark.asyncio
async def test_tool_end(callback_handler, mock_consumer):
    output = 'test output'
    await callback_handler.on_tool_end(output)
    mock_consumer.send_json.assert_called_once()

@pytest.mark.asyncio
async def test_agent_finish(callback_handler, mock_consumer):
    finish = AgentFinish(
        return_values={'output': 'test output'},
        log='test log'
    )
    await callback_handler.on_agent_finish(finish)
    mock_consumer.send_json.assert_called_once()

@pytest.mark.asyncio
async def test_duplicate_agent_finish_prevention(callback_handler, mock_consumer):
    finish = AgentFinish(
        return_values={'output': 'test output'},
        log='test log'
    )
    # First call should send message
    await callback_handler.on_agent_finish(finish)
    # Second call with same output should not send message
    await callback_handler.on_agent_finish(finish)
    assert mock_consumer.send_json.call_count == 1

@pytest.mark.asyncio
async def test_message_lock(callback_handler, mock_consumer):
    # Test that message lock prevents concurrent sends
    async def send_messages():
        messages = [{'type': f'msg_{i}'} for i in range(5)]
        await asyncio.gather(*[callback_handler._send_message(msg) for msg in messages])
    
    await send_messages()
    assert mock_consumer.send_json.call_count == 5 