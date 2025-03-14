from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from apps.agents.tools.deep_research_tool.deep_research_tool import DeepResearchTool
from .models import Research
from .services import ResearchService
import logging
from pydantic import Field
from typing import Any, Dict, List, Optional
from celery.exceptions import Ignore
import json
from contextlib import nullcontext
from apps.organizations.utils import OrganizationContext, get_current_organization

logger = logging.getLogger(__name__)
channel_layer = get_channel_layer()

class ProgressTracker:
    """Tracks progress of research tasks and sends updates via WebSockets."""
    
    def __init__(self, research_id):
        self.research_id = research_id
        self.group_name = f"research_{research_id}"
        self.step_count = 0
        logger.info(f"Initialized ProgressTracker for research {research_id}")

    def send_update(self, update_type: str, data: Dict):
        """Send an update to the WebSocket group."""
        try:
            # Determine the message type based on the update type
            if update_type in ['generating_queries', 'queries_generated', 'urls_found']:
                message_type = 'status_update'
                message_data = {
                    'status': 'in_progress',
                    'message': data.get('message', f'Processing {update_type}'),
                    'progress': self._calculate_progress(update_type)
                }
            elif update_type == 'step_added':
                message_type = 'step_update'
                self.step_count += 1
                message_data = {
                    'step': data.get('step', {}),
                    'step_number': self.step_count
                }
            elif update_type == 'completed':
                message_type = 'status_update'
                message_data = {
                    'status': 'completed',
                    'message': 'Research completed successfully',
                    'progress': 100
                }
            elif update_type == 'report_ready':
                message_type = 'report_update'
                message_data = {
                    'report_id': self.research_id
                }
            elif update_type == 'error':
                message_type = 'status_update'
                message_data = {
                    'status': 'failed',
                    'message': data.get('error', 'An error occurred'),
                    'progress': 0
                }
            elif update_type == 'cancelled':
                message_type = 'status_update'
                message_data = {
                    'status': 'cancelled',
                    'message': 'Research was cancelled',
                    'progress': 0
                }
            else:
                # Default to status update
                message_type = 'status_update'
                message_data = {
                    'status': 'in_progress',
                    'message': f'Processing {update_type}',
                    'progress': self._calculate_progress(update_type)
                }
            
            # Send the message to the group
            async_to_sync(channel_layer.group_send)(
                self.group_name,
                {
                    "type": message_type,
                    **message_data
                }
            )
            logger.debug(f"Sent {message_type} update for research {self.research_id}")
            
        except Exception as e:
            logger.error(f"Error sending WebSocket update for research {self.research_id}: {str(e)}", exc_info=True)
    
    def _calculate_progress(self, update_type: str) -> int:
        """Calculate progress percentage based on the update type."""
        # Define progress milestones for different stages
        progress_map = {
            'generating_queries': 10,
            'queries_generated': 20,
            'urls_found': 30,
            # Steps will increment between 30-90%
        }
        
        if update_type in progress_map:
            return progress_map[update_type]
        
        # For step updates, calculate based on expected total steps
        expected_total_steps = 10
        progress = 30 + min(60, int((self.step_count / expected_total_steps) * 60))
        return progress

    def check_cancelled(self) -> bool:
        """Check if the research has been cancelled."""
        try:
            # Use objects manager which is now organization-aware through the mixin
            research = Research.objects.get(id=self.research_id)
            return research.status == 'cancelled'
        except Research.DoesNotExist:
            return True

class ProgressDeepResearchTool(DeepResearchTool):
    """Extended DeepResearchTool that tracks progress and sends updates."""
    
    progress_tracker: Any = Field(None, exclude=True)

    def __init__(self, progress_tracker: ProgressTracker, **kwargs):
        super().__init__(**kwargs)
        self.progress_tracker = progress_tracker
        logger.info("Initialized ProgressDeepResearchTool with progress tracker")

    def _generate_serp_queries(self, query, num_queries, learnings=None, guidance=None):
        if self.progress_tracker.check_cancelled():
            raise Ignore()
            
        self.progress_tracker.send_update("generating_queries", {
            "message": f"Generating {num_queries} search queries..."
        })
        
        result = super()._generate_serp_queries(query, num_queries, learnings, guidance)
        
        self.progress_tracker.send_update("queries_generated", {
            "queries": [q["query"] for q in result]
        })
        
        return result

    def _extract_urls(self, search_results):
        if self.progress_tracker.check_cancelled():
            raise Ignore()
            
        urls = super()._extract_urls(search_results)
        
        self.progress_tracker.send_update("urls_found", {
            "urls": urls
        })
        
        return urls

    def _process_content(self, query, content, num_learnings=3, guidance=None):
        if self.progress_tracker.check_cancelled():
            raise Ignore()
        
        # Log content type and size for debugging
        content_type = type(content).__name__
        content_size = len(content) if isinstance(content, (str, dict)) else "unknown"
        logger.info(f"Processing content of type {content_type}, size {content_size}")
        
        # Create a proper content dictionary if content is a string
        if isinstance(content, str):
            # Check if we have URL information from the parent class call context
            url = getattr(self, '_current_url', 'unknown source')
            content_dict = {
                'url': url,
                'content': content
            }
            # Store the original content string
            original_content = content
            # Use the dictionary for processing
            result = super()._process_content(query, original_content, num_learnings, guidance)
        else:
            # Content is already a dictionary
            content_dict = content
            result = super()._process_content(query, content.get('content', content), num_learnings, guidance)
        
        # Validate result
        if not result:
            logger.error("Empty result from content processing")
            return {
                'learnings': [f"Unable to extract learnings from content about: {query}"],
                'follow_up_questions': [f"What are the key aspects of {query}?"]
            }
        
        # Log the result for debugging
        logger.info(f"Content processing result has {len(result.get('learnings', []))} learnings")
        if result.get('learnings'):
            for i, learning in enumerate(result.get('learnings', [])[:2]):
                logger.info(f"Task processor learning {i+1}: {learning[:100]}...")
        
        # Send step update
        if result and 'learnings' in result:
            url = content_dict.get('url', 'unknown source')
            content_length = len(content_dict.get('content', content_dict))
                
            step_data = {
                'step_type': 'content_analysis',
                'title': f"Analyzing content from {url}",
                'explanation': f"Extracting information relevant to the research query",
                'details': {
                    'url': url,
                    'source_length': content_length,
                    'focus': query,
                    'key_findings': result.get('learnings', []),
                    'follow_up_questions': result.get('follow_up_questions', [])
                }
            }
            
            # Add step to database
            research = ResearchService.update_research_steps(self.progress_tracker.research_id, step_data)
            
            # Send WebSocket update
            self.progress_tracker.send_update("step_added", {
                "step": step_data
            })
        
        return result

    # Override _update_token_counters to include progress updates
    def _update_token_counters(self):
        """Update total token counts from the token counter callback and send progress updates."""
        # Call the parent implementation to update counters
        input_tokens, output_tokens = super()._update_token_counters()
        
        # Send token usage update through progress tracker
        if hasattr(self, 'progress_tracker'):
            self.progress_tracker.send_update("token_usage", {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens
            })
        
        return input_tokens, output_tokens
        
    # Override _update_token_counters_from_subtool to include progress updates
    def _update_token_counters_from_subtool(self, input_tokens: int, output_tokens: int):
        """Update token counters with usage from a sub-tool and send progress updates."""
        # Call the parent implementation to update counters
        super()._update_token_counters_from_subtool(input_tokens, output_tokens)
        
        # Send token usage update through progress tracker
        if hasattr(self, 'progress_tracker'):
            self.progress_tracker.send_update("subtool_token_usage", {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "cumulative_input": self.total_input_tokens,
                "cumulative_output": self.total_output_tokens,
                "cumulative_total": self.total_input_tokens + self.total_output_tokens
            })

@shared_task
def run_research(research_id, model_name=None, tool_params=None, organization_id=None):
    """Run a research task with progress tracking."""
    research = None
    progress_tracker = None
    
    try:
        # Set organization context if provided
        from contextlib import nullcontext
        # Import Research model at the function level to avoid circular imports
        from apps.research.models import Research
        
        # Log the organization ID being passed to the task
        logger.info(f"Research task for ID {research_id} started with organization_id: {organization_id}")
        
        # If organization_id is not provided, try to get it from the research object first
        if not organization_id:
            try:
                # Use unfiltered_objects to avoid organization filtering when fetching initial object
                research_obj = Research.unfiltered_objects.get(id=research_id)
                organization_id = research_obj.organization_id
                logger.info(f"Got organization_id {organization_id} from research object")
            except Research.DoesNotExist:
                logger.error(f"Research {research_id} not found when trying to get organization ID")
                return {'success': False, 'error': f'Research {research_id} not found'}
            except Exception as e:
                logger.warning(f"Could not determine organization for research {research_id}: {str(e)}")
        
        # Verify that the Research object exists before entering context manager
        try:
            # Check if research exists using unfiltered manager (no organization context yet)
            research_obj = Research.unfiltered_objects.get(id=research_id)
            logger.info(f"Found research object with ID {research_id} using unfiltered manager. Organization ID: {research_obj.organization_id}")
        except Research.DoesNotExist:
            logger.error(f"Research {research_id} not found before entering organization context")
            return {'success': False, 'error': f'Research {research_id} not found'}
        except Exception as e:
            logger.error(f"Error checking if research {research_id} exists: {str(e)}")
            return {'success': False, 'error': f'Error checking research existence: {str(e)}'}
        
        # Use organization context manager if we have an organization ID
        context_manager = OrganizationContext.organization_context(organization_id) if organization_id else nullcontext()
        
        with context_manager:
            # Log the current organization context
            current_org = get_current_organization()
            logger.info(f"Current organization context inside context manager: {current_org.id if current_org else None}")
            
            try:
                # Try with objects manager first (organization-aware)
                logger.info(f"Attempting to get research {research_id} with objects manager")
                research = Research.objects.get(id=research_id)
                logger.info(f"Successfully found research with filtered objects manager")
            except Research.DoesNotExist:
                # Fallback to unfiltered objects if filtered query fails
                logger.warning(f"Research {research_id} not found with filtered manager. Falling back to unfiltered_objects.")
                try:
                    research = Research.unfiltered_objects.get(id=research_id)
                    logger.info(f"Found research with unfiltered_objects. Organization: {research.organization_id}")
                    
                    # Verify organization match
                    if organization_id and str(research.organization_id) != str(organization_id):
                        logger.warning(f"Organization mismatch! Task org: {organization_id}, Research org: {research.organization_id}")
                    
                except Research.DoesNotExist:
                    logger.error(f"Research {research_id} not found even with unfiltered_objects")
                    return {'success': False, 'error': f'Research {research_id} not found'}
            
            # Check if already cancelled before starting
            if research.status == 'cancelled':
                logger.info(f"Research task {research_id} was already cancelled")
                return {'success': False, 'status': 'cancelled'}
                
            # Update status to in_progress
            ResearchService.update_research_status(research_id, 'in_progress')

            # Initialize progress tracker
            progress_tracker = ProgressTracker(research_id)
            
            # Check if cancelled after tracker initialization
            if progress_tracker.check_cancelled():
                logger.info(f"Research task {research_id} was cancelled before starting")
                ResearchService.update_research_status(research_id, 'cancelled')
                progress_tracker.send_update("cancelled", {})
                return {'success': False, 'status': 'cancelled'}
                
            # Initialize tool with model name and any additional params
            tool_kwargs = {
                'progress_tracker': progress_tracker,
            }
            if tool_params:
                tool_kwargs.update(tool_params)
                
            # Create tool instance
            tool = ProgressDeepResearchTool(**tool_kwargs)

            # Get result from tool
            tool_result = tool._run(
                query=research.query,
                breadth=research.breadth,
                depth=research.depth,
                user_id=research.user_id,
                guidance=research.guidance
            )
            
            # For text-based output, store as is
            if isinstance(tool_result, str):
                logger.info(f"Report content length: {len(tool_result)}")
                report = tool_result
            # For JSON output, extract just the report field
            elif isinstance(tool_result, dict):
                # Check for deep_research_data structure
                if 'deep_research_data' in tool_result and 'report' in tool_result['deep_research_data']:
                    # Extract just the report content
                    report = tool_result['deep_research_data']['report']
                    logger.info(f"Extracted report content length: {len(report)}")
                else:
                    # Fallback to JSON string if structure is unexpected
                    logger.warning("Unexpected tool result structure, converting to JSON string")
                    report = json.dumps(tool_result, indent=2)
                
                # Get learnings from the appropriate location
                learnings = tool_result.get('deep_research_data', {}).get('learnings', [])
                visited_urls = tool_result.get('deep_research_data', {}).get('sources', [])
                
                logger.info(f"Received {len(learnings)} learnings from research tool")
                if learnings and len(learnings) > 0:
                    logger.debug(f"First few learnings: {', '.join(str(l) for l in learnings[:3])}")
            else:
                # Fallback for unexpected types
                report = str(tool_result)

            # Process the result
            if report:
                # Update research with all data including report
                ResearchService.update_research_data(research_id, {
                    'report': report,
                    'visited_urls': visited_urls if 'visited_urls' in locals() else [],
                    'learnings': learnings if 'learnings' in locals() else []
                })
                
                # Verify report was saved
                research.refresh_from_db()
                if not research.report:
                    logger.error(f"Report save failed for research {research_id}")
                    ResearchService.update_research_error(research_id, "Failed to save report")
                    progress_tracker.send_update("error", {"error": "Failed to save report"})
                else:
                    # Update status to completed
                    ResearchService.update_research_status(research_id, 'completed')
                    
                    # Send report ready notification
                    progress_tracker.send_update("report_ready", {})
                    
                    # Send completion notification
                    progress_tracker.send_update("completed", {})
            else:
                # Handle error
                error_message = "Unknown error occurred"
                ResearchService.update_research_error(research_id, error_message)
                progress_tracker.send_update("error", {"error": error_message})

    except Ignore:
        # Task was cancelled
        logger.info(f"Research task {research_id} was cancelled")
        if research:
            ResearchService.update_research_status(research_id, 'cancelled')
        if progress_tracker:
            progress_tracker.send_update("cancelled", {})

    except Exception as e:
        # Handle unexpected exceptions
        logger.error(f"Error in research task: {str(e)}", exc_info=True)
        if research:
            ResearchService.update_research_error(research_id, str(e))
            
            if progress_tracker:
                progress_tracker.send_update("error", {"error": str(e)}) 
    return {'success': True, 'status': research.status} 