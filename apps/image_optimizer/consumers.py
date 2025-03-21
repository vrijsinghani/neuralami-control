from channels.generic.websocket import AsyncJsonWebsocketConsumer
from apps.common.websockets.organization_consumer import OrganizationAwareConsumer
from channels.db import database_sync_to_async
from .models import OptimizedImage, OptimizationJob
import json
import logging

logger = logging.getLogger(__name__)

# Create a custom consumer that combines AsyncJsonWebsocketConsumer and OrganizationAwareConsumer
class OrganizationAwareJsonConsumer(OrganizationAwareConsumer):
    """
    Combines OrganizationAwareConsumer with AsyncJsonWebsocketConsumer functionality.
    """
    async def send_json(self, content, close=False):
        """Send JSON data to the client"""
        await self.send(text_data=json.dumps(content), close=close)
        
    async def receive_json(self, content):
        """
        Override to handle JSON messages. To be implemented by subclasses.
        """
        pass
        
    async def receive(self, text_data, **kwargs):
        """Parse the JSON content and call receive_json"""
        try:
            data = json.loads(text_data)
            await self.receive_json(data)
        except json.JSONDecodeError:
            logger.error("Invalid JSON received")
            await self.send_json({"error": "Invalid JSON"})

class OptimizationConsumer(OrganizationAwareJsonConsumer):
    async def connect(self):
        """Handle connection with organization context"""
        # Set organization context first
        await super().connect()
        
        # Get optimization_id from URL route
        self.optimization_id = self.scope['url_route']['kwargs']['optimization_id']
        self.job_group_name = None

        # Accept the connection
        await self.accept()

        # Add to optimization-specific group
        await self.channel_layer.group_add(
            f"optimization_{self.optimization_id}",
            self.channel_name
        )

        # Get job ID and add to job group if part of a job
        job_id = await self.get_job_id()
        if job_id:
            self.job_group_name = f"optimization_job_{job_id}"
            await self.channel_layer.group_add(
                self.job_group_name,
                self.channel_name
            )

    async def disconnect(self, close_code):
        """Handle disconnection"""
        # Remove from optimization group
        await self.channel_layer.group_discard(
            f"optimization_{self.optimization_id}",
            self.channel_name
        )

        # Remove from job group if part of a job
        if self.job_group_name:
            await self.channel_layer.group_discard(
                self.job_group_name,
                self.channel_name
            )
            
        # Clear organization context
        await super().disconnect(close_code)

    @database_sync_to_async
    def get_job_id(self):
        """Get job ID for the optimization"""
        try:
            optimization = OptimizedImage.objects.get(id=self.optimization_id)
            return optimization.job_id if optimization.job else None
        except OptimizedImage.DoesNotExist:
            return None

    async def optimization_update(self, event):
        """Handle optimization updates"""
        # Add message type to data
        data = event['data']
        data['type'] = 'optimization_update'
        # Send message to WebSocket
        await self.send_json(data)

    async def job_update(self, event):
        """Handle job updates"""
        # Add message type to data
        data = event['data']
        data['type'] = 'job_update'
        # Send message to WebSocket
        await self.send_json(data) 