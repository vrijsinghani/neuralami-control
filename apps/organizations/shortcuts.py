import logging
from django.shortcuts import get_object_or_404 as django_get_object_or_404
from django.core.exceptions import PermissionDenied
from .utils import get_current_organization, get_current_user

logger = logging.getLogger(__name__)

def get_object_or_404(*args, **kwargs):
    """
    Drop-in secure replacement for Django's get_object_or_404 that enforces
    organization-based access control automatically.
    
    Works with both synchronous and asynchronous code via ContextVars.
    
    Args:
        Same arguments as Django's get_object_or_404
        
    Returns:
        The requested object if it exists and belongs to the current organization
        
    Raises:
        Http404: If the object doesn't exist
        PermissionDenied: If the object belongs to a different organization
    """
    # Get the object using Django's function
    obj = django_get_object_or_404(*args, **kwargs)
    
    # Skip security check for superusers
    user = get_current_user()
    if user and user.is_superuser:
        return obj
    
    # If the object has an organization field, verify access
    if hasattr(obj, 'organization_id'):
        current_org = get_current_organization()
        if (current_org and obj.organization_id and 
            str(obj.organization_id) != str(current_org.id)):
                
            logger.warning(
                f"Organization security violation detected in get_object_or_404. "
                f"User: {getattr(user, 'username', 'None')}, "
                f"Object: {obj.__class__.__name__} (ID: {obj.pk}), "
                f"Object organization: {obj.organization_id}, "
                f"User organization: {current_org.id}"
            )
            
            raise PermissionDenied(
                f"You don't have access to this {obj.__class__.__name__}"
            )
    
    return obj

# Async version of the same function
async def aget_object_or_404(*args, **kwargs):
    """
    Async version of get_object_or_404 that enforces organization-based access control.
    This works with async views and contexts.
    
    Args:
        Same arguments as Django's get_object_or_404
        
    Returns:
        The requested object if it exists and belongs to the current organization
        
    Raises:
        Http404: If the object doesn't exist
        PermissionDenied: If the object belongs to a different organization
    """
    # In fully async implementations, this would use a Django async ORM method
    # For now, we're just wrapping the synchronous method
    
    from asgiref.sync import sync_to_async
    
    # Run the synchronous version in a thread
    obj = await sync_to_async(get_object_or_404)(*args, **kwargs)
    return obj

def patch_django_shortcuts():
    """
    Patches Django's shortcuts module to replace get_object_or_404 with our secure version.
    This should be called in AppConfig.ready() to apply globally.
    """
    import django.shortcuts
    django.shortcuts.get_object_or_404 = get_object_or_404
    
    # In Django 4.1+, patch the async version as well
    try:
        if hasattr(django.shortcuts, 'aget_object_or_404'):
            django.shortcuts.aget_object_or_404 = aget_object_or_404
            logger.info("Django shortcuts patched with secure sync and async get_object_or_404")
        else:
            logger.info("Django shortcuts patched with secure get_object_or_404 (async version not available)")
    except Exception as e:
        logger.warning(f"Error patching async shortcuts: {e}")
        logger.info("Django shortcuts patched with secure get_object_or_404 only") 