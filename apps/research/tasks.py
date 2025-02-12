from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from apps.agents.tools.deep_research_tool.deep_research_tool import DeepResearchTool
from .models import Research
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
        #logger.info(f"Sending update type {update_type} for research {self.research_id}: {data}")
        try:
            async_to_sync(channel_layer.group_send)(
                self.group_name,
                {
                    "type": "research_update",
                    "data": {
                        "update_type": update_type,
                        **data
                    }
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

    def _generate_serp_queries(self, query, num_queries, learnings=None):
        if self.progress_tracker.check_cancelled():
            raise Ignore()
        self.progress_tracker.send_update("generating_queries", {
            "message": f"Generating {num_queries} search queries..."
        })
        result = super()._generate_serp_queries(query, num_queries, learnings)
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

    def _process_content(self, query, content, num_learnings=3):
        if self.progress_tracker.check_cancelled():
            raise Ignore()
        self.progress_tracker.send_update("processing_content", {
            "message": f"Processing content for query: {query}"
        })
        # submit progress_tracker for first 100 chars of content
        self.progress_tracker.send_update("processing_content", {
            "message": f"Content: {content[:100]}"
        })
        result = super()._process_content(query, content, num_learnings)
        self.progress_tracker.send_update("learnings_extracted", {
            "learnings": result["learnings"]
        })
        return result

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
            
        research.status = 'in_progress'
        research.save()

        progress_tracker = ProgressTracker(research_id)
        
        # Check if cancelled after tracker initialization
        if progress_tracker.check_cancelled():
            logger.info(f"Research task {research_id} was cancelled before starting")
            research.status = 'cancelled'
            research.save()
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
            user_id=research.user_id
        )

        if result['success']:
            data = result['deep_research_data']
            research.status = 'completed'
            research.report = data['report']
            research.visited_urls = data['sources']
            research.learnings = data['learnings']
        else:
            research.status = 'failed'
            research.error = result.get('error', 'Unknown error occurred')

        research.save()
        
        # Send final update
        progress_tracker.send_update("completed", {
            "status": research.status,
            "report": research.report if research.status == 'completed' else None,
            "error": research.error if research.status == 'failed' else None
        })

    except Ignore:
        # Task was cancelled
        logger.info(f"Research task {research_id} was cancelled")
        if research:
            research.status = 'cancelled'
            research.save()
        if progress_tracker:
            progress_tracker.send_update("cancelled", {})
        return

    except Exception as e:
        logger.error(f"Error in research task: {str(e)}", exc_info=True)
        if research:
            research.status = 'failed'
            research.error = str(e)
            research.save()
            
            if progress_tracker:
                progress_tracker.send_update("error", {
                    "error": str(e)
                }) 