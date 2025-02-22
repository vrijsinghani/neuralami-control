from apps.common.websockets.base_consumer import BaseWebSocketConsumer
from channels.db import database_sync_to_async
from django.template.loader import render_to_string
from ..models import Research
import logging
import json

logger = logging.getLogger(__name__)

class ResearchConsumer(BaseWebSocketConsumer):
    async def connect(self):
        self.research_id = self.scope['url_route']['kwargs']['research_id']
        self.group_name = f"research_{self.research_id}"
        #logger.info(f"WebSocket connecting for research {self.research_id}")
        await super().connect()
        #logger.info(f"WebSocket connected for research {self.research_id}")

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
            #logger.info(f"Updating research {self.research_id} with data type: {data.get('type')}")
            
            # Handle reasoning steps
            if data.get('type') == 'reasoning':
                step_data = {
                    'step_type': data.get('step'),
                    'title': data.get('title'),
                    'explanation': data.get('explanation'),
                    'details': data.get('details', {})
                }
                #logger.info(f"Adding reasoning step: {step_data['title']}")
                
                # Append new step to reasoning_steps
                research.reasoning_steps = research.reasoning_steps + [step_data]
                research.save(update_fields=['reasoning_steps'])
                #logger.info(f"Research now has {len(research.reasoning_steps)} reasoning steps")
                
            # Handle status updates
            elif data.get('type') == 'status':
                #logger.info(f"Updating status to: {data.get('status')}")
                research.status = data.get('status')
                research.save(update_fields=['status'])
                
            # Handle error updates
            elif data.get('type') == 'error':
                logger.error(f"Research error: {data.get('message')}")
                research.error = data.get('message')
                research.status = 'failed'
                research.save(update_fields=['error', 'status'])

            # Handle report updates
            elif data.get('type') == 'report':
                #logger.info(f"Updating report for research {self.research_id}")
                research.report = data.get('report')
                # Only update the report field, preserving other fields
                research.save(update_fields=['report'])
                
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
        data = event.get('data')
        if not data:
            logger.error(f"No data in research update event for research {self.research_id}")
            return
            
        logger.info(f"Received research update: {data.get('update_type')} for research {self.research_id}")
        logger.debug(f"Update data contents: {json.dumps(data)[:500]}")  # Log first 500 chars of data
        
        # Update research object if needed
        update_type = data.get('update_type')
        if update_type in ['reasoning', 'status', 'error', 'report']:
            research = await self.update_research({
                'type': update_type,
                **data
            })
            
            if research:
                if update_type == 'reasoning':
                    # Only render the latest step
                    latest_step = research.reasoning_steps[-1] if research.reasoning_steps else None
                    if latest_step:
                        # Add step number to details for template
                        latest_step['details']['step_number'] = len(research.reasoning_steps)
                        
                        # For content analysis steps, include content length in KB
                        if latest_step.get('step') == 'content_analysis' and 'source_length' in latest_step.get('details', {}):
                            latest_step['details']['source_length_kb'] = f"{latest_step['details']['source_length'] / 1024:.1f}"
                        
                        # For insights steps, ensure learnings are included
                        if latest_step.get('step') == 'insights_extracted':
                            if 'key_findings' in latest_step.get('details', {}):
                                latest_step['details']['learnings'] = latest_step['details']['key_findings']
                        
                        # Render just the new step
                        html = await self.render_template_async(
                            'research/partials/_step.html',
                            {
                                'step': latest_step,
                                'step_number': len(research.reasoning_steps),
                                'is_last': True,
                                'details': latest_step.get('details', {})
                            }
                        )
                        logger.debug(f"Sending WebSocket HTML update for new step: {latest_step['title']}")
                        
                        # Send the new step to be inserted before the processing indicator
                        await self.send(text_data=f'''
                            <div id="step-{latest_step['step_type']}-{len(research.reasoning_steps)}" 
                                 hx-swap-oob="beforebegin:#processing-indicator">
                                {html}
                            </div>
                        ''')
                
                elif update_type == 'status':
                    # For status updates, target the progress bar and status badge
                    if 'progress_percent' in data:
                        updates = []
                        # Update progress bar
                        updates.append(f'<div id="research-progress" class="progress-bar bg-gradient-primary" role="progressbar" style="width: {data.get("progress_percent")}%" hx-swap-oob="true"></div>')
                        # Update status badge
                        updates.append(f'<span id="status-badge" class="badge bg-gradient-primary" hx-swap-oob="true">{research.status.title()}</span>')
                        
                        # If research is complete
                        if research.status == 'completed':
                            # Remove processing indicator
                            updates.append('<div id="processing-indicator" class="d-none" hx-swap-oob="true"></div>')
                        
                        await self.send(text_data=''.join(updates))
                
                elif update_type == 'report':
                    # Handle report updates separately
                    if research.report:
                        logger.debug(f"Sending report update. First 500 chars: {research.report[:500]}")
                        # Escape the markdown content for the data attribute
                        escaped_markdown = research.report.replace('"', '&quot;').replace("'", "&#39;").replace("<", "&lt;").replace(">", "&gt;")
                        await self.send(text_data=f'''
                            <div id="report-section" hx-swap-oob="true">
                                <div class="mt-4">
                                    <h6 class="mb-3">Research Report</h6>
                                    <div class="p-3 bg-gray-100 border-radius-md">
                                        <div class="markdown-content" id="report-content" data-raw-markdown="{escaped_markdown}"></div>
                                    </div>
                                </div>
                            </div>
                        ''')
                    else:
                        logger.warning(f"Research {self.research_id} report update but no report found")
                
                elif update_type == 'error':
                    # For errors, show in the progress container
                    html = f'<div id="progress-container" class="alert alert-danger text-white" role="alert" hx-swap-oob="true">{research.error}</div>'
                    await self.send(text_data=html)

    @database_sync_to_async
    def render_template_async(self, template_name, context):
        return render_to_string(template_name, context)