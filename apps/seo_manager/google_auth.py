from google_auth_oauthlib.flow import Flow
from django.conf import settings
from django.urls import reverse
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
import json
import logging

logger = logging.getLogger(__name__)

def get_google_auth_flow(request):
    """
    Creates OAuth2 flow for Google Analytics and Search Console authentication.
    """
    flow = Flow.from_client_secrets_file(
        settings.GOOGLE_CLIENT_SECRETS_FILE,
        scopes=[
            'https://www.googleapis.com/auth/analytics.readonly',  # GA4 scope
            'https://www.googleapis.com/auth/webmasters.readonly',
            'openid',
            'https://www.googleapis.com/auth/userinfo.email',
            'https://www.googleapis.com/auth/userinfo.profile'
        ],
        redirect_uri=request.build_absolute_uri('/google/login/callback/')
    )
    return flow

def get_analytics_accounts_oauth(credentials):
    """Get GA4 accounts using OAuth credentials"""
    try:
        # Create the Analytics Admin API client
        analytics = build('analyticsadmin', 'v1beta', credentials=credentials)
        
        try:
            # First get accounts
            accounts_request = analytics.accounts().list().execute()
            accounts = []
            
            # For each account, get its properties
            for account in accounts_request.get('accounts', []):
                account_id = account['name']  # Format: "accounts/1234567"
                account_name = account.get('displayName', 'Unknown Account')
                #logger.info(f"Fetching properties for account: {account_name}")
                
                try:
                    # Initialize pagination variables
                    page_token = None
                    page_num = 1
                    properties_count = 0
                    
                    while True:
                        # List properties for this account with pagination
                        request_params = {
                            'filter': f'parent:{account_id}',
                            'pageSize': 200  # Maximum allowed page size
                        }
                        if page_token:
                            request_params['pageToken'] = page_token
                            
                        properties_request = analytics.properties().list(**request_params).execute()
                        
                        for property in properties_request.get('properties', []):
                            property_id = property['name']
                            property_name = property.get('displayName', 'Unknown Property')
                            
                            accounts.append({
                                'property_id': property_id,
                                'property_name': property_name,
                                'account_name': account_name
                            })
                            properties_count += 1
                        
                        # Check if there are more pages
                        page_token = properties_request.get('nextPageToken')
                        if not page_token:
                            break
                            
                        page_num += 1
                    
                    # logger.info(f"Found {properties_count} properties in account: {account_name}")
                        
                except Exception as e:
                    logger.error(f"Error listing properties for account {account_id}: {str(e)}", exc_info=True)
                    continue
            
            logger.info(f"Total GA4 properties found across all accounts: {len(accounts)}")
            return accounts
            
        except Exception as e:
            logger.error(f"Error listing GA4 accounts: {str(e)}", exc_info=True)
            return []
            
    except Exception as e:
        logger.error(f"Error building GA4 service: {str(e)}", exc_info=True)
        return []

def get_analytics_accounts_service_account(service_account_json):
    """Get GA4 properties using service account credentials"""
    try:
        credentials = service_account.Credentials.from_service_account_info(
            json.loads(service_account_json),
            scopes=['https://www.googleapis.com/auth/analytics.readonly']
        )
        analytics = build('analyticsadmin', 'v1beta', credentials=credentials)
        return fetch_analytics_accounts(analytics)
    except Exception as e:
        logger.error(f"Error building GA4 service with service account: {str(e)}")
        return []

def fetch_analytics_accounts(analytics):
    """Fetch GA4 properties using the Analytics Admin API"""
    try:
        # List all GA4 properties accessible to the user
        request = analytics.accounts().list()
        response = request.execute()
        
        accounts = []
        for account in response.get('accounts', []):
            account_id = account['name'].split('/')[-1]  # Format: "accounts/123456"
            account_name = account.get('displayName', 'Unknown Account')
            
            # Get properties for this account using the correct API call
            properties_request = analytics.properties().list(
                filter=f"parent:accounts/{account_id}"  # Changed from parent parameter to filter
            )
            properties_response = properties_request.execute()
            
            for property in properties_response.get('properties', []):
                property_id = property['name'].split('/')[-1]  # Format: "properties/123456"
                accounts.append({
                    'account_id': account_id,
                    'account_name': account_name,
                    'property_id': property_id,
                    'property_name': property.get('displayName', 'Unknown Property')
                })
        
        logger.info(f"Found {len(accounts)} GA4 properties")
        if not accounts:
            logger.warning("No GA4 properties found for this account")
            
        return accounts
        
    except Exception as e:
        logger.error(f"Error fetching GA4 properties: {str(e)}")
        return []

def get_search_console_service(credentials):
    return build('searchconsole', 'v1', credentials=credentials)

def get_search_console_properties(credentials_or_json):
    """Get list of Search Console properties"""
    try:
        if isinstance(credentials_or_json, str):
            service_account_info = json.loads(credentials_or_json)
            credentials = service_account.Credentials.from_service_account_info(
                service_account_info,
                scopes=['https://www.googleapis.com/auth/webmasters.readonly']
            )
        else:
            credentials = credentials_or_json

        service = build('searchconsole', 'v1', credentials=credentials)
        sites = service.sites().list().execute()
        
        properties = []
        if 'siteEntry' in sites:
            for site in sites['siteEntry']:
                # logger.info(f"Found Search Console site: {site}")
                properties.append({
                    'url': site['siteUrl'],
                    'permission_level': site.get('permissionLevel', '')
                })
        
        return properties

    except Exception as e:
        logger.error(f"Error getting Search Console properties: {str(e)}")
        raise