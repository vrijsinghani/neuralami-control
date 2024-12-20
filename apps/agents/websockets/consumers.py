import json
from django.db import models
from django.db.models import Q
from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from apps.agents.models import Agent
from apps.agents.services import ChatService

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        session_id = self.scope['url_route']['kwargs']['session_id']
        agent_id = self.scope['url_route']['kwargs'].get('agent_id')
        
        # Get the agent from the database
        agent = await database_sync_to_async(Agent.objects.get)(id=agent_id)
        
        # Initialize chat service with the specified agent
        self.chat_service = ChatService(
            agent=agent,
            model_name=self.model_name,
            client_data=self.client_data,
            callback_handler=self,
            session_id=session_id
        )
        
        await self.chat_service.initialize()
        await self.accept()

    async def receive(self, text_data):
        data = json.loads(text_data)
        if data.get('type') == 'agent_change':
            # Handle agent change
            new_agent = await database_sync_to_async(Agent.objects.get)(id=data['agent_id'])
            self.chat_service.update_agent(new_agent)
            return
            
        # ... rest of receive code ... 