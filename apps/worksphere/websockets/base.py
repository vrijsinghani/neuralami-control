from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.conf import settings


class BaseMessagingConsumer(AsyncJsonWebsocketConsumer):
    """
    Base WebSocket consumer for WorkSphere messaging.
    Handles authentication, connection lifecycle, and message routing.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None
        self.room_group_name = None

    async def connect(self):
        """
        Handle WebSocket connection.
        Authenticate user and set up room group.
        """
        if not self.scope["user"].is_authenticated:
            await self.close()
            return

        self.user = self.scope["user"]
        await self.accept()

    async def disconnect(self, close_code):
        """
        Handle WebSocket disconnection.
        Clean up any resources and group memberships.
        """
        if self.room_group_name:
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive_json(self, content):
        """
        Handle incoming WebSocket messages.
        Route messages to appropriate handlers based on message type.
        
        Args:
            content (dict): The message content
        """
        message_type = content.get('type')
        if not message_type:
            await self.send_error("Message type is required")
            return

        handler = getattr(self, f"handle_{message_type}", None)
        if not handler:
            await self.send_error(f"Unknown message type: {message_type}")
            return

        try:
            await handler(content)
        except Exception as e:
            if settings.DEBUG:
                await self.send_error(str(e))
            else:
                await self.send_error("An error occurred processing your request")

    async def send_error(self, message):
        """
        Send an error message to the client.
        
        Args:
            message (str): The error message
        """
        await self.send_json({
            'type': 'error',
            'message': message
        })

    async def send_success(self, data=None):
        """
        Send a success message to the client.
        
        Args:
            data (dict, optional): Additional data to send
        """
        response = {
            'type': 'success',
        }
        if data:
            response.update(data)
        await self.send_json(response)

    @database_sync_to_async
    def get_user(self):
        """
        Get the authenticated user.
        
        Returns:
            User: The authenticated user
        """
        return self.scope["user"]
