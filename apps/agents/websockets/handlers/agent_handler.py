import logging
from apps.common.utils import create_box
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

            # Check if we need to reinitialize the chat service (agent or model changed)
            should_reinitialize = (
                not self.chat_service or
                str(self.chat_service.agent.id) != str(agent_id) or
                self.chat_service.model_name != model_name
            )

            if should_reinitialize:
                # Create new chat service with new agent/model but preserve message manager
                logger.info(create_box("AGENT HANDLER", f"Reinitializing chat service for agent {agent_id} with model {model_name}"))
                callback_handler = WebSocketCallbackHandler(self.consumer)
                
                # Preserve the existing message manager if it exists
                message_manager = self.chat_service.message_manager if self.chat_service else None
                
                self.chat_service = ChatService(
                    agent=agent,
                    model_name=model_name,
                    client_data=client_data,
                    callback_handler=callback_handler,
                    session_id=self.consumer.session_id
                )
                
                # Set the preserved message manager if it exists
                if message_manager:
                    self.chat_service.message_manager = message_manager
                    
                await self.chat_service.initialize()
            else:
                # Just update client data if it changed
                self.chat_service.client_data = client_data

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