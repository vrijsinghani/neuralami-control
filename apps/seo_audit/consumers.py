import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import SEOAuditResult

logger = logging.getLogger(__name__)

class SEOAuditConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.audit_id = self.scope['url_route']['kwargs']['audit_id']
        self.audit_group_name = f'audit_{self.audit_id}'
        
        #logger.info(f"WebSocket connecting for audit {self.audit_id}")
        #logger.debug(f"Channel name: {self.channel_name}")
        #logger.debug(f"Group name: {self.audit_group_name}")

        # Join audit group
        try:
            await self.channel_layer.group_add(
                self.audit_group_name,
                self.channel_name
            )
            # logger.info(f"Added to group {self.audit_group_name}")
        except Exception as e:
            logger.error(f"Error joining group: {str(e)}")
            return

        try:
            await self.accept()
            # logger.info(f"WebSocket connection accepted for audit {self.audit_id}")
        except Exception as e:
            logger.error(f"Error accepting connection: {str(e)}")

    async def disconnect(self, close_code):
        # logger.info(f"WebSocket disconnecting for audit {self.audit_id} with code {close_code}")
        # Leave audit group
        try:
            await self.channel_layer.group_discard(
                self.audit_group_name,
                self.channel_name
            )
            # logger.info(f"Left group {self.audit_group_name}")
        except Exception as e:
            logger.error(f"Error leaving group: {str(e)}")

    async def receive(self, text_data):
        """Handle incoming messages from WebSocket"""
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type')
            # logger.info(f"Received message type: {message_type}")
            
            if message_type == 'get_status':
                await self.send_audit_status()
            elif message_type == 'test':
                # logger.info("Received test message, echoing back")
                await self.send(text_data=json.dumps({
                    'type': 'test',
                    'message': 'WebSocket connection working'
                }))
        except json.JSONDecodeError as e:
            logger.error(f"Invalid message format: {str(e)}")
            await self.send_error("Invalid message format")
        except Exception as e:
            logger.error(f"Error handling message: {str(e)}")
            await self.send_error(f"Error processing message: {str(e)}")

    async def audit_update(self, event):
        """Handle audit update messages"""
        #logger.info(f"Received audit update for {self.audit_id}")
        #logger.debug(f"Update data: {event}")
        try:
            await self.send(text_data=json.dumps({
                'type': 'audit.update',
                'data': event.get('data', {})
            }))
            # logger.debug("Sent audit update to client")
        except Exception as e:
            logger.error(f"Error sending audit update: {str(e)}")

    async def audit_complete(self, event):
        """Handle audit completion messages"""
        # logger.info(f"Received audit complete for {self.audit_id}")
        # logger.debug(f"Complete data: {event}")
        try:
            await self.send(text_data=json.dumps({
                'type': 'audit.complete',
                'data': event.get('data', {})
            }))
            # logger.debug("Sent audit complete to client")
        except Exception as e:
            logger.error(f"Error sending audit complete: {str(e)}")

    async def audit_error(self, event):
        """Handle audit error messages"""
        logger.error(f"Received audit error for {self.audit_id}: {event.get('error', 'Unknown error')}")
        try:
            await self.send(text_data=json.dumps({
                'type': 'audit.error',
                'error': event.get('error', 'Unknown error')
            }))
            logger.debug("Sent audit error to client")
        except Exception as e:
            logger.error(f"Error sending audit error: {str(e)}")

    @database_sync_to_async
    def get_audit_status(self):
        """Get current audit status"""
        try:
            audit = SEOAuditResult.objects.get(id=self.audit_id)
            return {
                'status': audit.status,
                'progress': audit.progress,
                'error': audit.error
            }
        except SEOAuditResult.DoesNotExist:
            logger.error(f"Audit {self.audit_id} not found")
            return None
        except Exception as e:
            logger.error(f"Error getting audit status: {str(e)}")
            return None

    async def send_audit_status(self):
        """Send current audit status to client"""
        # logger.info(f"Getting status for audit {self.audit_id}")
        status = await self.get_audit_status()
        if status:
            try:
                await self.send(text_data=json.dumps({
                    'type': 'audit.status',
                    'data': status
                }))
                # logger.debug("Sent audit status to client")
            except Exception as e:
                logger.error(f"Error sending audit status: {str(e)}")
        else:
            await self.send_error("Audit not found")

    async def send_error(self, message):
        """Send error message to client"""
        logger.error(f"Sending error for audit {self.audit_id}: {message}")
        try:
            await self.send(text_data=json.dumps({
                'type': 'audit.error',
                'error': message
            }))
        except Exception as e:
            logger.error(f"Error sending error message: {str(e)}") 