#!/usr/bin/env python
"""
Test script for verifying the centralized OAuth implementation.

This script tests the OAuth flow with both analytics.readonly and analytics (full) scopes.
It can be run as a Django management command:

python manage.py shell < scripts/test_oauth_reauthorization.py
"""

import logging
import os
from django.test.client import RequestFactory
from django.conf import settings
from apps.seo_manager.models import OAuthManager, Client
from apps.seo_manager.oauth_utils import get_credentials, get_analytics_service, get_search_console_service

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_oauth_flow():
    """Test the OAuth flow with both analytics scopes"""
    # Create a mock request
    factory = RequestFactory()
    
    # Get APP_DOMAIN from environment variables
    app_domain = os.environ.get('APP_DOMAIN', '').split(',')[0]
    valid_host = app_domain if app_domain else 'localhost'
    logger.info(f"Using host: {valid_host}")
    
    # Create the request with the valid host
    request = factory.get('/', HTTP_HOST=valid_host)
    
    # Add session to request
    def add_session_to_request(request):
        from django.contrib.sessions.middleware import SessionMiddleware
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()
        
    add_session_to_request(request)
    
    # Test flow creation for different service types
    for service_type in ['ga', 'sc', 'ads', None]:
        try:
            # Create flow
            flow = OAuthManager.create_oauth_flow(request, service_type=service_type)
            
            # Get the scopes from the flow
            scopes = flow.oauth2session.scope
            
            logger.info(f"=== OAuth Flow Test for {service_type or 'all services'} ===")
            logger.info(f"Scopes requested: {scopes}")
            
            # Check if analytics scopes are included for GA
            if service_type == 'ga' or service_type is None:
                readonly_scope = OAuthManager.OAUTH_SCOPES['analytics']['readonly']
                full_scope = OAuthManager.OAUTH_SCOPES['analytics']['full']
                
                if readonly_scope in scopes and full_scope in scopes:
                    logger.info("SUCCESS: Both analytics.readonly and analytics (full) scopes are included.")
                else:
                    logger.error("ERROR: Missing one or both analytics scopes.")
                    if readonly_scope not in scopes:
                        logger.error(f"  - Missing: {readonly_scope}")
                    if full_scope not in scopes:
                        logger.error(f"  - Missing: {full_scope}")
            
            # Get the authorization URL
            auth_url, _ = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent'
            )
            
            logger.info(f"Authorization URL: {auth_url[:100]}...")
            
        except Exception as e:
            logger.error(f"Error testing OAuth flow for {service_type}: {str(e)}")

def test_environment_variable_support():
    """Test environment variable support for OAuth credentials"""
    logger.info("\n=== Environment Variable Support Test ===")
    use_env = getattr(settings, 'GOOGLE_OAUTH_USE_ENV', False)
    if use_env:
        logger.info("Environment variable mode is ENABLED.")
        
        # Check if required environment variables are set
        client_id = getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', None)
        client_secret = getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', None)
        
        if client_id and client_secret:
            logger.info("Required OAuth client environment variables are set.")
        else:
            logger.warning("WARNING: Some required OAuth client environment variables are missing:")
            if not client_id:
                logger.warning("  - GOOGLE_OAUTH_CLIENT_ID is not set")
            if not client_secret:
                logger.warning("  - GOOGLE_OAUTH_CLIENT_SECRET is not set")
        
        # Check service account environment variables
        sa_project_id = getattr(settings, 'GOOGLE_SA_PROJECT_ID', None)
        sa_private_key = getattr(settings, 'GOOGLE_SA_PRIVATE_KEY', None)
        sa_client_email = getattr(settings, 'GOOGLE_SA_CLIENT_EMAIL', None)
        
        if sa_project_id and sa_private_key and sa_client_email:
            logger.info("Required service account environment variables are set.")
        else:
            logger.warning("WARNING: Some required service account environment variables are missing:")
            if not sa_project_id:
                logger.warning("  - GOOGLE_SA_PROJECT_ID is not set")
            if not sa_private_key:
                logger.warning("  - GOOGLE_SA_PRIVATE_KEY is not set")
            if not sa_client_email:
                logger.warning("  - GOOGLE_SA_CLIENT_EMAIL is not set")
    else:
        logger.info("Environment variable mode is DISABLED.")
        logger.info("The application is using JSON files for credentials.")
        
        # Check if the JSON files exist
        client_secrets_file = getattr(settings, 'GOOGLE_CLIENT_SECRETS_FILE', None)
        service_account_file = getattr(settings, 'SERVICE_ACCOUNT_FILE', None)
        
        if client_secrets_file:
            try:
                import json
                with open(client_secrets_file, 'r') as f:
                    json.load(f)
                logger.info(f"Client secrets file exists and is valid JSON: {client_secrets_file}")
            except FileNotFoundError:
                logger.warning(f"WARNING: Client secrets file not found: {client_secrets_file}")
            except json.JSONDecodeError:
                logger.warning(f"WARNING: Client secrets file is not valid JSON: {client_secrets_file}")
        else:
            logger.warning("WARNING: GOOGLE_CLIENT_SECRETS_FILE setting is not defined")
        
        if service_account_file:
            try:
                import json
                with open(service_account_file, 'r') as f:
                    json.load(f)
                logger.info(f"Service account file exists and is valid JSON: {service_account_file}")
            except FileNotFoundError:
                logger.warning(f"WARNING: Service account file not found: {service_account_file}")
            except json.JSONDecodeError:
                logger.warning(f"WARNING: Service account file is not valid JSON: {service_account_file}")
        else:
            logger.warning("WARNING: SERVICE_ACCOUNT_FILE setting is not defined")

def test_client_credentials():
    """Test client credentials if available"""
    logger.info("\n=== Client Credentials Test ===")
    
    # Get all clients with GA credentials
    clients_with_ga = Client.objects.filter(googleanalyticscredentials__isnull=False)
    if clients_with_ga.exists():
        logger.info(f"Found {clients_with_ga.count()} clients with Google Analytics credentials")
        
        # Test the first client's credentials
        client = clients_with_ga.first()
        try:
            ga_credentials = client.googleanalyticscredentials
            logger.info(f"Testing GA credentials for client: {client.name}")
            
            # Create a credentials dictionary
            credentials_dict = {
                'access_token': ga_credentials.access_token,
                'refresh_token': ga_credentials.refresh_token,
                'token_uri': ga_credentials.token_uri,
                'ga_client_id': ga_credentials.ga_client_id,
                'client_secret': ga_credentials.client_secret,
                'scopes': ga_credentials.scopes
            }
            
            # Use the centralized utility to create credentials
            credentials = get_credentials(credentials_dict, service_type='ga')
            logger.info("Successfully created credentials using centralized utility")
            
            # Try to create an analytics service
            service = get_analytics_service(credentials)
            logger.info("Successfully created analytics service using centralized utility")
            
        except Exception as e:
            logger.error(f"Error testing GA credentials: {str(e)}")
    else:
        logger.info("No clients with Google Analytics credentials found")
    
    # Get all clients with SC credentials
    clients_with_sc = Client.objects.filter(searchconsolecredentials__isnull=False)
    if clients_with_sc.exists():
        logger.info(f"Found {clients_with_sc.count()} clients with Search Console credentials")
        
        # Test the first client's credentials
        client = clients_with_sc.first()
        try:
            sc_credentials = client.searchconsolecredentials
            logger.info(f"Testing SC credentials for client: {client.name}")
            
            # Create a credentials dictionary
            credentials_dict = {
                'access_token': sc_credentials.access_token,
                'refresh_token': sc_credentials.refresh_token,
                'token_uri': sc_credentials.token_uri,
                'sc_client_id': sc_credentials.sc_client_id,
                'client_secret': sc_credentials.client_secret,
                'scopes': sc_credentials.scopes
            }
            
            # Use the centralized utility to create credentials
            credentials = get_credentials(credentials_dict, service_type='sc')
            logger.info("Successfully created credentials using centralized utility")
            
            # Try to create a search console service
            service = get_search_console_service(credentials)
            logger.info("Successfully created search console service using centralized utility")
            
        except Exception as e:
            logger.error(f"Error testing SC credentials: {str(e)}")
    else:
        logger.info("No clients with Search Console credentials found")

def main():
    """Run all tests"""
    logger.info("=== Starting OAuth Implementation Tests ===")
    
    # Test OAuth flow
    test_oauth_flow()
    
    # Test environment variable support
    test_environment_variable_support()
    
    # Test client credentials
    test_client_credentials()
    
    logger.info("\n=== Test Complete ===")
    logger.info("If you see any warnings above, please address them before proceeding.")
    logger.info("If all tests passed, your OAuth configuration is correctly set up.")
    logger.info("\nTo reauthorize credentials, go to the client integrations page and reconnect your Google accounts.")

if __name__ == "__main__":
    main()
