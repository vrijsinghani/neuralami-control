import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from ..models import Client, GoogleAdsCredentials, OAuthManager
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from django.conf import settings
from google.oauth2.credentials import Credentials
from django.urls import reverse

logger = logging.getLogger(__name__)

@login_required
def initiate_google_ads_oauth(request, client_id):
    """Initiate OAuth flow for Google Ads"""
    try:
        client = get_object_or_404(Client, id=client_id)
        
        # Create state key for this OAuth flow
        state_key = f"{client_id}_ads"
        
        # Create OAuth flow
        flow = OAuthManager.create_oauth_flow(
            request=request,
            state_key=state_key
        )
        
        # Store state in session - use the state_key we created
        request.session['oauth_state'] = state_key
        request.session['service_type'] = 'ads'
        
        # Redirect to authorization URL
        auth_url = flow.authorization_url()[0]
        return redirect(auth_url)
        
    except Exception as e:
        logger.error(f"Error initiating Google Ads OAuth: {str(e)}", exc_info=True)
        messages.error(request, "Failed to initiate Google Ads authentication.")
        return redirect('seo_manager:client_integrations', client_id=client_id)

@login_required
def select_ads_account(request, client_id):
    """Handle Google Ads account selection"""
    try:
        client = get_object_or_404(Client, id=client_id)
        
        if request.method == 'POST':
            customer_id = request.POST.get('customer_id')
            login_customer_id = request.POST.get('login_customer_id')
            
            if not customer_id:
                raise ValidationError("No customer ID selected")
                
            # Get OAuth credentials from session
            credentials_dict = request.session.get('oauth_credentials')
            if not credentials_dict:
                raise ValidationError("OAuth credentials not found")
                
            # Create or update GoogleAdsCredentials
            credentials, created = GoogleAdsCredentials.objects.update_or_create(
                client=client,
                defaults={
                    'customer_id': customer_id,
                    'login_customer_id': login_customer_id or customer_id,
                    'access_token': credentials_dict['token'],
                    'refresh_token': credentials_dict['refresh_token'],
                    'token_uri': credentials_dict['token_uri'],
                    'ads_client_id': credentials_dict['client_id'],
                    'client_secret': credentials_dict['client_secret'],
                    'scopes': credentials_dict['scopes'],
                    'user_email': credentials_dict.get('user_email', '')
                }
            )
            
            # Clean up session
            request.session.pop('oauth_credentials', None)
            request.session.pop('customer_ids', None)
            
            messages.success(request, "Google Ads account connected successfully!")
            return redirect('seo_manager:client_integrations', client_id=client_id)
            
        # If GET request, try to fetch accessible customers
        credentials_dict = request.session.get('oauth_credentials')
        if not credentials_dict:
            messages.error(request, "OAuth credentials not found")
            return redirect('seo_manager:client_integrations', client_id=client_id)
            
        customer_ids = request.session.get('customer_ids')
        if not customer_ids:
            try:
                # Log credentials dictionary to diagnose issues (excluding sensitive data)
                safe_creds = {k: ('***REDACTED***' if k in ['token', 'refresh_token', 'client_secret'] else v) 
                             for k, v in credentials_dict.items()}
                logger.debug(f"OAuth credentials retrieved: {safe_creds}")
                
                # First, create proper OAuth credentials
                logger.debug("Creating OAuth Credentials object...")
                oauth_credentials = Credentials(
                    token=credentials_dict['token'],
                    refresh_token=credentials_dict['refresh_token'],
                    token_uri=credentials_dict['token_uri'],
                    client_id=credentials_dict['client_id'],
                    client_secret=credentials_dict['client_secret'],
                    scopes=credentials_dict['scopes']
                )
                logger.debug("OAuth Credentials object created successfully.")
                
                # Then use the GoogleAdsClient with the OAuth credentials
                logger.debug("Initializing GoogleAdsClient...")
                ads_client = GoogleAdsClient(
                    credentials=oauth_credentials,
                    developer_token=settings.GOOGLE_ADS_DEVELOPER_TOKEN,
                    use_proto_plus=True
                )
                logger.debug("GoogleAdsClient initialized successfully.")
                
                # Fetch accessible customers
                logger.info("Attempting to list accessible Google Ads customers...")
                customer_service = ads_client.get_service("CustomerService")
                accessible_customers = customer_service.list_accessible_customers()
                logger.info(f"Successfully listed {len(accessible_customers.resource_names)} Google Ads customers.")
                
                # Store customer IDs in session
                customer_ids = [
                    resource_name.split('/')[-1] 
                    for resource_name in accessible_customers.resource_names
                ]
                request.session['customer_ids'] = customer_ids
                logger.debug(f"Stored customer IDs in session: {customer_ids}")
                
            except GoogleAdsException as e:
                # Catch Google Ads specific exceptions for more detailed logging
                logger.error(f"Google Ads API error occurred while fetching customers: {e}", exc_info=True)
                messages.error(request, f"Google Ads API error: {e}. Please check permissions and API access.")
                return redirect('seo_manager:client_integrations', client_id=client_id)
            except Exception as e:
                # Catch any other exceptions
                logger.error(f"Generic error fetching Google Ads customers: {str(e)}", exc_info=True)
                messages.error(request, "Failed to fetch Google Ads accounts. Please try again.")
                return redirect('seo_manager:client_integrations', client_id=client_id)
                
        return render(request, 'seo_manager/select_ads_account.html', {
            'client': client,
            'customer_ids': customer_ids
        })
        
    except Exception as e:
        logger.error(f"Error in select_ads_account: {str(e)}", exc_info=True)
        messages.error(request, "An error occurred while setting up Google Ads integration.")
        return redirect('seo_manager:client_integrations', client_id=client_id)

@login_required
def remove_ads_credentials(request, client_id):
    """Remove Google Ads credentials for a client"""
    try:
        client = get_object_or_404(Client, id=client_id)
        
        # Delete the credentials
        if hasattr(client, 'ads_credentials'):
            client.ads_credentials.delete()
            messages.success(request, "Google Ads credentials removed successfully.")
        else:
            messages.warning(request, "No Google Ads credentials found to remove.")
            
        # Get the next URL from query parameters or default to client integrations
        next_url = request.GET.get('next', '')
        if next_url == 'integrations':
            return redirect('seo_manager:client_integrations', client_id=client_id)
        return redirect('seo_manager:client_detail', client_id=client_id)
        
    except Exception as e:
        logger.error(f"Error removing Google Ads credentials: {str(e)}", exc_info=True)
        messages.error(request, "Failed to remove Google Ads credentials.")
        return redirect('seo_manager:client_integrations', client_id=client_id) 