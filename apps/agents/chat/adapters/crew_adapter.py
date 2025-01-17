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