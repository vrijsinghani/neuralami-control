import logging
from apps.common.utils import format_message
from apps.agents.models import Agent
from channels.db import database_sync_to_async
from apps.agents.websockets.handlers.callback_handler import WebSocketCallbackHandler
from apps.agents.websockets.services.chat_service import ChatService

logger = logging.getLogger(__name__)

class AgentHandler:
    def __init__(self, consumer):
        self.consumer = consumer
        self.chat_service = None

    async def process_response(self, message, agent_id, model_name, client_id):
        """Manages agent and chat service lifecycle"""
        try:
            # Get agent data
            agent = await self.get_agent(agent_id)
            if not agent:
                raise ValueError("Agent not found")

            # Get client data
            client_data = await self.consumer.client_manager.get_client_data(client_id)

            # Initialize or reset chat service
            if not self.chat_service:
                callback_handler = WebSocketCallbackHandler(self.consumer)
                self.chat_service = ChatService(
                    agent=agent,
                    model_name=model_name,
                    client_data=client_data,
                    callback_handler=callback_handler,
                    session_id=self.consumer.session_id
                )
                await self.chat_service.initialize()
            else:
                # Reset token counter if service exists
                if hasattr(self.chat_service, 'token_counter'):
                    self.chat_service.token_counter.input_tokens = 0
                    self.chat_service.token_counter.output_tokens = 0

            # Process message - no return value needed as everything goes through callbacks
            await self.chat_service.process_message(message)

        except Exception as e:
            logger.error(f"Error in agent handler: {str(e)}")
            raise

    @database_sync_to_async
    def get_agent(self, agent_id):
        """Get agent from database"""
        try:
            return Agent.objects.get(id=agent_id)
        except Exception as e:
            logger.error(f"Error getting agent: {str(e)}")
            raise