import logging
from django.utils import timezone
from apps.seo_manager.models import Client
from channels.db import database_sync_to_async
from apps.agents.utils.client_utils import ClientDataUtils
from apps.organizations.utils import get_current_organization

logger = logging.getLogger(__name__)

class ClientDataManager:
    def __init__(self):
        pass

    @database_sync_to_async
    def get_client_data(self, client_id):
        """Get and format client data using the common utility"""
        if not client_id:
            return {
                'client_id': None,
                'current_date': timezone.now().date().isoformat(),
            }
            
        try:
            # Get organization context from the current request if available
            organization = get_current_organization()
            organization_id = organization.id if organization else None
            
            # Use the common client utility to get client and client data with organization context
            client = ClientDataUtils.get_client_by_id(client_id, organization_id=organization_id)
            if not client:
                logger.warning(f"No client found with ID {client_id}, returning default data")
                return {
                    'client_id': None,
                    'current_date': timezone.now().date().isoformat(),
                }
                
            # Get full client data using the utility with organization context
            return ClientDataUtils.get_client_data(client, organization_id=organization_id)
            
        except Exception as e:
            logger.error(f"Error getting client data: {str(e)}", exc_info=True)
            return {
                'client_id': None,
                'current_date': timezone.now().date().isoformat(),
            } 