from channels.generic.websocket import AsyncWebsocketConsumer
import json
import logging

logger = logging.getLogger(__name__)

class BaseWebSocketConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.group_name = self.get_group_name()
        if self.group_name:
            await self.channel_layer.group_add(
                self.group_name,
                self.channel_name
            )
        await self.accept()

    async def disconnect(self, close_code):
        if self.group_name:
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            if data.get('type') == 'ping':
                await self.send_json({'type': 'pong'})
                return
            await self.handle_message(data)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid message format: {str(e)}")
            await self.send_error("Invalid message format")
        except Exception as e:
            logger.error(f"Error handling message: {str(e)}")
            await self.send_error(str(e))

    async def send_error(self, message):
        await self.send_json({
            'type': 'error',
            'message': message
        })

    async def send_json(self, content):
        await self.send(text_data=json.dumps(content))

    def get_group_name(self):
        """Override in child classes to set group name"""
        return None

    async def handle_message(self, data):
        """Override in child classes to handle specific messages"""
        pass 