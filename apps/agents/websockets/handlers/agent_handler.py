import logging
from apps.common.utils import create_box
from apps.agents.models import Agent
from channels.db import database_sync_to_async
from apps.agents.websockets.handlers.callback_handler import WebSocketCallbackHandler
from apps.agents.websockets.services.chat_service import ChatService
from apps.agents.chat.services.crew_chat_service import CrewChatService

logger = logging.getLogger(__name__)

class AgentHandler:
    def __init__(self, consumer):
        self.consumer = consumer
        self.chat_service = None
        
    async def process_response(self, message, agent_id, model_name, client_id, crew_id=None):
        """Manages agent/crew and chat service lifecycle"""
        try:
            if crew_id:
                # Handle crew-based chat
                crew = await self.get_crew(crew_id)
                if not crew:
                    raise ValueError("Crew not found")
                    
                # Get client data
                client_data = await self.consumer.client_manager.get_client_data(client_id)
                
                # Check if we need to reinitialize the chat service
                should_reinitialize = (
                    not self.chat_service or
                    not isinstance(self.chat_service, CrewChatService) or
                    str(self.chat_service.crew.id) != str(crew_id) or
                    self.chat_service.model_name != model_name
                )
                
                if should_reinitialize:
                    # Create new crew chat service
                    logger.info(create_box("AGENT HANDLER", f"Initializing crew chat service for crew {crew_id} with model {model_name}"))
                    callback_handler = WebSocketCallbackHandler(self.consumer)
                    
                    # Preserve existing conversation ID and message history if it exists
                    conversation_id = self.chat_service.conversation_id if self.chat_service else None
                    message_manager = self.chat_service.message_manager if self.chat_service else None
                    
                    self.chat_service = CrewChatService(
                        crew=crew,
                        model_name=model_name,
                        client_data=client_data,
                        callback_handler=callback_handler,
                        session_id=self.consumer.session_id
                    )
                    
                    # Set preserved data if it exists
                    if conversation_id:
                        self.chat_service.conversation_id = conversation_id
                    if message_manager:
                        self.chat_service.message_manager = message_manager
                        
                    await self.chat_service.initialize()
                else:
                    # Just update client data if it changed
                    self.chat_service.client_data = client_data
                    
            else:
                # Handle agent-based chat (existing code)
                agent = await self.get_agent(agent_id)
                if not agent:
                    raise ValueError("Agent not found")
                    
                client_data = await self.consumer.client_manager.get_client_data(client_id)
                
                should_reinitialize = (
                    not self.chat_service or
                    not isinstance(self.chat_service, ChatService) or
                    str(self.chat_service.agent.id) != str(agent_id) or
                    self.chat_service.model_name != model_name
                )
                
                if should_reinitialize:
                    logger.info(create_box("AGENT HANDLER", f"Reinitializing chat service for agent {agent_id} with model {model_name}"))
                    callback_handler = WebSocketCallbackHandler(self.consumer)
                    
                    conversation_id = self.chat_service.conversation_id if self.chat_service else None
                    message_manager = self.chat_service.message_manager if self.chat_service else None
                    
                    self.chat_service = ChatService(
                        agent=agent,
                        model_name=model_name,
                        client_data=client_data,
                        callback_handler=callback_handler,
                        session_id=self.consumer.session_id
                    )
                    
                    if conversation_id:
                        self.chat_service.conversation_id = conversation_id
                    if message_manager:
                        self.chat_service.message_manager = message_manager
                        
                    await self.chat_service.initialize()
                else:
                    self.chat_service.client_data = client_data
            
            # Process message - no return value needed as everything goes through callbacks
            await self.chat_service.process_message(message)
            
        except Exception as e:
            logger.error(f"Error in agent handler: {str(e)}")
            raise
            
    async def get_crew(self, crew_id):
        """Get crew by ID"""
        try:
            from apps.agents.models import Crew
            return await Crew.objects.filter(id=crew_id).afirst()
        except Exception as e:
            logger.error(f"Error getting crew: {str(e)}")
            return None
            
    async def get_agent(self, agent_id):
        """Get agent by ID"""
        try:
            from apps.agents.models import Agent
            return await Agent.objects.filter(id=agent_id).afirst()
        except Exception as e:
            logger.error(f"Error getting agent: {str(e)}")
            return None