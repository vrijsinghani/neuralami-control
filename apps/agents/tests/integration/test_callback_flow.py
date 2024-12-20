import pytest
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from apps.agents.websockets.chat_consumer import ChatConsumer
from apps.agents.models import Conversation, ChatMessage
from apps.agents.websockets.handlers.callback_handler import WebSocketCallbackHandler
from langchain_core.agents import AgentFinish

User = get_user_model()

@pytest.mark.django_db
@pytest.mark.asyncio
class TestCallbackFlow:
    async def test_full_callback_flow(self):
        # Create test user and conversation
        user = await User.objects.acreate(
            username='test_user',
            email='test@example.com'
        )
        
        conversation = await Conversation.objects.acreate(
            session_id='test_session',
            user=user,
            title='Test Conversation'
        )
        
        # Create WebSocket communicator
        communicator = WebsocketCommunicator(
            ChatConsumer.as_asgi(),
            f"/ws/chat/?session=test_session"
        )
        communicator.scope["user"] = user
        connected, _ = await communicator.connect()
        assert connected
        
        try:
            # Create callback handler
            handler = WebSocketCallbackHandler(communicator)
            
            # Test tool start
            await handler.on_tool_start(
                serialized={'name': 'test_tool'},
                input_str='test input'
            )
            response = await communicator.receive_json_from()
            assert response['type'] == 'tool_start'
            
            # Test tool end
            await handler.on_tool_end('test output')
            response = await communicator.receive_json_from()
            assert response['type'] == 'tool_end'
            
            # Test agent finish
            finish = AgentFinish(
                return_values={'output': 'test final output'},
                log='test log'
            )
            await handler.on_agent_finish(finish)
            response = await communicator.receive_json_from()
            assert response['type'] == 'agent_finish'
            
            # Verify database state
            messages = await ChatMessage.objects.filter(
                session_id='test_session'
            ).acount()
            assert messages == 1  # One message from agent_finish
            
        finally:
            await communicator.disconnect()

    async def test_error_handling(self):
        # Create test user
        user = await User.objects.acreate(
            username='test_user',
            email='test@example.com'
        )
        
        # Create WebSocket communicator
        communicator = WebsocketCommunicator(
            ChatConsumer.as_asgi(),
            f"/ws/chat/?session=invalid_session"
        )
        communicator.scope["user"] = user
        connected, _ = await communicator.connect()
        assert connected
        
        try:
            handler = WebSocketCallbackHandler(communicator)
            
            # Test handling of invalid tool
            await handler.on_tool_start(
                serialized={'name': 'invalid_tool'},
                input_str='test input'
            )
            response = await communicator.receive_json_from()
            assert response['type'] == 'tool_start'
            
            # Test handling of invalid output
            await handler.on_tool_end(None)
            response = await communicator.receive_json_from()
            assert response['type'] == 'tool_end'
            
        finally:
            await communicator.disconnect()

    async def test_concurrent_callbacks(self):
        # Create test user and conversation
        user = await User.objects.acreate(
            username='test_user',
            email='test@example.com'
        )
        
        conversation = await Conversation.objects.acreate(
            session_id='test_session',
            user=user,
            title='Test Conversation'
        )
        
        # Create WebSocket communicator
        communicator = WebsocketCommunicator(
            ChatConsumer.as_asgi(),
            f"/ws/chat/?session=test_session"
        )
        communicator.scope["user"] = user
        connected, _ = await communicator.connect()
        assert connected
        
        try:
            handler = WebSocketCallbackHandler(communicator)
            
            # Send multiple tool starts concurrently
            import asyncio
            tasks = []
            for i in range(5):
                tasks.append(
                    handler.on_tool_start(
                        serialized={'name': f'tool_{i}'},
                        input_str=f'input_{i}'
                    )
                )
            await asyncio.gather(*tasks)
            
            # Verify all messages were received in order
            for i in range(5):
                response = await communicator.receive_json_from()
                assert response['type'] == 'tool_start'
                assert f'tool_{i}' in str(response['message'])
                
        finally:
            await communicator.disconnect() 