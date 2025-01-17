import logging
from typing import Optional, Dict, Any, List
from apps.agents.websockets.services.chat_service import ChatService
from apps.agents.models import Crew, CrewExecution
from apps.seo_manager.models import Client
from apps.agents.tasks.core.crew import initialize_crew, run_crew
from apps.common.utils import create_box, get_llm
from langchain_core.messages import SystemMessage, AIMessage
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from langchain.memory import ConversationBufferMemory
from apps.agents.tasks.callbacks.execution import StepCallback, TaskCallback

logger = logging.getLogger(__name__)

class CrewChatService(ChatService):
    """Chat service that uses CrewAI instead of single agent"""
    
    def __init__(self, crew, model_name, client_data, callback_handler, session_id=None):
        # Initialize with None as agent since we're using crew
        super().__init__(None, model_name, client_data, callback_handler, session_id)
        self.crew = crew
        self.crew_executor = None
        self.execution = None
        self.waiting_for_human_input = False
        self.human_input_request = None

    async def initialize(self) -> None:
        """Initialize with crew instead of agent"""
        try:
            logger.info(f"Initializing CrewChatService for crew: {self.crew.name}")
            
            # Get client if present
            client = None
            client_data = {}
            if self.client_data and self.client_data.get('client_id'):
                client = await database_sync_to_async(Client.objects.get)(id=self.client_data['client_id'])
                logger.debug(f"Retrieved client: {client.name if client else None}")
                if client:
                    client_data = {
                        'client_id': str(client.id),
                        'client_name': client.name,
                        'client_website_url': client.website_url,
                        'client_business_objectives': client.business_objectives,
                        'client_target_audience': client.target_audience,
                        'client_profile': client.client_profile
                    }

            # Create or get conversation
            conversation = await self._create_or_get_conversation(client)
            logger.debug(f"Created/retrieved conversation with ID: {conversation.id}")
            
            # Update managers with conversation ID
            self.conversation_id = str(conversation.id)
            self.token_manager.conversation_id = self.conversation_id
            self.message_manager.conversation_id = self.conversation_id

            # Create a CrewExecution object
            self.execution = await database_sync_to_async(CrewExecution.objects.create)(
                crew=self.crew,
                status='CHAT_MODE',
                client=client,
                inputs={
                    'session_id': self.session_id,
                    'client_data': client_data
                }
            )
            logger.info(f"Created CrewExecution with ID: {self.execution.id}")
            
            # Initialize crew executor
            logger.debug("Initializing crew executor...")
            self.crew_executor = await database_sync_to_async(initialize_crew)(self.execution)
            if not self.crew_executor:
                raise ValueError("Failed to initialize crew")
            logger.info("Successfully initialized crew executor")

            # Send initial message
            await self.callback_handler._send_message({
                'type': 'crew_start',
                'message': f'Initializing chat session with crew: {self.crew.name}',
                'metadata': {
                    'agent': 'System',
                    'status': 'running',
                    'crew_name': self.crew.name
                }
            })
            
            # Get LLM with token tracking
            self.llm, token_callback = get_llm(
                model_name=self.model_name,
                temperature=0.7,
            )
            
            # Set up token tracking
            self.llm.callbacks = [token_callback]
            logger.debug(f"Setting up token tracking with callback: {token_callback}")
            self.token_manager.set_token_callback(token_callback)

            # Initialize memory with proper message handling
            memory = ConversationBufferMemory(
                memory_key="chat_history",
                return_messages=True,
                chat_memory=self.message_manager,
                output_key="output",
                input_key="input"
            )

            # Load initial messages into memory and get chat history
            chat_history = await self.message_manager.get_messages()
            if chat_history:
                memory.chat_memory.messages.extend(chat_history)
            
            logger.info("CrewChatService initialization completed successfully")
            
        except Exception as e:
            logger.error(f"Error initializing crew chat service: {str(e)}", exc_info=True)
            raise

    async def process_message(self, message: str) -> None:
        """Process message through crew"""
        async with self.processing_lock:
            try:
                logger.info(f"Processing message for crew {self.crew.name}")
                
                # Check if this is a response to a human input request
                if self.waiting_for_human_input and self.human_input_request:
                    logger.info("Processing human input response")
                    # Update execution with human input
                    self.execution.human_input = message
                    await database_sync_to_async(self.execution.save)()
                    
                    # Reset human input state
                    self.waiting_for_human_input = False
                    self.human_input_request = None
                    
                    # Continue execution
                    result = await database_sync_to_async(run_crew)(
                        None,
                        self.crew_executor,
                        self.execution
                    )
                    
                    if result:
                        await self._handle_response(str(result))
                    return
                
                # Reset token tracking
                self.token_manager.reset_tracking()
                
                # Get chat history
                chat_history = await self.message_manager.get_messages()
                
                # Get client data
                client_data = {}
                if self.execution.client:
                    client = self.execution.client
                    client_data = {
                        'client_id': str(client.id),
                        'client_name': client.name,
                        'client_website_url': client.website_url,
                        'client_business_objectives': client.business_objectives,
                        'client_target_audience': client.target_audience,
                        'client_profile': client.client_profile
                    }
                
                # Update execution inputs
                self.execution.inputs.update({
                    'message': message,
                    'chat_history': [
                        {
                            'role': 'human' if msg.type == 'human' else 'assistant',
                            'content': msg.content
                        } for msg in chat_history
                    ],
                    'client_data': client_data
                })
                await database_sync_to_async(self.execution.save)()
                
                # Run crew
                logger.info(f"Running crew for execution {self.execution.id}")
                result = await database_sync_to_async(run_crew)(
                    None,  # task_id is None for chat
                    self.crew_executor,
                    self.execution
                )
                
                # Handle final response
                if result:
                    await self._handle_response(str(result))
                    
            except Exception as e:
                logger.error(f"Error in crew process_message: {str(e)}", exc_info=True)
                await self._handle_error(str(e), e, unexpected=True)

    async def crew_message(self, event):
        """Handle crew messages from log_crew_message"""
        try:
            logger.debug(f"Received crew message: {event}")
            
            # Check for human input request
            if event.get('human_input_request'):
                self.waiting_for_human_input = True
                self.human_input_request = event['human_input_request']
                
                # Send special message for human input request
                await self.callback_handler._send_message({
                    'type': 'human_input_request',
                    'message': event['message'],
                    'metadata': {
                        'agent': event.get('metadata', {}).get('agent', 'System'),
                        'status': 'waiting',
                        'message_type': 'human_input'
                    }
                })
                return
            
            # Store intermediate messages
            if event.get('message'):
                await self.message_manager.add_message(
                    AIMessage(content=event['message']),
                    token_usage=self.token_manager.get_current_usage()
                )
            
            # Forward to client
            await self.callback_handler._send_message(event)
            
        except Exception as e:
            logger.error(f"Error handling crew message: {str(e)}", exc_info=True) 