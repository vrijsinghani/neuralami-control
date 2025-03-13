import functools
import logging
from celery import shared_task

from apps.organizations.utils import OrganizationContext

logger = logging.getLogger(__name__)

def organization_aware_task(**task_kwargs):
    """
    Decorator for Celery tasks that preserves organization context.
    
    This decorator wraps Celery's shared_task decorator to automatically
    handle organization context propagation. It ensures that tasks
    executed in the background maintain the correct organization context.
    
    Example usage:
    
    @organization_aware_task()
    def my_task(arg1, arg2, organization_id=None):
        # This task will have the correct organization context set
        # based on the organization_id parameter
        ...
    
    # Call the task with organization context
    my_task.delay(arg1, arg2, organization_id=org.id)
    """
    def decorator(func):
        @shared_task(**task_kwargs)
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Extract organization_id from kwargs
            organization_id = kwargs.pop('organization_id', None)
            
            if not organization_id:
                logger.warning(
                    f"Task {func.__name__} called without organization_id. "
                    "Organization context will not be set."
                )
                # Execute task without organization context
                return func(*args, **kwargs)
            
            # Execute task with organization context
            try:
                with OrganizationContext.organization_context(organization_id):
                    logger.debug(f"Running task {func.__name__} with organization_id: {organization_id}")
                    return func(*args, **kwargs)
            except Exception as e:
                logger.exception(
                    f"Error in organization_aware_task {func.__name__} "
                    f"with organization_id {organization_id}: {str(e)}"
                )
                raise
        
        return wrapper
    
    return decorator 