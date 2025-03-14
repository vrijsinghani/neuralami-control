from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.template.loader import render_to_string
from ..models import Research
from ..services import ResearchService
from apps.common.websockets.organization_consumer import OrganizationAwareConsumer
import logging
import json
import asyncio

logger = logging.getLogger(__name__)

class ResearchConsumer(OrganizationAwareConsumer):
    """
    WebSocket consumer for research app that handles real-time updates.
    Uses a standardized message protocol for all communications.
    Supports organization context for multi-tenancy.
    """
    
    async def connect(self):
        """Handle WebSocket connection"""
        logger.debug(f"Starting connection for research WebSocket with URL route: {self.scope.get('url_route', {})}")
        
        try:
            # Set organization context first
            await super().connect()
            
            self.research_id = self.scope['url_route']['kwargs']['research_id']
            #logger.debug(f"Extracted research_id from URL route: {self.research_id}")
            self.group_name = f"research_{self.research_id}"
            
            # Join the group
            #logger.debug(f"Joining channel group: {self.group_name}")
            await self.channel_layer.group_add(
                self.group_name,
                self.channel_name
            )
            
            # Accept the connection
            #logger.debug("Accepting WebSocket connection")
            await self.accept()
            #logger.info(f"WebSocket connected for research {self.research_id}")
            
            # Send initial state
            #logger.debug("Sending initial state")
            await self.send_initial_state()
        except Exception as e:
            logger.error(f"Error in WebSocket connect: {str(e)}", exc_info=True)
            raise
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        logger.info(f"WebSocket disconnected for research {self.research_id} with code {close_code}")
        
        # Leave the group
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )
        
        # Clear organization context
        await super().disconnect(close_code)
    
    async def receive(self, text_data):
        """Handle messages from WebSocket client"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'get_state':
                await self.send_initial_state()
            elif message_type == 'cancel_research':
                logger.info(f"Received cancel_research request for {self.research_id}")
                await self.cancel({"type": "cancel"})
            else:
                logger.warning(f"Unknown message type: {message_type}")
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received: {text_data}")
            await self.send_error("Invalid message format")
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}", exc_info=True)
            await self.send_error(f"Error processing message: {str(e)}")

    @database_sync_to_async
    def get_research(self, research_id):
        """Fetch a research object by ID."""
        from apps.research.models import Research
        
        try:
            #logger.debug(f"Attempting to fetch research with ID: {research_id}")
            research = Research.objects.get(id=research_id)
            #logger.debug(f"Successfully found research with ID: {research_id}")
            return research
        except Research.DoesNotExist:
            # Fallback to unfiltered objects if filtered query fails
            logger.warning(f"Research {research_id} not found with filtered manager. Falling back to unfiltered_objects.")
            try:
                research = Research.unfiltered_objects.get(id=research_id)
                logger.info(f"Found research with unfiltered_objects. Organization: {research.organization_id}")
                return research
            except Research.DoesNotExist:
                logger.error(f"Research {research_id} not found")
                return None

    @database_sync_to_async
    def cancel_research(self):
        """Cancel the research in database"""
        from apps.research.models import Research
        
        try:
            # Try with objects manager first (organization-aware)
            research = Research.objects.get(id=self.research_id)
            logger.info(f"Found research to cancel with objects manager: {research.id}")
        except Research.DoesNotExist:
            # Fallback to unfiltered objects if filtered query fails
            try:
                research = Research.unfiltered_objects.get(id=self.research_id)
                logger.info(f"Found research to cancel with unfiltered_objects: {research.id}, org: {research.organization_id}")
            except Research.DoesNotExist:
                logger.error(f"Research {self.research_id} not found for cancellation")
                return None
        
        if research.status == 'completed':
            logger.info(f"Research {self.research_id} already completed, cannot cancel")
            return research
        
        research.status = 'cancelled'
        research.save()
        logger.info(f"Research {self.research_id} cancelled")
        return research
    
    @database_sync_to_async
    def render_template_async(self, template_name, context):
        """Render a template asynchronously"""
        return render_to_string(template_name, context)
    
    async def send_initial_state(self):
        """Send initial state to the client"""
        research = await self.get_research(self.research_id)
        if not research:
            await self.send_error("Research not found")
            return
        
        # Send current state
        await self.send_json({
            'type': 'initial_state',
            'research': {
                'id': research.id,
                'status': research.status,
                'progress': self._calculate_progress(research),
                'query': research.query,
                'created_at': research.created_at.isoformat(),
                'error': research.error
            }
        })
        
        # Send HTML for steps
        if research.reasoning_steps:
            html = await self.render_template_async(
                'research/partials/steps.html',
                {'research': research}
            )
            await self.send(text_data=html)
    
    def _calculate_progress(self, research):
        """Calculate progress percentage based on research state"""
        if research.status == 'completed':
            return 100
        elif research.status == 'failed' or research.status == 'cancelled':
            return 0
        elif research.status == 'pending':
            return 0
        
        # For in_progress, calculate based on steps
        if not research.reasoning_steps:
            return 5  # Just started
        
        # Estimate progress based on number of steps and expected total
        step_count = len(research.reasoning_steps)
        expected_total = 10  # Typical number of steps for a complete research
        
        progress = min(95, int((step_count / expected_total) * 100))
        return progress
    
    async def send_json(self, data):
        """Send JSON data to the WebSocket"""
        await self.send(text_data=json.dumps(data))
    
    async def send_error(self, message):
        """Send error message to the WebSocket"""
        await self.send_json({
            'type': 'error',
            'message': message
        })
    
    # Channel layer event handlers
    
    async def status_update(self, event):
        """Handle status update event from channel layer"""
        await self.send_json({
            'type': 'status_update',
            'status': event['status'],
            'message': event.get('message', ''),
            'progress': event.get('progress')
        })
    
    async def step_update(self, event):
        """Handle step update event from channel layer"""
        step_data = event.get('step', {})
        
        # Render the step HTML
        html = await self.render_template_async(
            'research/partials/_step.html',
            {
                'step': step_data,
                'step_number': event.get('step_number', 1),
                'is_last': True
            }
        )
        
        # Send both the raw data and the HTML
        await self.send_json({
            'type': 'step_update',
            'step': step_data,
            'step_number': event.get('step_number', 1)
        })
        
        # Send the HTML with OOB swap instruction
        step_id = f"step-{step_data.get('step_type', 'unknown')}-{event.get('step_number', 1)}"
        await self.send(text_data=f'''
            <div id="{step_id}" 
                 hx-swap-oob="beforeend:#steps-container">
                {html}
            </div>
        ''')
        
    async def report_update(self, event):
        """Handle report update event from channel layer"""
        research = await self.get_research(self.research_id)
        if not research or not research.report:
            return
        
        # Render the report HTML
        html = await self.render_template_async(
            'research/partials/_report.html',
            {'research': research}
        )
        
        # Send the HTML with OOB swap instruction
        await self.send(text_data=f'''
            <div id="report-section" hx-swap-oob="innerHTML">
                {html}
            </div>
        ''')

    async def cancel(self, event):
        """Handle cancel request from client"""
        logger.info(f"Cancel request received for research {self.research_id}")
        research = await self.cancel_research()
        
        if research:
            # Send cancellation message to group
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "status_update",
                    "status": "cancelled",
                    "message": "Research cancelled by user"
                }
            )
            await self.send_json({
                "type": "cancel_response",
                "success": True,
                "message": "Research cancelled"
            })
        else:
            await self.send_json({
                "type": "cancel_response",
                "success": False,
                "message": "Research not found or already completed"
            })
