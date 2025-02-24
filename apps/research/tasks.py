from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from apps.agents.tools.deep_research_tool.deep_research_tool import DeepResearchTool
from .models import Research
from .services import ResearchService
import logging
from pydantic import Field
from typing import Any
from celery.exceptions import Ignore

logger = logging.getLogger(__name__)
channel_layer = get_channel_layer()

class ProgressTracker:
    def __init__(self, research_id):
        self.research_id = research_id
        self.group_name = f"research_{research_id}"
        logger.info(f"Initialized ProgressTracker for research {research_id}")

    def send_update(self, update_type, data):
        #logger.info(f"Sending update type {update_type} for research {self.research_id}")
        try:
            update_data = {
                "update_type": update_type,
                **data
            }
            logger.info(f"Update data: {update_data}")
            
            async_to_sync(channel_layer.group_send)(
                self.group_name,
                {
                    "type": "research_update",
                    "data": update_data
                }
            )
            #logger.info(f"Successfully sent update type {update_type} for research {self.research_id}")
        except Exception as e:
            logger.error(f"Error sending WebSocket update for research {self.research_id}: {str(e)}", exc_info=True)

    def check_cancelled(self):
        """Check if the research has been cancelled."""
        try:
            research = Research.objects.get(id=self.research_id)
            return research.status == 'cancelled'
        except Research.DoesNotExist:
            return True

class ProgressDeepResearchTool(DeepResearchTool):
    progress_tracker: Any = Field(None, exclude=True)

    def __init__(self, progress_tracker: ProgressTracker, **kwargs):
        super().__init__(**kwargs)
        self.progress_tracker = progress_tracker

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
        return super()._process_content(query, content, num_learnings, guidance)

@shared_task
def run_research(research_id, model_name=None, tool_params=None):
    research = None
    progress_tracker = None
    try:
        research = Research.objects.get(id=research_id)
        
        # Check if already cancelled before starting
        if research.status == 'cancelled':
            logger.info(f"Research task {research_id} was already cancelled")
            return
            
        ResearchService.update_research_status(research_id, 'in_progress')

        progress_tracker = ProgressTracker(research_id)
        
        # Check if cancelled after tracker initialization
        if progress_tracker.check_cancelled():
            logger.info(f"Research task {research_id} was cancelled before starting")
            ResearchService.update_research_status(research_id, 'cancelled')
            progress_tracker.send_update("cancelled", {})
            return
            
        # Initialize tool with model name and any additional params
        tool_kwargs = {
            'progress_tracker': progress_tracker,
        }
        if tool_params:
            tool_kwargs.update(tool_params)
            
        tool = ProgressDeepResearchTool(**tool_kwargs)

        result = tool._run(
            query=research.query,
            breadth=research.breadth,
            depth=research.depth,
            user_id=research.user_id,
            guidance=research.guidance
        )

        if result['success']:
            data = result['deep_research_data']
            
            # Debug log report content
            logger.info(f"Report content length: {len(data.get('report', ''))}")
            logger.debug(f"Report content preview: {data.get('report', '')[:500]}")
            
            # Update research with all data including report
            ResearchService.update_research_data(research_id, {
                'report': data['report'],
                'visited_urls': data['sources'],
                'learnings': data['learnings']
            })
            
            # Verify report was saved
            research.refresh_from_db()
            logger.info(f"After refresh - Report exists: {bool(research.report)}, Length: {len(research.report or '')}")
            if not research.report:
                logger.error(f"Report save failed for research {research_id}")
                ResearchService.update_research_error(research_id, "Failed to save report")
                progress_tracker.send_update("error", {"error": "Failed to save report"})
            else:
                # Update status to completed first
                ResearchService.update_research_status(research_id, 'completed')
                research.refresh_from_db()  # Refresh to get latest status
                
                # Now send report ready
                progress_tracker.send_update("report_ready", {"message": "Report is ready to view"})
                progress_tracker.send_update("completed", {
                    "status": "completed",
                    "error": None
                })
            
            # Send final completion status
            progress_tracker.send_update("completed", {
                "status": "completed",
                "error": None
            })
        else:
            ResearchService.update_research_error(research_id, result.get('error', 'Unknown error occurred'))
            
            # Send error status
            progress_tracker.send_update("error", {
                "error": result.get('error', 'Unknown error occurred')
            })

    except Ignore:
        # Task was cancelled
        logger.info(f"Research task {research_id} was cancelled")
        if research:
            ResearchService.update_research_status(research_id, 'cancelled')
        if progress_tracker:
            progress_tracker.send_update("cancelled", {})
        return

    except Exception as e:
        logger.error(f"Error in research task: {str(e)}", exc_info=True)
        if research:
            ResearchService.update_research_error(research_id, str(e))
            
            if progress_tracker:
                progress_tracker.send_update("error", {
                    "error": str(e)
                }) 