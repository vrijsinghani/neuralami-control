import logging
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import resolve, reverse
from .utils import set_current_user, set_current_organization, clear_organization_context, get_current_organization
from .models.base import Organization

logger = logging.getLogger(__name__)

class OrganizationMiddleware:
    """
    Middleware that stores the current user and their active organization
    in context variables for access throughout the request lifecycle.
    
    Using ContextVars instead of thread-local storage enables this middleware
    to work properly in both synchronous and asynchronous contexts.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        # Clear organization context at the start of each request
        clear_organization_context()
        
        if request.user.is_authenticated:
            # Set the current user
            set_current_user(request.user)
            
            # Try to get the active organization from session
            active_org_id = request.session.get('active_organization_id')
            
            if active_org_id:
                # Verify user membership in this organization
                try:
                    membership = request.user.organization_memberships.filter(
                        organization_id=active_org_id, 
                        status='active'
                    ).select_related('organization').first()
                    
                    if membership:
                        set_current_organization(membership.organization)
                except Exception as e:
                    logger.error(f"Error setting organization context from session: {e}")
            
            # If no organization set from session, fall back to first active membership
            if not get_current_organization():
                try:
                    membership = request.user.organization_memberships.filter(
                        status='active'
                    ).select_related('organization').first()
                    
                    if membership:
                        set_current_organization(membership.organization)
                        
                        # Store in session for future requests
                        request.session['active_organization_id'] = str(membership.organization.id)
                        request.session['active_organization_name'] = membership.organization.name
                except Exception as e:
                    logger.error(f"Error setting organization context: {e}")
            
            # Log the final organization context before assigning to request
            final_org = get_current_organization()
            request.organization = final_org # Assign to request
            
            # Check if organization is inactive and restrict certain operations
            current_org = get_current_organization()
            if current_org and not current_org.is_active and request.method == 'POST':
                # Get the current view name
                resolver_match = resolve(request.path)
                view_name = resolver_match.view_name if resolver_match else ''
                
                # List of allowed POST views for inactive organizations
                allowed_views = [  
                    'organizations:toggle_status',
                    'organizations:switch_organization',
                    'logout', 
                    'password_change'
                ]
                
                # If the view is not in allowed views, restrict it
                if view_name not in allowed_views and not request.user.is_superuser:
                    messages.error(
                        request, 
                        f"This organization is currently inactive. Contact the organization owner or an administrator."
                    )
                    # Determine redirect URL based on the current path
                    if 'organizations/settings' in request.path:
                        return redirect('organizations:settings')
                    else:
                        return redirect('dashboard')
        
        # Process the request
        response = self.get_response(request)
        
        # Clean up at the end of the request
        clear_organization_context()
        
        return response

# For ASGI applications, an async middleware version is also needed
class OrganizationMiddlewareAsync:
    """
    Async version of the OrganizationMiddleware for ASGI applications.
    This is used when the application is running in an async context.
    """
    def __init__(self, inner):
        self.inner = inner
        
    async def __call__(self, scope, receive, send):
        # Process only if this is a http or websocket scope
        if scope["type"] not in ["http", "websocket"]:
            return await self.inner(scope, receive, send)
            
        # Clear organization context at the start
        clear_organization_context()
        
        # Check if user is authenticated
        if "user" in scope and scope["user"].is_authenticated:
            user = scope["user"]
            # Set the current user
            set_current_user(user)
            
            # Try to get the active organization for this user
            try:
                # First try to get from session 
                session = scope.get("session", {})
                active_org_id = session.get('active_organization_id')
                
                if active_org_id:
                    membership = await self._get_membership_by_org_id(user, active_org_id)
                    if membership:
                        set_current_organization(membership.organization)
            except Exception as e:
                logger.error(f"Error setting organization context for {scope['type']}: {e}")
            
        # Call the inner application, maintaining the organization context
        try:
            return await self.inner(scope, receive, send)
        finally:
            # Clean up organization context when done
            clear_organization_context()

    async def _get_membership_by_org_id(self, user, org_id):
        """Helper method to get membership asynchronously - actual implementation would use database_sync_to_async"""
        from django.db.models.query import QuerySet
        from asgiref.sync import sync_to_async
        
        get_membership = sync_to_async(lambda: user.organization_memberships.filter(
            organization_id=org_id, 
            status='active'
        ).select_related('organization').first())
        
        return await get_membership()
        
    async def _get_first_active_membership(self, user):
        """Helper method to get first active membership asynchronously"""
        from asgiref.sync import sync_to_async
        
        get_membership = sync_to_async(lambda: user.organization_memberships.filter(
            status='active'
        ).select_related('organization').first())
        
        return await get_membership()


class OrganizationSecurityMiddleware:
    """
    Middleware that automatically intercepts responses and checks if
    there's any unauthorized cross-organization access.
    
    This acts as a safety net to prevent data leakage between organizations
    even if developers forget to add explicit checks.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        # Process request normally
        response = self.get_response(request)
        
        # Skip for anonymous users, superusers, or non-HTML responses
        if not request.user.is_authenticated or request.user.is_superuser:
            return response
            
        # Skip admin, static, media, and API requests
        skip_paths = ['/admin/', '/static/', '/media/', '/api/']
        if any(request.path.startswith(path) for path in skip_paths):
            return response
            
        # Only process TemplateResponse objects that have context_data
        if hasattr(response, 'context_data') and response.context_data:
            try:
                self._validate_context_objects(request, response.context_data)
            except PermissionDenied as e:
                logger.warning(
                    f"Organization security violation detected: {str(e)}. "
                    f"User: {request.user.username}, Path: {request.path}, "
                    f"Organization: {getattr(get_current_organization(), 'name', 'None')}"
                )
                # Re-raise the exception to be handled by Django's exception middleware
                raise
            
        return response
        
    def _validate_context_objects(self, request, context):
        """Validate all objects in the template context for organization isolation."""
        from django.db.models import Model
        from django.db.models.query import QuerySet
        
        current_org = get_current_organization()
        if not current_org:
            return
            
        # Check all context items that might be model instances or querysets
        for key, value in context.items():
            # Skip non-data items
            if key.startswith('_') or callable(value) or isinstance(value, (str, int, bool, float)):
                continue
                
            # Check single model instances
            if isinstance(value, Model) and hasattr(value, 'organization_id'):
                if value.organization_id and str(value.organization_id) != str(current_org.id):
                    raise PermissionDenied(
                        f"Unauthorized access to {value.__class__.__name__} ({key}) "
                        f"from organization {value.organization_id} (user's organization: {current_org.id})"
                    )
                    
            # Check querysets
            elif isinstance(value, QuerySet) and hasattr(value.model, 'organization'):
                # We'll just check the first few items as a sample - checking all could be expensive
                for item in value[:10]:
                    if hasattr(item, 'organization_id'):
                        if item.organization_id and str(item.organization_id) != str(current_org.id):
                            raise PermissionDenied(
                                f"Unauthorized access to {item.__class__.__name__} in {key} "
                                f"from organization {item.organization_id} (user's organization: {current_org.id})"
                            )
            
            # Check lists and other iterables
            elif hasattr(value, '__iter__') and not isinstance(value, (str, bytes, dict)):
                for item in value:
                    if isinstance(item, Model) and hasattr(item, 'organization_id'):
                        if item.organization_id and str(item.organization_id) != str(current_org.id):
                            raise PermissionDenied(
                                f"Unauthorized access to {item.__class__.__name__} in {key} list "
                                f"from organization {item.organization_id} (user's organization: {current_org.id})"
                            ) 


# Async version of the security middleware
class OrganizationSecurityMiddlewareAsync:
    """
    Async version of the OrganizationSecurityMiddleware for ASGI applications.
    """
    def __init__(self, inner):
        self.inner = inner
        
    async def __call__(self, scope, receive, send):
        # Skip non-http scopes
        if scope["type"] != "http":
            return await self.inner(scope, receive, send)
            
        # Skip for anonymous users, superusers
        if not scope["user"].is_authenticated or scope["user"].is_superuser:
            return await self.inner(scope, receive, send)
            
        # Skip admin, static, media, and API requests
        skip_paths = ['/admin/', '/static/', '/media/', '/api/']
        if any(scope["path"].startswith(path) for path in skip_paths):
            return await self.inner(scope, receive, send)

        # We can't inspect/validate template context in ASGI middleware
        # This would need to be done in an actual view or template processor
        # The security check must happen in sync context

        return await self.inner(scope, receive, send)