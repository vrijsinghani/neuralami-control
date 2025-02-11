from apps.common.websockets.base_consumer import BaseWebSocketConsumer
from channels.db import database_sync_to_async
from ..models import Research
import logging

logger = logging.getLogger(__name__)

class ResearchConsumer(BaseWebSocketConsumer):
    async def connect(self):
        self.research_id = self.scope['url_route']['kwargs']['research_id']
        self.group_name = f"research_{self.research_id}"
        logger.info(f"WebSocket connecting for research {self.research_id}")
        await super().connect()
        logger.info(f"WebSocket connected for research {self.research_id}")

    def get_group_name(self):
        return self.group_name

    @database_sync_to_async
    def get_research(self):
        try:
            return Research.objects.get(id=self.research_id)
        except Research.DoesNotExist:
            logger.error(f"Research {self.research_id} not found")
            return None

    async def handle_message(self, data):
        message_type = data.get('type')
        #logger.info(f"Received message type {message_type} for research {self.research_id}")
        
        if message_type == 'get_status':
            research = await self.get_research()
            if research:
                await self.send_json({
                    'type': 'research_status',
                    'status': research.status,
                    'visited_urls': research.visited_urls,
                    'learnings': research.learnings,
                    'report': research.report
                })
            else:
                await self.send_error('Research not found')

    async def research_update(self, event):
        """Handle research updates from Celery task"""
        #logger.info(f"Received research update for {self.research_id}: {event}")
        await self.send_json({
            'type': 'research_update',
            'data': event['data']
        }) 