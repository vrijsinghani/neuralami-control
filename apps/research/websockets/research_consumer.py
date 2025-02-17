from apps.common.websockets.base_consumer import BaseWebSocketConsumer
from channels.db import database_sync_to_async
from ..models import Research
import logging
import json

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

    @database_sync_to_async
    def update_research(self, data):
        try:
            research = Research.objects.get(id=self.research_id)
            logger.info(f"Updating research {self.research_id} with data type: {data.get('type')}")
            
            # Handle reasoning steps
            if data.get('type') == 'reasoning':
                step_data = {
                    'step_type': data.get('step'),
                    'title': data.get('title'),
                    'explanation': data.get('explanation'),
                    'details': data.get('details', {})
                }
                logger.info(f"Adding reasoning step: {step_data['title']}")
                
                # Append new step to reasoning_steps
                research.reasoning_steps = research.reasoning_steps + [step_data]
                research.save(update_fields=['reasoning_steps'])
                logger.info(f"Research now has {len(research.reasoning_steps)} reasoning steps")
                
            # Handle status updates
            elif data.get('type') == 'status':
                logger.info(f"Updating status to: {data.get('status')}")
                research.status = data.get('status')
                research.save(update_fields=['status'])
                
            # Handle error updates
            elif data.get('type') == 'error':
                logger.error(f"Research error: {data.get('message')}")
                research.error = data.get('message')
                research.status = 'failed'
                research.save(update_fields=['error', 'status'])
                
            return research
            
        except Research.DoesNotExist:
            logger.error(f"Research {self.research_id} not found")
            return None
        except Exception as e:
            logger.error(f"Error updating research: {str(e)}", exc_info=True)
            return None

    async def handle_message(self, data):
        message_type = data.get('type')
        
        if message_type == 'get_status':
            research = await self.get_research()
            if research:
                await self.send_json({
                    'type': 'research_status',
                    'status': research.status,
                    'visited_urls': research.visited_urls,
                    'learnings': research.learnings,
                    'reasoning_steps': research.reasoning_steps,
                    'report': research.report
                })
            else:
                await self.send_error('Research not found')

    async def research_update(self, event):
        """Handle research updates from Celery task"""
        data = event.get('data')
        if not data:
            logger.error(f"No data in research update event for research {self.research_id}")
            return
            
        logger.info(f"Received research update: {data.get('update_type')} for research {self.research_id}")
        
        # Update research object if needed
        update_type = data.get('update_type')
        if update_type in ['reasoning', 'status', 'error']:
            research = await self.update_research({
                'type': update_type,
                **{k: v for k, v in data.items() if k != 'update_type'}
            })
            if not research:
                logger.error("Failed to update research object")
                return
        
        try:
            # Send update to WebSocket
            await self.send_json({
                'type': 'research_update',
                'data': data
            })
            logger.info(f"Sent WebSocket update for {update_type}")
        except Exception as e:
            logger.error(f"Error sending WebSocket update: {str(e)}", exc_info=True) 