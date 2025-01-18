from channels.generic.websocket import AsyncWebsocketConsumer
import json
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

class CrewKanbanConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        """
        Handle WebSocket connection setup
        """
        self.crew_id = self.scope['url_route']['kwargs']['crew_id']
        self.room_group_name = f'crew_{self.crew_id}_kanban'
        self.is_connected = False
        
        try:
            # Add to crew group
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            await self.accept()
            self.is_connected = True
            logger.info(f"WebSocket connection established for crew {self.crew_id}")
        except Exception as e:
            logger.error(f"Error establishing WebSocket connection: {str(e)}")
            if not self.is_connected:
                await self.close()
    
    async def disconnect(self, close_code):
        """
        Handle WebSocket disconnection cleanup
        """
        try:
            self.is_connected = False
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            logger.info(f"WebSocket connection closed for crew {self.crew_id} with code {close_code}")
        except Exception as e:
            logger.error(f"Error during WebSocket disconnect: {str(e)}")
    
    async def receive(self, text_data):
        """
        Handle incoming WebSocket messages
        """
        if not self.is_connected:
            logger.warning("Received message but WebSocket is not connected")
            return
            
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            logger.debug(f"Received WebSocket message: {message_type}")
            
            # Handle ping messages immediately
            if message_type == 'ping':
                await self.send(text_data=json.dumps({
                    'type': 'pong'
                }))
                return
            
            handlers = {
                'execution_update': self.handle_execution_update,
                'agent_step': self.handle_agent_step,
                'human_input_request': self.handle_human_input_request,
                'task_complete': self.handle_task_complete
            }
            
            handler = handlers.get(message_type)
            if handler:
                await handler(data)
            else:
                logger.warning(f"Unknown message type received: {message_type}")
        
        except json.JSONDecodeError:
            logger.error(f"Failed to decode WebSocket message: {text_data}")
        except Exception as e:
            logger.error(f"Error processing WebSocket message: {str(e)}")
            if self.is_connected:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Internal server error occurred'
                }))
    
    async def handle_execution_update(self, data):
        """Handle execution status updates"""
        if not self.is_connected:
            logger.warning("Cannot send execution update - WebSocket not connected")
            return
            
        try:
            # Get crewai_task_id from execution
            execution_id = data.get('execution_id')
            if execution_id:
                crewai_task_id = await self.get_task_id_for_execution(execution_id)
                data['crewai_task_id'] = crewai_task_id
            
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'execution_update',
                    **data
                }
            )
            logger.debug(f"Sent execution update for execution {execution_id}")
        except Exception as e:
            logger.error(f"Error sending execution update: {str(e)}")
            # Don't try to send error message if we already know connection is broken
            if self.is_connected:
                try:
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': 'Failed to send execution update'
                    }))
                except:
                    pass

    async def handle_agent_step(self, data):
        """Handle individual agent step updates"""
        if not self.is_connected:
            logger.warning("Cannot send agent step - WebSocket not connected")
            return
            
        try:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'agent_step',
                    'execution_id': data.get('execution_id'),
                    'agent': data.get('agent', ''),
                    'content': data.get('content', ''),
                    'step_type': data.get('step_type', ''),
                    'is_final_step': data.get('is_final_step', False)
                }
            )
        except Exception as e:
            logger.error(f"Error sending agent step: {str(e)}")
            if self.is_connected:
                try:
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': 'Failed to send agent step'
                    }))
                except:
                    pass

    async def handle_human_input_request(self, data):
        """Handle requests for human input"""
        if not self.is_connected:
            logger.warning("Cannot send human input request - WebSocket not connected")
            return
            
        try:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'human_input_request',
                    'execution_id': data.get('execution_id'),
                    'prompt': data.get('prompt', ''),
                    'context': data.get('context', {})
                }
            )
        except Exception as e:
            logger.error(f"Error sending human input request: {str(e)}")
            if self.is_connected:
                try:
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': 'Failed to send human input request'
                    }))
                except:
                    pass

    async def handle_task_complete(self, data):
        """Handle task completion notifications"""
        if not self.is_connected:
            logger.warning("Cannot send task complete - WebSocket not connected")
            return
            
        try:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'task_complete',
                    'execution_id': data.get('execution_id'),
                    'message': data.get('message', ''),
                    'results': data.get('results', {})
                }
            )
        except Exception as e:
            logger.error(f"Error sending task complete: {str(e)}")
            if self.is_connected:
                try:
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': 'Failed to send task complete'
                    }))
                except:
                    pass
    
    # WebSocket send handlers
    async def execution_update(self, event):
        """Send execution updates to WebSocket"""
        if not self.is_connected:
            logger.warning("Cannot send execution update - WebSocket not connected")
            return
            
        try:
            # Ensure stage data has all required fields
            stage = event.get('stage', {})
            if stage:
                stage.setdefault('stage_type', 'processing')
                stage.setdefault('title', 'Processing...')
                stage.setdefault('content', '')
                stage.setdefault('status', 'in_progress')
                stage.setdefault('agent', 'System')
                stage.setdefault('completed', False)
                
                # Mark stage as completed if status is 'completed'
                if stage.get('status') == 'completed':
                    stage['completed'] = True
                
                # Ensure chat_message_prompts exists and has at least one item
                if 'chat_message_prompts' not in stage:
                    stage['chat_message_prompts'] = [{
                        'role': 'system',
                        'content': stage.get('content', 'Processing task...')
                    }]
            
            # Use the crewai_task_id directly from the event
            crewai_task_id = event.get('crewai_task_id')
            # if not crewai_task_id:
            #     logger.debug(f"No CrewAI task ID provided in event for execution {event.get('execution_id')}")
            
            await self.send(text_data=json.dumps({
                'type': 'execution_update',
                'execution_id': event['execution_id'],  # Internal execution ID
                'status': event['status'],
                'crewai_task_id': crewai_task_id,  # Use task ID from event for kanban board placement
                'message': event.get('message'),
                'stage': stage,
                'human_input_request': event.get('human_input_request')  # Add this line

            }))
        except Exception as e:
            logger.error(f"Error sending execution update: {str(e)}")
            if self.is_connected:
                try:
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': 'Failed to send execution update'
                    }))
                except:
                    pass

    async def agent_step(self, event):
        """Send agent step updates to WebSocket"""
        if not self.is_connected:
            logger.warning("Cannot send agent step - WebSocket not connected")
            return
            
        try:
            # Get crewai_task_id for this execution
            execution_id = event['execution_id']
            crewai_task_id = await self.get_task_id_for_execution(execution_id)
            
            # Format agent step as a stage update with chat_message_prompts
            stage_data = {
                'stage_type': event.get('step_type', 'agent_step'),
                'title': f"Agent: {event.get('agent', 'System')}",
                'content': event.get('content', ''),
                'status': 'in_progress',
                'agent': event.get('agent', 'System'),
                'completed': False,
                'chat_message_prompts': [{
                    'role': 'assistant',
                    'content': event.get('content', '')
                }]
            }
            
            await self.send(text_data=json.dumps({
                'type': 'execution_update',
                'execution_id': execution_id,
                'crewai_task_id': crewai_task_id,
                'stage': stage_data
            }))
            
            # Send a completion update for this stage if it's the final step
            if event.get('is_final_step', False):
                stage_data.update({
                    'status': 'completed',
                    'completed': True
                })
                await self.send(text_data=json.dumps({
                    'type': 'execution_update',
                    'execution_id': execution_id,
                    'crewai_task_id': crewai_task_id,
                    'stage': stage_data
                }))
        except Exception as e:
            logger.error(f"Error sending agent step: {str(e)}")
            if self.is_connected:
                try:
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': 'Failed to send agent step'
                    }))
                except:
                    pass

    async def human_input_request(self, event):
        """Send human input requests to WebSocket"""
        logger.debug(f"Consumer received human_input_request event: {event}")
        try:
            message = {
                'type': 'human_input_request',
                'execution_id': event['execution_id'],
                'prompt': event['prompt'],
                'context': event.get('context', {})
            }
            logger.debug(f"Consumer attempting to send message: {message}")
            await self.send(text_data=json.dumps(message))
            logger.debug("Consumer successfully sent message")
        except Exception as e:
            logger.error(f"Consumer failed to send message: {e}")

    async def task_complete(self, event):
        """Send task completion notifications to WebSocket"""
        execution_id = event['execution_id']
        crewai_task_id = await self.get_task_id_for_execution(execution_id)
        
        await self.send(text_data=json.dumps({
            'type': 'task_complete',
            'execution_id': execution_id,
            'crewai_task_id': crewai_task_id,
            'message': event['message'],
            'results': event['results']
        }))

    @database_sync_to_async
    def get_task_id_for_execution(self, execution_id):
        """Get CrewAI task ID for a given execution"""
        from .models import CrewExecution
        try:
            execution = CrewExecution.objects.get(id=execution_id)
            # Get the latest execution stage for this execution
            latest_stage = execution.executionstage_set.order_by('-created_at').first()
            return latest_stage.crewai_task_id if latest_stage else None
        except CrewExecution.DoesNotExist:
            return None
