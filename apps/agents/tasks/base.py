from celery import Task
from celery.utils.log import get_task_logger
from typing import Any, Dict, Optional

logger = get_task_logger(__name__)

class ProgressTask(Task):
    """Base task class that provides standardized progress reporting."""
    
    def update_progress(self, current: int, total: int, status: str = None, **kwargs) -> None:
        """
        Update task progress in a standardized way.
        
        Args:
            current: Current progress value
            total: Total expected value
            status: Status message
            **kwargs: Additional progress information
        """
        try:
            meta = {
                'current': current,
                'total': total,
                'progress_status': status,
                **kwargs
            }
            logger.debug(f"Updating task progress: {meta}")
            
            # Update state through standard Celery mechanism
            self.update_state(
                state='PROGRESS',
                meta=meta
            )
            
            # Force backend update to ensure persistence
            if hasattr(self, 'backend') and hasattr(self.backend, 'store_result'):
                try:
                    self.backend.store_result(
                        self.request.id,
                        meta,
                        'PROGRESS'
                    )
                except Exception as e:
                    logger.error(f"Failed to force progress update in backend: {e}")
        except Exception as e:
            logger.error(f"Failed to update progress: {e}")
    
    def before_start(self, task_id: str, args: Any, kwargs: Any) -> None:
        """Initialize progress tracking when task starts."""
        super().before_start(task_id, args, kwargs)
        self.update_progress(0, 100, "Task starting") 