import logging
from apps.common.utils import format_message
from apps.agents.models import Agent

logger = logging.getLogger(__name__)

class AgentHandler:
    def __init__(self, consumer):
        self.consumer = consumer
        self.chat_service = None

    async def process_response(self, message, agent_id, model_name, client_id):
        """Process and send agent response"""
        try:
            # Get agent data
            agent = await self.get_agent(agent_id)
            if not agent:
                raise ValueError("Agent not found")

            # Get client data
            client_data = await self.consumer.client_manager.get_client_data(client_id)

            # Initialize chat service if needed
            if not self.chat_service:
                from ..services.chat_service import ChatService
                from ..handlers.callback_handler import WebSocketCallbackHandler
                
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

            # Process message
            response = await self.chat_service.process_message(message)
            return response

        except Exception as e:
            logger.error(f"Error in agent handler: {str(e)}")
            raise

    async def get_agent(self, agent_id):
        """Get agent from database"""
        try:
            from django.db import models
            from channels.db import database_sync_to_async

            @database_sync_to_async
            def get_agent_from_db(agent_id):
                return Agent.objects.get(id=agent_id)

            return await get_agent_from_db(agent_id)
        except Exception as e:
            logger.error(f"Error getting agent: {str(e)}")
            raise 

    async def process_message(self, message: str, is_edit: bool = False) -> str:
        """Process a message using the agent"""
        try:
            # Get agent and model info
            agent_id = self.consumer.scope.get('agent_id')
            model_name = self.consumer.scope.get('model_name')
            client_id = self.consumer.scope.get('client_id')

            # Initialize chat service
            chat_service = ChatService(
                agent=await self.get_agent(agent_id),
                model_name=model_name,
                client_data=await self.get_client_data(client_id),
                callback_handler=self.callback_handler,
                session_id=self.consumer.session_id
            )

            await chat_service.initialize()
            
            # Process message with edit flag
            return await chat_service.process_message(message, is_edit=is_edit)

        except Exception as e:
            error_msg = f"Error in agent handler: {str(e)}"
            logger.error(error_msg)
            raise