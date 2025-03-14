import logging
from django.utils import timezone
from apps.seo_manager.models import Client
from django.apps import apps
from channels.db import database_sync_to_async
from apps.organizations.shortcuts import get_object_or_404

# Try to import OrganizationContext, but don't fail if not available
try:
    from apps.organizations.utils import OrganizationContext
except ImportError:
    OrganizationContext = None
    logging.getLogger(__name__).warning("OrganizationContext not available, some multi-tenancy features may be limited")

logger = logging.getLogger(__name__)

class ClientDataUtils:
    """
    Utility class for client data operations.
    Provides consistent access to client data across the application.
    Compatible with both synchronous and asynchronous code via ContextVars.
    """
    
    @staticmethod
    def get_client_data(client, organization_id=None):
        """
        Get formatted client data with analytics credentials.
        
        Args:
            client: A Client model instance
            organization_id: Optional organization ID to override current context
            
        Returns:
            dict: Dictionary containing client data and credentials
        """
        if not client:
            logger.warning("get_client_data called with None client")
            return {
                'client_id': None,
                'current_date': timezone.now().date().isoformat(),
            }
        
        # Format SEO projects into a readable string
        seo_projects_list = []
        for project in client.seo_projects.all().order_by('-implementation_date'):
            project_str = (
                f"Project: {project.title}\n"
                f"Description: {project.description}\n"
                f"Status: {project.status}\n"
                f"Implementation Date: {project.implementation_date.isoformat() if project.implementation_date else 'Not set'}\n"
                f"Completion Date: {project.completion_date.isoformat() if project.completion_date else 'Not set'}"
            )
            seo_projects_list.append(project_str)
        
        seo_projects_str = "\n\n".join(seo_projects_list) if seo_projects_list else ""
        
        client_data = {
            'client_id': client.id,
            'client_name': client.name,
            'client_website_url': client.website_url,
            'client_business_objectives': '\n'.join(str(obj) for obj in client.business_objectives) if client.business_objectives else '',
            'client_target_audience': client.target_audience,
            'client_profile': client.client_profile,
            'client_seo_projects': seo_projects_str,
            'current_date': timezone.now().date().isoformat(),
        }
        
        # Add Google Analytics credentials if available
        try:
            if hasattr(client, 'ga_credentials') and client.ga_credentials:
                ga_creds = client.ga_credentials
                
                # Try to get property_id using get_property_id() method if available
                if hasattr(ga_creds, 'get_property_id') and callable(getattr(ga_creds, 'get_property_id')):
                    try:
                        property_id = ga_creds.get_property_id()
                        client_data['analytics_property_id'] = str(property_id) if property_id is not None else ''
                        logger.debug(f"Got property_id '{property_id}' using get_property_id() method")
                    except Exception as e:
                        logger.warning(f"Failed to get property_id using get_property_id() method: {e}")
                        client_data['analytics_property_id'] = ''
                else:
                    # Fallback to direct attribute access
                    client_data['analytics_property_id'] = getattr(ga_creds, 'property_id', '')
                    
                    # Fallback to view_id for older GA3 structure
                    if not client_data['analytics_property_id'] and hasattr(ga_creds, 'view_id'):
                        client_data['analytics_property_id'] = getattr(ga_creds, 'view_id', '')
                        logger.debug(f"Using view_id as fallback for property_id")
                
                # Create actual credentials dictionary with real values
                client_data['analytics_credentials'] = {
                    'ga_client_id': getattr(ga_creds, 'ga_client_id', ''),
                    'client_secret': getattr(ga_creds, 'client_secret', ''), 
                    'refresh_token': getattr(ga_creds, 'refresh_token', ''),
                    'token_uri': getattr(ga_creds, 'token_uri', 'https://oauth2.googleapis.com/token'),
                    'access_token': getattr(ga_creds, 'access_token', '')
                }
                
                # Log safely without exposing sensitive data
                logger.debug(f"Added Google Analytics credentials for client {client.name} (ID: {client.id})")
                
                # Add warning for missing critical fields
                missing_fields = []
                for field in ['ga_client_id', 'client_secret', 'refresh_token']:
                    if not getattr(ga_creds, field, ''):
                        missing_fields.append(field)
                
                if missing_fields:
                    logger.warning(f"Missing critical Analytics credential fields for client {client.name}: {', '.join(missing_fields)}")
            else:
                logger.debug(f"Client {client.name} (ID: {client.id}) has no Google Analytics credentials")
        except Exception as e:
            logger.error(f"Error adding Google Analytics credentials for client {client.name}: {str(e)}")
        
        # Add Search Console credentials if available
        try:
            if hasattr(client, 'sc_credentials') and client.sc_credentials:
                sc_creds = client.sc_credentials
                
                # Use the get_property_url method properly
                try:
                    if hasattr(sc_creds, 'get_property_url') and callable(getattr(sc_creds, 'get_property_url')):
                        property_url = sc_creds.get_property_url()
                        client_data['search_console_property_url'] = property_url if property_url else ''
                        logger.debug(f"Got property_url using get_property_url() method")
                    else:
                        # Fallback to direct attribute access
                        property_url = getattr(sc_creds, 'property_url', '') or getattr(sc_creds, 'property_id', '')
                        client_data['search_console_property_url'] = property_url
                except Exception as e:
                    logger.error(f"Error calling get_property_url: {str(e)}")
                    # Fallback to direct attribute access
                    property_url = getattr(sc_creds, 'property_url', '') or getattr(sc_creds, 'property_id', '')
                    client_data['search_console_property_url'] = property_url
                
                if not property_url:
                    logger.warning(f"Client {client.name} has Search Console credentials but no valid property URL")
                
                # Create actual credentials dictionary with real values
                client_data['search_console_credentials'] = {
                    'sc_client_id': getattr(sc_creds, 'sc_client_id', ''),
                    'client_secret': getattr(sc_creds, 'client_secret', ''),
                    'refresh_token': getattr(sc_creds, 'refresh_token', ''),
                    'token_uri': getattr(sc_creds, 'token_uri', 'https://oauth2.googleapis.com/token'),
                    'access_token': getattr(sc_creds, 'access_token', '')
                }
                
                # Log safely without exposing sensitive data
                logger.debug(f"Added Search Console credentials for client {client.name} (ID: {client.id})")
                
                # Add warning for missing critical fields
                missing_fields = []
                for field in ['sc_client_id', 'client_secret', 'refresh_token']:
                    if not getattr(sc_creds, field, ''):
                        missing_fields.append(field)
                
                if missing_fields:
                    logger.warning(f"Missing critical Search Console credential fields for client {client.name}: {', '.join(missing_fields)}")
            else:
                logger.debug(f"Client {client.name} (ID: {client.id}) has no Search Console credentials")
        except Exception as e:
            logger.error(f"Error adding Search Console credentials for client {client.name}: {str(e)}")
        
        # Log the available keys for debugging
        logger.debug(f"Client data keys available: {', '.join(client_data.keys())}")
        
        return client_data
    
    @staticmethod
    def get_client_by_id(client_id, organization_id=None):
        """
        Get a client by ID with organization-aware error handling.
        Works with both synchronous and asynchronous code via ContextVars.
        
        Args:
            client_id: The ID of the client to retrieve
            organization_id: Optional organization ID to override current context
            
        Returns:
            Client: The client object or None if not found
        """
        if not client_id:
            logger.warning("get_client_by_id called with None client_id")
            return None
            
        try:
            # If organization_id is provided, use it to set context temporarily
            if organization_id:
                # Check if OrganizationContext is available
                if OrganizationContext:
                    with OrganizationContext.organization_context(organization_id):
                        # Use the secure get_object_or_404 that enforces organization boundaries
                        return get_object_or_404(Client, id=client_id)
                else:
                    # Fall back to direct filter
                    logger.warning("OrganizationContext not available, using direct filter")
                    return get_object_or_404(Client, id=client_id, organization_id=organization_id)
            else:
                # Use secure get_object_or_404 with the current organization context
                return get_object_or_404(Client, id=client_id)
                
        except Exception as e:
            logger.error(f"Error retrieving client with ID {client_id}: {str(e)}")
            return None
    
    @staticmethod
    @database_sync_to_async
    def get_client_data_async(client_id, organization_id=None):
        """
        Async version of get_client_data that first retrieves the client by ID.
        Uses ContextVars for organization context, making it work properly in async code.
        
        Args:
            client_id: The ID of the client to retrieve data for
            organization_id: Optional organization ID to override current context
            
        Returns:
            dict: Dictionary containing client data and credentials
        """
        try:
            # Get client with proper organization context
            client = ClientDataUtils.get_client_by_id(client_id, organization_id)
            return ClientDataUtils.get_client_data(client, organization_id)
        except Exception as e:
            logger.error(f"Error in get_client_data_async: {str(e)}", exc_info=True)
            return {
                'client_id': None,
                'current_date': timezone.now().date().isoformat(),
            } 