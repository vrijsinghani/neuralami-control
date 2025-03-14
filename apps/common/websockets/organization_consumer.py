from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
import json
import logging

# Import OrganizationContext
try:
    from apps.organizations.utils import OrganizationContext
except ImportError:
    OrganizationContext = None
    logging.getLogger(__name__).warning("OrganizationContext not available, organization isolation may not work properly in WebSocket consumers")

logger = logging.getLogger(__name__)

class OrganizationAwareConsumer(AsyncWebsocketConsumer):
    """
    Base WebSocket consumer that sets organization context from session.
    
    This consumer ensures organization isolation is maintained in WebSocket connections
    by setting the organization context from the session when the connection is established.
    """
    
    async def set_organization_context(self):
        """
        Set organization context based on session data.
        
        WebSockets have access to the session via the scope, so we can extract
        the active organization ID from there.
        """
        if not OrganizationContext:
            logger.error("OrganizationContext not available, skipping context setup")
            return False
            
        try:
            # Get session from scope
            session = self.scope.get('session', {})
            logger.debug(f"Session in WebSocket scope: {session}")
            
            # Get organization ID from session
            org_id = session.get('active_organization_id')
            logger.debug(f"Active organization ID from session: {org_id}")
            
            if not org_id:
                logger.warning("No active organization ID in session")
                return False
                
            # Set organization context
            # Import here to avoid circular imports
            from apps.organizations.models import Organization
            
            # Get organization object asynchronously
            organization = await self.get_organization(org_id)
            
            if organization:
                # Set as current organization in context
                OrganizationContext.set_current(organization)
                logger.debug(f"Set organization context to {organization.name} (ID: {organization.id})")
                return True
            else:
                logger.error(f"Organization with ID {org_id} not found")
                return False
                
        except Exception as e:
            logger.error(f"Error setting organization context: {str(e)}", exc_info=True)
            return False
            
    @sync_to_async
    def get_organization(self, org_id):
        """Get organization object synchronously, wrapped in sync_to_async"""
        from apps.organizations.models import Organization
        try:
            return Organization.objects.get(id=org_id)
        except Organization.DoesNotExist:
            return None
            
    async def clear_organization_context(self):
        """Clear organization context when disconnecting"""
        if OrganizationContext:
            from apps.organizations.utils import clear_organization_context
            clear_organization_context()
            
    async def connect(self):
        """
        Set organization context from session.
        
        Note: Child classes should call this with super().connect() 
        at the beginning of their connect method, but should not
        expect any additional functionality like group joining or
        connection acceptance. Those should be implemented in the
        child class.
        """
        # Just set organization context
        await self.set_organization_context()
        # Child classes need to handle their own connection logic
        
    async def disconnect(self, close_code):
        """Disconnect and clear organization context"""
        # Clear organization context
        await self.clear_organization_context()
        
        # Child classes should override and call super().disconnect(close_code)
        pass 