import logging
from typing import Dict, Optional, List
from .models import Research
import json
from django.db import transaction

logger = logging.getLogger(__name__)

class ResearchService:
    @staticmethod
    def update_research_steps(research_id: int, step_data: Dict) -> Optional[Research]:
        """Update research steps in the database."""
        try:
            logger.info(f"Updating research steps for research {research_id}")
            logger.info(f"Step data received: {json.dumps(step_data)}")
            
            # Use transaction context manager
            with transaction.atomic():
                # Get research object with select_for_update to prevent race conditions
                research = Research.objects.select_for_update().get(id=research_id)
                
                # Ensure we have a valid list for current_steps
                current_steps = research.reasoning_steps
                if current_steps is None or not isinstance(current_steps, list):
                    logger.warning(f"Current steps was not a valid list, resetting. Type was: {type(current_steps)}")
                    current_steps = []
                
                logger.info(f"Current step count before update: {len(current_steps)}")
                
                # Validate step data
                if not all(key in step_data for key in ['step_type', 'title', 'explanation']):
                    logger.error(f"Invalid step data format: {json.dumps(step_data)}")
                    return None
                
                # Only append if this is a new step
                is_duplicate = False
                if current_steps:
                    # Check for duplicate step based on step_type and title
                    for existing_step in current_steps:
                        if (existing_step.get('step_type') == step_data.get('step_type') and 
                            existing_step.get('title') == step_data.get('title')):
                            # Update the existing step instead of adding a new one
                            existing_step.update(step_data)
                            is_duplicate = True
                            logger.info(f"Updated existing step: {step_data.get('title')}")
                            break
                    
                    # Special case: don't add 'complete' step if it's already there
                    if step_data.get('step_type') == 'complete' and any(s.get('step_type') == 'complete' for s in current_steps):
                        is_duplicate = True
                        logger.info("Skipping duplicate complete step")
                
                if not is_duplicate:
                    current_steps.append(step_data)
                    logger.info(f"Added new step: {step_data.get('title')}")
                
                logger.info(f"Current step count after update: {len(current_steps)}")
                
                # Save the updated steps
                research.reasoning_steps = current_steps
                research.save(update_fields=['reasoning_steps'])
                
                # Verify the save
                research.refresh_from_db()
                logger.info(f"Verified step count after save: {len(research.reasoning_steps)}")
                
                return research
                
        except Research.DoesNotExist:
            logger.error(f"Research {research_id} not found")
            return None
        except Exception as e:
            logger.error(f"Error updating research steps: {str(e)}", exc_info=True)
            return None

    @staticmethod
    def update_research_status(research_id: int, status: str) -> Optional[Research]:
        """Update research status."""
        try:
            with transaction.atomic():
                research = Research.objects.select_for_update().get(id=research_id)
                research.status = status
                research.save(update_fields=['status'])
                return research
        except Research.DoesNotExist:
            logger.error(f"Research {research_id} not found")
            return None
        except Exception as e:
            logger.error(f"Error updating research status: {str(e)}", exc_info=True)
            return None

    @staticmethod
    def update_research_error(research_id: int, error_message: str) -> Optional[Research]:
        """Update research error state."""
        try:
            with transaction.atomic():
                research = Research.objects.select_for_update().get(id=research_id)
                research.error = error_message
                research.status = 'failed'
                research.save(update_fields=['error', 'status'])
                return research
        except Research.DoesNotExist:
            logger.error(f"Research {research_id} not found")
            return None
        except Exception as e:
            logger.error(f"Error updating research error: {str(e)}", exc_info=True)
            return None

    @staticmethod
    def update_research_report(research_id: int, report: str) -> Optional[Research]:
        """Update research report."""
        try:
            with transaction.atomic():
                research = Research.objects.select_for_update().get(id=research_id)
                research.report = report
                research.save(update_fields=['report'])
                return research
        except Research.DoesNotExist:
            logger.error(f"Research {research_id} not found")
            return None
        except Exception as e:
            logger.error(f"Error updating research report: {str(e)}", exc_info=True)
            return None

    @staticmethod
    def update_research_data(research_id: int, data: Dict) -> Optional[Research]:
        """Update research data fields (report, visited_urls, learnings)."""
        try:
            with transaction.atomic():
                research = Research.objects.select_for_update().get(id=research_id)
                
                fields_to_update = []
                
                if 'report' in data:
                    research.report = data['report']
                    fields_to_update.append('report')
                    
                if 'visited_urls' in data:
                    research.visited_urls = data['visited_urls']
                    fields_to_update.append('visited_urls')
                    
                if 'learnings' in data:
                    research.learnings = data['learnings']
                    fields_to_update.append('learnings')
                    
                if fields_to_update:
                    research.save(update_fields=fields_to_update)
                    
                return research
        except Research.DoesNotExist:
            logger.error(f"Research {research_id} not found")
            return None
        except Exception as e:
            logger.error(f"Error updating research data: {str(e)}", exc_info=True)
            return None 