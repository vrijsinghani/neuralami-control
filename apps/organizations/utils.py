import threading
import logging
from contextlib import contextmanager
import contextvars  # Add contextvars import

logger = logging.getLogger(__name__)

# Context variables for organization context (replaces thread local storage)
_user_var = contextvars.ContextVar('user', default=None)
_organization_var = contextvars.ContextVar('organization', default=None)

# Keep thread local storage for backward compatibility during transition
_thread_locals = threading.local()

def get_current_user():
    """
    Get the current user from context variable or thread local storage.
    
    Returns:
        User or None: The current user or None if not set
    """
    # Try contextvars first
    user = _user_var.get()
    if user is not None:
        return user
    
    # Fall back to thread local for backward compatibility
    return getattr(_thread_locals, 'user', None)

def set_current_user(user):
    """
    Set the current user in context variable and thread local storage.
    
    Args:
        user (User): The user to set as current
    """
    # Set in contextvars
    _user_var.set(user)
    
    # Also set in thread local for backward compatibility
    _thread_locals.user = user

def get_current_organization():
    """
    Get the current organization from context variable or thread local storage.
    
    Returns:
        Organization or None: The current organization or None if not set
    """
    # Try contextvars first
    org = _organization_var.get()
    if org is not None:
        return org
    
    # Fall back to thread local for backward compatibility
    return getattr(_thread_locals, 'organization', None)

def set_current_organization(organization):
    """
    Set the current organization in context variable and thread local storage.
    
    Args:
        organization (Organization): The organization to set as current
    """
    # Set in contextvars
    _organization_var.set(organization)
    
    # Also set in thread local for backward compatibility
    _thread_locals.organization = organization

def get_user_active_organization(user=None):
    """
    Get active organization ID for the user.
    First checks context variable, then falls back to database query.
    
    Args:
        user (User, optional): The user to get the organization for. 
                              If None, uses current user from context variable.
    
    Returns:
        UUID or None: The organization ID or None if not found
    """
    if not user:
        user = get_current_user()
    
    if not user or not user.is_authenticated:
        return None
        
    # Get from context variable if available
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
    Clear the organization context from context variables and thread local storage.
    Call this at the end of a request or when the context is no longer needed.
    """
    # Clear contextvars
    _user_var.set(None)
    _organization_var.set(None)
    
    # Also clear thread local for backward compatibility
    if hasattr(_thread_locals, 'user'):
        delattr(_thread_locals, 'user')
    
    if hasattr(_thread_locals, 'organization'):
        delattr(_thread_locals, 'organization')

class OrganizationContext:
    """
    Class for managing organization context.
    Provides methods for getting, setting, and temporarily switching the current organization.
    Works with both synchronous and asynchronous code using ContextVars.
    """
    
    @classmethod
    def get_current(cls, request=None):
        """
        Get organization from multiple possible sources.
        
        Args:
            request (HttpRequest, optional): The current request, if available
            
        Returns:
            Organization or None: The current organization or None if not found
        """
        # Try request first (highest priority)
        if request and hasattr(request, 'organization'):
            return request.organization
               
        # Try context variable storage
        org = get_current_organization()
        if org:
            return org
               
        # Get from current user's membership
        user = get_current_user()
        if user and user.is_authenticated:
            # Get organization ID
            org_id = get_user_active_organization(user)
            if org_id:
                # Convert ID to organization object if needed
                if not isinstance(org_id, (str, int)):
                    return org_id  # Already an organization object
                    
                # Import here to avoid circular imports
                from apps.organizations.models import Organization
                try:
                    return Organization.objects.get(id=org_id)
                except Exception as e:
                    logger.error(f"Error getting organization object: {e}")
                    
        return None
       
    @classmethod
    def set_current(cls, organization, request=None):
        """
        Set organization in all relevant storage mechanisms.
        
        Args:
            organization (Organization): The organization to set as current
            request (HttpRequest, optional): The current request, if available
        """
        # Set in context variable storage
        set_current_organization(organization)
           
        # Set in request if provided
        if request:
            request.organization = organization
       
    @classmethod
    @contextmanager
    def organization_context(cls, organization_id):
        """
        Context manager for temporarily setting organization context.
        Works in both sync and async code thanks to ContextVars.
        
        Args:
            organization_id: The ID of the organization to set as current
            
        Yields:
            Organization: The organization object
        """
        if organization_id is None:
            # Handle null organization_id gracefully
            logger.warning("organization_context called with None organization_id")
            yield None
            return
            
        # Save tokens for restoring context later
        user_token = _user_var.set(_user_var.get())
        org_token = _organization_var.set(_organization_var.get())
        
        try:
            # Import here to avoid circular imports
            from apps.organizations.models import Organization
            
            # Get the organization object
            try:
                organization = Organization.objects.get(id=organization_id)
                # Set as current
                cls.set_current(organization)
                logger.debug(f"Organization context set to: {organization.name} ({organization.id})")
                yield organization
            except Organization.DoesNotExist:
                logger.error(f"Organization with ID {organization_id} not found")
                cls.set_current(None)
                yield None
            except Exception as e:
                logger.error(f"Error in organization_context: {str(e)}", exc_info=True)
                cls.set_current(None)
                yield None
        except Exception as e:
            # Catch all exceptions to ensure context is always restored
            logger.error(f"Unexpected error in organization_context: {str(e)}", exc_info=True)
            cls.set_current(None)
            yield None
        finally:
            # Restore previous context
            try:
                _user_var.reset(user_token)
                _organization_var.reset(org_token)
                logger.debug("Organization context reset to previous value")
            except Exception as e:
                # Make sure we don't break even if resetting fails
                logger.error(f"Error resetting organization context: {str(e)}", exc_info=True)
                # Clear context as a fallback
                clear_organization_context() 