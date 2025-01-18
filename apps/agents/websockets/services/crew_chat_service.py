import uuid
from typing import Optional
from django.contrib.auth import get_user_model
from apps.agents.models import (
    Conversation,
    CrewChatSession,
    ChatMessage
)

User = get_user_model()

class CrewChatService:
    """Service for handling crew chat operations"""
    def __init__(self, user, conversation=None):
        self.user = user
        self.conversation = conversation
        self.websocket_handler = None
    
    async def initialize_chat(self, crew_execution):
        """Initialize a new crew chat session"""
        if not self.conversation:
            self.conversation = await Conversation.objects.acreate(
                session_id=uuid.uuid4(),
                user=self.user,
                participant_type='crew',
                crew_execution=crew_execution
            )
        
        await CrewChatSession.objects.acreate(
            conversation=self.conversation,
            crew_execution=crew_execution
        )
        
        return self.conversation
    
    async def handle_message(self, content: str):
        """Handle incoming chat message"""
        # Create chat message
        message = await ChatMessage.objects.acreate(
            conversation=self.conversation,
            content=content,
            user=self.user,
            is_agent=False
        )
        
        # Get crew chat session
        session = await self.conversation.crew_chat_session
        
        # Update crew execution with message
        crew_execution = self.conversation.crew_execution
        if crew_execution.status == 'WAITING_FOR_HUMAN_INPUT':
            crew_execution.human_input_response = {'message': content}
            await crew_execution.asave()
        
        return message
    
    async def send_crew_message(self, content: str, task_id: Optional[int] = None):
        """Send message from crew to chat"""
        message = await ChatMessage.objects.acreate(
            conversation=self.conversation,
            content=content,
            user=self.user,
            is_agent=True
        )
        
        if self.websocket_handler:
            await self.websocket_handler.send_message({
                'type': 'crew_message',
                'content': content,
                'task_id': task_id
            })
        
        return message
