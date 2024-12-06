from channels.generic.websocket import AsyncWebsocketConsumer
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class BaseWebSocketConsumer(AsyncWebsocketConsumer):
    async def send_json(self, data):
        """Send JSON data as text"""
        try:
            await self.send(text_data=json.dumps(data))
        except Exception as e:
            logger.error(f"Error sending JSON: {str(e)}")
            await self.send(text_data=json.dumps({
                'error': True,
                'message': 'Error sending message'
            }))

    async def handle_binary_message(self, message):
        """Handle binary message data"""
        try:
            if isinstance(message, bytes):
                message = message.decode('utf-8')
            return json.loads(message)
        except Exception as e:
            logger.error(f"Error handling binary message: {str(e)}")
            return None 