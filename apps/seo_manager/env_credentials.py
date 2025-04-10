"""
Module for creating Google OAuth credentials from environment variables.
This allows for more secure credential management without storing sensitive
information in files.
"""

import os
import json
import logging
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import Flow

logger = logging.getLogger(__name__)

def get_oauth_flow_from_env(redirect_uri, scopes, state=None):
    """
    Create an OAuth flow using environment variables instead of a client secrets file.
    
    Args:
        redirect_uri: The redirect URI for the OAuth flow
        scopes: List of scopes to request
        state: Optional state parameter
        
    Returns:
        Flow object configured with client credentials from environment variables
    """
    try:
        # Get client credentials from environment variables
        client_id = os.environ.get('GOOGLE_OAUTH_CLIENT_ID')
        client_secret = os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET')
        auth_uri = os.environ.get('GOOGLE_OAUTH_AUTH_URI', 'https://accounts.google.com/o/oauth2/auth')
        token_uri = os.environ.get('GOOGLE_OAUTH_TOKEN_URI', 'https://oauth2.googleapis.com/token')
        
        if not client_id or not client_secret:
            logger.error("Missing required environment variables for OAuth flow")
            raise ValueError("GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET must be set")
        
        # Create client config dictionary (same structure as client_secrets.json)
        client_config = {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": auth_uri,
                "token_uri": token_uri,
                "redirect_uris": [redirect_uri]
            }
        }
        
        # Create flow from client config
        flow = Flow.from_client_config(
            client_config,
            scopes=scopes,
            state=state,
            redirect_uri=redirect_uri
        )
        
        return flow
        
    except Exception as e:
        logger.error(f"Error creating OAuth flow from environment variables: {str(e)}")
        raise

def get_service_account_credentials_from_env(scopes):
    """
    Create service account credentials from environment variables.
    
    Args:
        scopes: List of scopes to request
        
    Returns:
        Service account credentials object
    """
    try:
        # Get service account info from environment variables
        project_id = os.environ.get('GOOGLE_SA_PROJECT_ID')
        private_key_id = os.environ.get('GOOGLE_SA_PRIVATE_KEY_ID')
        private_key = os.environ.get('GOOGLE_SA_PRIVATE_KEY', '').replace('\\n', '\n')  # Replace escaped newlines
        client_email = os.environ.get('GOOGLE_SA_CLIENT_EMAIL')
        client_id = os.environ.get('GOOGLE_SA_CLIENT_ID')
        
        if not all([project_id, private_key_id, private_key, client_email, client_id]):
            logger.error("Missing required environment variables for service account credentials")
            raise ValueError("One or more required service account environment variables are not set")
        
        # Create service account info dictionary (same structure as service-account.json)
        service_account_info = {
            "type": "service_account",
            "project_id": project_id,
            "private_key_id": private_key_id,
            "private_key": private_key,
            "client_email": client_email,
            "client_id": client_id,
            "auth_uri": os.environ.get('GOOGLE_SA_AUTH_URI', 'https://accounts.google.com/o/oauth2/auth'),
            "token_uri": os.environ.get('GOOGLE_SA_TOKEN_URI', 'https://oauth2.googleapis.com/token'),
            "auth_provider_x509_cert_url": os.environ.get(
                'GOOGLE_SA_AUTH_PROVIDER_CERT_URL', 
                'https://www.googleapis.com/oauth2/v1/certs'
            ),
            "client_x509_cert_url": os.environ.get('GOOGLE_SA_CLIENT_CERT_URL', '')
        }
        
        # Create credentials from service account info
        credentials = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=scopes
        )
        
        return credentials
        
    except Exception as e:
        logger.error(f"Error creating service account credentials from environment variables: {str(e)}")
        raise

def get_oauth_credentials_from_env(scopes):
    """
    Create OAuth credentials from environment variables.
    
    Args:
        scopes: List of scopes for the credentials
        
    Returns:
        OAuth credentials object
    """
    try:
        # Get OAuth credentials from environment variables
        token = os.environ.get('GOOGLE_OAUTH_TOKEN')
        refresh_token = os.environ.get('GOOGLE_OAUTH_REFRESH_TOKEN')
        client_id = os.environ.get('GOOGLE_OAUTH_CLIENT_ID')
        client_secret = os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET')
        token_uri = os.environ.get('GOOGLE_OAUTH_TOKEN_URI', 'https://oauth2.googleapis.com/token')
        
        if not all([token, refresh_token, client_id, client_secret]):
            logger.error("Missing required environment variables for OAuth credentials")
            raise ValueError("One or more required OAuth credential environment variables are not set")
        
        # Create credentials
        credentials = Credentials(
            token=token,
            refresh_token=refresh_token,
            token_uri=token_uri,
            client_id=client_id,
            client_secret=client_secret,
            scopes=scopes
        )
        
        return credentials
        
    except Exception as e:
        logger.error(f"Error creating OAuth credentials from environment variables: {str(e)}")
        raise
