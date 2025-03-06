import threading
import logging

logger = logging.getLogger(__name__)

# Thread local storage for organization context
_thread_locals = threading.local()

def get_current_user():
    """
    Get the current user from thread local storage.
    
    Returns:
        User or None: The current user or None if not set
    """
    return getattr(_thread_locals, 'user', None)

def set_current_user(user):
    """
    Set the current user in thread local storage.
    
    Args:
        user (User): The user to set as current
    """
    _thread_locals.user = user

def get_current_organization():
    """
    Get the current organization from thread local storage.
    
    Returns:
        Organization or None: The current organization or None if not set
    """
    return getattr(_thread_locals, 'organization', None)

def set_current_organization(organization):
    """
    Set the current organization in thread local storage.
    
    Args:
        organization (Organization): The organization to set as current
    """
    _thread_locals.organization = organization

def get_user_active_organization(user=None):
    """
    Get active organization ID for the user.
    First checks thread local storage, then falls back to database query.
    
    Args:
        user (User, optional): The user to get the organization for. 
                              If None, uses current user from thread local.
    
    Returns:
        UUID or None: The organization ID or None if not found
    """
    if not user:
        user = get_current_user()
    
    if not user or not user.is_authenticated:
        return None
        
    # Get from thread local if available
    org = get_current_organization()
    if org:
        return org.id
        
    # Otherwise query the database
    try:
        membership = user.organization_memberships.filter(status='active').first()
        return membership.organization.id if membership else None
    except Exception as e:
        logger.error(f"Error getting user's active organization: {e}")
        return None

def clear_organization_context():
    """
    Clear the organization context from thread local storage.
    Call this at the end of a request or when the context is no longer needed.
    """
    if hasattr(_thread_locals, 'user'):
        delattr(_thread_locals, 'user')
    
    if hasattr(_thread_locals, 'organization'):
        delattr(_thread_locals, 'organization') 