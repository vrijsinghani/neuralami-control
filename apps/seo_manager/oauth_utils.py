"""
Centralized OAuth utilities for Google services.

This module provides a single entry point for all OAuth-related operations,
including creating OAuth flows, handling credentials, and managing scopes.
"""

import logging
import os
from typing import Dict, List, Optional, Union, Any

from django.conf import settings
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Import the OAuthManager for scope definitions
from apps.seo_manager.models import OAuthManager
from apps.seo_manager.env_credentials import (
    get_oauth_flow_from_env,
    get_service_account_credentials_from_env,
    get_oauth_credentials_from_env
)

logger = logging.getLogger(__name__)

def get_credentials(
    credentials_dict: Dict[str, Any],
    service_type: str = 'ga'
) -> Credentials:
    """
    Create Google OAuth credentials from a dictionary.
    
    Args:
        credentials_dict: Dictionary containing credential information
        service_type: Type of service ('ga', 'sc', 'ads')
        
    Returns:
        Google OAuth credentials object
    """
    # Determine the appropriate scopes based on service type
    scopes = []
    if service_type == 'ga':
        scopes = [
            OAuthManager.OAUTH_SCOPES['analytics']['readonly'],
            OAuthManager.OAUTH_SCOPES['analytics']['full'],  # Include full access for future editing
            OAuthManager.OAUTH_SCOPES['common']['email']
        ]
    elif service_type == 'sc':
        scopes = [
            OAuthManager.OAUTH_SCOPES['search_console']['readonly'],
            OAuthManager.OAUTH_SCOPES['common']['email']
        ]
    elif service_type == 'ads':
        scopes = [
            OAuthManager.OAUTH_SCOPES['adwords']['full'],
            OAuthManager.OAUTH_SCOPES['common']['email']
        ]
    else:
        # Default to all scopes
        scopes = [
            OAuthManager.OAUTH_SCOPES['analytics']['readonly'],
            OAuthManager.OAUTH_SCOPES['analytics']['full'],
            OAuthManager.OAUTH_SCOPES['search_console']['readonly'],
            OAuthManager.OAUTH_SCOPES['adwords']['full'],
            OAuthManager.OAUTH_SCOPES['common']['openid'],
            OAuthManager.OAUTH_SCOPES['common']['email'],
            OAuthManager.OAUTH_SCOPES['common']['profile']
        ]
    
    # Check if we should use environment variables
    use_env = getattr(settings, 'GOOGLE_OAUTH_USE_ENV', False)
    
    if use_env and not all([
        credentials_dict.get('refresh_token'),
        credentials_dict.get('token_uri', 'https://oauth2.googleapis.com/token'),
        credentials_dict.get('ga_client_id') or credentials_dict.get('sc_client_id') or credentials_dict.get('ads_client_id'),
        credentials_dict.get('client_secret')
    ]):
        # Use environment variables for credentials
        return get_oauth_credentials_from_env(scopes=scopes)
    
    # Use the provided credentials dictionary
    client_id_key = 'ga_client_id'
    if service_type == 'sc':
        client_id_key = 'sc_client_id'
    elif service_type == 'ads':
        client_id_key = 'ads_client_id'
    
    # Create credentials object
    credentials = Credentials(
        token=credentials_dict.get('access_token'),
        refresh_token=credentials_dict.get('refresh_token'),
        token_uri=credentials_dict.get('token_uri', 'https://oauth2.googleapis.com/token'),
        client_id=credentials_dict.get(client_id_key),
        client_secret=credentials_dict.get('client_secret'),
        scopes=credentials_dict.get('scopes', scopes)
    )
    
    # Try to refresh the token if we have a refresh token
    if credentials.refresh_token:
        try:
            logger.debug("Attempting to refresh credentials token")
            request = Request()
            credentials.refresh(request)
            logger.debug("Successfully refreshed credentials token")
        except Exception as e:
            logger.error(f"Failed to refresh token: {str(e)}")
            if 'invalid_grant' in str(e).lower():
                raise ValueError("Google credentials have expired. Please reconnect your Google account.")
    
    return credentials

def get_service_account_credentials(
    service_account_json: str,
    service_type: str = 'ga'
) -> service_account.Credentials:
    """
    Create service account credentials from JSON.
    
    Args:
        service_account_json: JSON string containing service account info
        service_type: Type of service ('ga', 'sc', 'ads')
        
    Returns:
        Service account credentials object
    """
    # Determine the appropriate scopes based on service type
    scopes = []
    if service_type == 'ga':
        scopes = [
            OAuthManager.OAUTH_SCOPES['analytics']['readonly'],
            OAuthManager.OAUTH_SCOPES['analytics']['full']  # Include full access for future editing
        ]
    elif service_type == 'sc':
        scopes = [OAuthManager.OAUTH_SCOPES['search_console']['readonly']]
    elif service_type == 'ads':
        scopes = [OAuthManager.OAUTH_SCOPES['adwords']['full']]
    
    # Check if we should use environment variables
    use_env = getattr(settings, 'GOOGLE_OAUTH_USE_ENV', False)
    
    if use_env and not service_account_json:
        # Use environment variables for service account
        return get_service_account_credentials_from_env(scopes=scopes)
    
    # Use the provided service account JSON
    import json
    service_account_info = json.loads(service_account_json)
    return service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=scopes
    )

def get_analytics_service(credentials: Credentials):
    """
    Create a Google Analytics service using the provided credentials.
    
    Args:
        credentials: Google OAuth credentials
        
    Returns:
        Google Analytics service
    """
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    return BetaAnalyticsDataClient(credentials=credentials)

def get_search_console_service(credentials: Credentials):
    """
    Create a Google Search Console service using the provided credentials.
    
    Args:
        credentials: Google OAuth credentials
        
    Returns:
        Google Search Console service
    """
    return build('searchconsole', 'v1', credentials=credentials)

def get_ads_service(credentials: Credentials):
    """
    Create a Google Ads service using the provided credentials.
    
    Args:
        credentials: Google OAuth credentials
        
    Returns:
        Google Ads service
    """
    from google.ads.googleads.client import GoogleAdsClient
    
    # The google-ads client library expects a dictionary
    credentials_dict = {
        "developer_token": settings.GOOGLE_ADS_DEVELOPER_TOKEN,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "refresh_token": credentials.refresh_token,
        "use_proto_plus": True
    }
    
    return GoogleAdsClient.load_from_dict(credentials_dict)
