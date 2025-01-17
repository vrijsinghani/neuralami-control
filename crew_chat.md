Here's the high-level approach for integrating crew-based chat:
Frontend Changes:
Add crew selection alongside/alternative to agent selection in chat interface
Modify message sending to include crew_id instead of agent_id when in crew mode
Keep existing WebSocket connection and message handling patterns
Add any crew-specific UI elements (e.g., showing crew execution status/progress)
Backend Changes:
New Components:
CrewChatAdapter: Bridge between chat system and crew execution
CrewChatService: Handle crew-based chat instead of agent-based chat
Keep existing crew.py untouched
Flow:
Frontend -> WebSocket -> ChatConsumer -> CrewChatService -> CrewChatAdapter -> crew.py
Key Integration Points:
Chat messages become crew inputs
Chat history provides context for crew execution
Crew responses flow back through existing WebSocket channels
Execution records track chat-based crew usage
Data Flow:
User sends message with crew_id
System initializes/reuses crew for chat session
Message + chat history become crew inputs
Crew executes and returns response
Response handled like agent responses
State Management:
Maintain conversation history
Track crew execution state
Preserve client/user context
Handle crew initialization/reuse
This approach allows crews to handle chat interactions while:
Preserving existing crew functionality
Maintaining backward compatibility
Using existing WebSocket infrastructure
Keeping clean separation of concerns
Here's a comprehensive list of files that need to be modified to implement crew-based chat:
New Files to Create:
apps/agents/chat/adapters/crew_adapter.py - Adapter between chat and crew systems
apps/agents/chat/services/crew_chat_service.py - Crew-specific chat service
Frontend Files to Modify:
apps/agents/templates/agents/chat.html
Add crew selection UI
Modify message form to handle crew selection
apps/agents/static/agents/js/chat/app.js
Add crew selection handling
Modify message sending logic
3. apps/agents/static/agents/js/services/websocket.js
Add crew-specific message types
Update message handling
Backend Files to Modify:
apps/agents/websockets/chat_consumer.py
Add crew message handling
Update connection initialization
apps/agents/websockets/handlers/agent_handler.py
Add crew handling capability
Modify process_response for crews
apps/agents/models.py
Add crew chat-related fields/metadata
Update conversation model if needed
apps/agents/websockets/services/chat_service.py
Add crew service integration
Update message processing
apps/agents/urls.py
Add any new crew chat endpoints
apps/agents/views_chat.py
Update context to include crews
Add crew-related view logic
core/routing.py
Update WebSocket routing if needed
This maintains the existing structure while adding crew chat capability.
This approach:
Keeps crew.py completely unchanged and backward compatible
Creates an adapter layer to bridge chat and crew functionality
Maintains proper execution records and context
Preserves all existing crew functionality
Allows crews to be used in chat context without modification
The key benefits are:
No changes to existing crew functionality
Clean separation of concerns
Proper handling of chat context
Maintains execution records
Preserves all existing patterns

example code:
# apps/agents/chat/adapters/crew_adapter.py

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from apps.agents.tasks.core.crew import initialize_crew, run_crew
from apps.agents.models import CrewExecution, Crew
from apps.common.utils import create_box

logger = logging.getLogger(__name__)

class CrewChatAdapter:
    """Adapter to use CrewAI in chat context while preserving original functionality"""
    
    def __init__(self, crew: Crew, execution_context: Dict[str, Any] = None):
        self.crew = crew
        self.crew_executor = None
        self.execution = None
        self.execution_context = execution_context or {}
        
    async def initialize(self) -> None:
        """Initialize crew for chat usage"""
        try:
            # Create a temporary execution record for this chat interaction
            self.execution = await self._create_chat_execution()
            
            # Initialize crew using existing functionality
            self.crew_executor = initialize_crew(self.execution)
            if not self.crew_executor:
                raise ValueError("Failed to initialize crew")
                
            logger.debug(create_box("Initialized crew for chat", f"Crew: {self.crew.name}"))
            
        except Exception as e:
            logger.error(f"Error initializing crew chat adapter: {str(e)}")
            raise

    async def process_message(self, message: str, chat_history: List[Dict] = None) -> str:
        """Process chat message through crew"""
        try:
            # Prepare inputs that crew.py expects
            inputs = self._prepare_crew_inputs(message, chat_history)
            
            # Run crew using existing functionality
            result = run_crew(
                task_id=None,  # No Celery task ID for chat
                crew=self.crew_executor,
                execution=self.execution,
                inputs=inputs
            )
            
            return str(result)
            
        except Exception as e:
            logger.error(f"Error processing message through crew: {str(e)}")
            raise

    async def _create_chat_execution(self) -> CrewExecution:
        """Create temporary execution record for chat"""
        try:
            execution = await CrewExecution.objects.acreate(
                crew=self.crew,
                status='CHAT_MODE',
                client_id=self.execution_context.get('client_id'),
                user_id=self.execution_context.get('user_id'),
                metadata={
                    'chat_session_id': self.execution_context.get('session_id'),
                    'is_chat_execution': True
                }
            )
            return execution
        except Exception as e:
            logger.error(f"Error creating chat execution: {str(e)}")
            raise

    def _prepare_crew_inputs(self, message: str, chat_history: List[Dict] = None) -> Dict:
        """Prepare inputs in format expected by crew.py"""
        inputs = {
            'message': message,
            'current_date': datetime.now().strftime("%Y-%m-%d"),
            'chat_context': {
                'message': message,
                'history': chat_history or [],
                'session_id': self.execution_context.get('session_id')
            }
        }
        
        # Add client context if available
        if self.execution_context.get('client_id'):
            inputs.update({
                'client_id': self.execution_context['client_id'],
                'client_name': self.execution_context.get('client_name'),
                'client_website_url': self.execution_context.get('client_website_url'),
                'client_business_objectives': self.execution_context.get('client_business_objectives'),
                'client_target_audience': self.execution_context.get('client_target_audience'),
                'client_profile': self.execution_context.get('client_profile')
            })
            
        return inputs

Then modify the ChatService to use this adapter:

# apps/agents/websockets/services/chat_service.py

class CrewChatService(ChatService):
    """Chat service that uses CrewAI instead of single agent"""
    
    def __init__(self, crew, model_name, client_data, callback_handler, session_id=None):
        super().__init__(None, model_name, client_data, callback_handler, session_id)
        self.crew = crew
        self.crew_adapter = None
        
    async def initialize(self) -> None:
        """Initialize with crew instead of agent"""
        try:
            # Create execution context
            execution_context = {
                'session_id': self.session_id,
                'client_id': self.client_data.get('client_id') if self.client_data else None,
                'user_id': self.client_data.get('user_id') if self.client_data else None,
                'client_name': self.client_data.get('client_name'),
                'client_website_url': self.client_data.get('client_website_url'),
                'client_business_objectives': self.client_data.get('client_business_objectives'),
                'client_target_audience': self.client_data.get('client_target_audience'),
                'client_profile': self.client_data.get('client_profile')
            }
            
            # Initialize crew adapter
            self.crew_adapter = CrewChatAdapter(
                crew=self.crew,
                execution_context=execution_context
            )
            await self.crew_adapter.initialize()
            
            # Initialize other components (message history, token tracking etc)
            await super()._initialize_components()
            
        except Exception as e:
            logger.error(f"Error initializing crew chat service: {str(e)}")
            raise

    async def process_message(self, message: str) -> None:
        """Process message through crew adapter"""
        async with self.processing_lock:
            try:
                # Reset token tracking
                self.token_manager.reset_tracking()
                
                # Get chat history
                chat_history = await self.message_manager.get_messages()
                
                # Convert chat history to format crew can use
                formatted_history = [
                    {
                        'role': 'human' if msg.type == 'human' else 'assistant',
                        'content': msg.content
                    } for msg in chat_history
                ]
                
                # Process through crew adapter
                result = await self.crew_adapter.process_message(
                    message=message,
                    chat_history=formatted_history
                )
                
                # Handle response
                if result:
                    await self._handle_response(result)
                    
            except Exception as e:
                logger.error(f"Error in crew process_message: {str(e)}")
                await self._handle_error(str(e), e, unexpected=True)