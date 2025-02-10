import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from ..models import Client, GoogleAnalyticsCredentials, OAuthManager, SearchConsoleCredentials
from ..google_auth import (
    get_analytics_accounts_oauth, 
    get_analytics_accounts_service_account,
    get_search_console_properties
)
from apps.common.tools.user_activity_tool import user_activity_tool
from ..exceptions import AuthError
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
import logging
import google.oauth2.credentials
from google_auth_oauthlib.flow import Flow
from django.conf import settings
from django.urls import reverse

logger = logging.getLogger(__name__)

def _get_redirect_url(request, client_id):
    """Helper function to determine redirect URL based on 'next' parameter"""
    next_page = request.GET.get('next')
    if next_page == 'integrations':
        return 'seo_manager:client_integrations'
    return 'seo_manager:client_detail'

@login_required
def client_ads(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    # Add page_title to the context
    context = {
        'client': client,
        'page_title': 'Google Ads',
    }
    return render(request, 'seo_manager/client_ads.html', context)

@login_required
def client_dataforseo(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    # Add page_title to the context
    context = {
        'client': client,
        'page_title': 'DataforSEO',
    }
    return render(request, 'seo_manager/client_dataforseo.html', context)

@login_required
def initiate_google_oauth(request, client_id, service_type):
    """Start OAuth flow for Google services"""
    client = get_object_or_404(Client, id=client_id)
    
    try:
        # Create state key
        state_key = f"{client_id}_{service_type}"
        
        # Get the current domain and scheme
        scheme = request.scheme
        domain = request.get_host()
        redirect_uri = f'{scheme}://{domain}/google/login/callback/'
        
        # Define scopes based on service type
        scopes = []
        if service_type == 'ga':
            scopes = [
                'https://www.googleapis.com/auth/analytics.readonly',
                'https://www.googleapis.com/auth/userinfo.email'
            ]
        elif service_type == 'sc':
            scopes = [
                'https://www.googleapis.com/auth/webmasters.readonly',
                'https://www.googleapis.com/auth/userinfo.email'
            ]
        
        # Create OAuth flow with correct callback URL
        flow = Flow.from_client_secrets_file(
            settings.GOOGLE_CLIENT_SECRETS_FILE,
            scopes=scopes,
            state=state_key,
            redirect_uri=redirect_uri
        )
        
        # Store both state and redirect URI in session
        request.session['oauth_state'] = state_key
        request.session['oauth_redirect_uri'] = redirect_uri
        request.session['oauth_service_type'] = service_type
        request.session.modified = True
        
        # Get authorization URL with proper parameters
        authorization_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='select_account'
        )
        
        logger.info(f"Initiating OAuth flow for client {client.name} ({service_type})")
        
        return redirect(authorization_url)
        
    except Exception as e:
        logger.error(f"OAuth initiation error: {str(e)}", exc_info=True)
        messages.error(request, "Failed to start authentication process")
        return redirect('seo_manager:client_detail', client_id=client_id)

@login_required
def google_oauth_callback(request):
    """Handle OAuth callback"""
    try:
        # Verify state
        state = request.GET.get('state')
        stored_state = request.session.get('oauth_state')
        
        if not state or state != stored_state:
            logger.error("Invalid OAuth state")
            messages.error(request, "Invalid authentication state. Please try again.")
            return redirect('seo_manager:dashboard')
        
        # Extract client_id from state
        try:
            client_id = int(state.split('_')[0])
            service_type = state.split('_')[1]
        except (IndexError, ValueError):
            logger.error(f"Invalid state format: {state}")
            messages.error(request, "Invalid authentication data. Please try again.")
            return redirect('seo_manager:dashboard')
        
        client = get_object_or_404(Client, id=client_id)
        
        # Get the current domain and scheme for redirect URI
        scheme = request.scheme
        domain = request.get_host()
        redirect_uri = f'{scheme}://{domain}/google/login/callback/'
        
        # Complete OAuth flow
        try:
            flow = Flow.from_client_secrets_file(
                settings.GOOGLE_CLIENT_SECRETS_FILE,
                scopes=[
                    'https://www.googleapis.com/auth/analytics.readonly',
                    'https://www.googleapis.com/auth/webmasters.readonly',
                    'openid',
                    'https://www.googleapis.com/auth/userinfo.email',
                    'https://www.googleapis.com/auth/userinfo.profile'
                ],
                state=state,
                redirect_uri=redirect_uri
            )
            
            # Fetch token
            token = flow.fetch_token(code=request.GET.get('code'))
            
            # Convert token to Google Credentials
            credentials = google.oauth2.credentials.Credentials(
                token=token['access_token'],
                refresh_token=token.get('refresh_token'),
                token_uri='https://oauth2.googleapis.com/token',
                client_id=flow.client_config['client_id'],
                client_secret=flow.client_config['client_secret'],
                scopes=token.get('scope', '').split(' ') if isinstance(token.get('scope'), str) else token.get('scope', [])
            )
            
            # Store credentials in session
            request.session['oauth_credentials'] = OAuthManager.credentials_to_dict(credentials)
            
            if service_type == 'ga':
                try:
                    # Get available accounts using the Google Credentials
                    accounts = get_analytics_accounts_oauth(credentials)
                    
                    if not accounts:
                        logger.warning(f"No GA4 properties found for client {client.name}")
                        messages.warning(request, "No Google Analytics 4 properties were found.")
                        redirect_url = _get_redirect_url(request, client_id)
                        return redirect(redirect_url, client_id=client_id)
                    
                    request.session['accounts'] = accounts
                    # Pass the next parameter to the select account view
                    next_page = request.GET.get('next')
                    url = reverse('seo_manager:select_analytics_account', args=[client_id])
                    if next_page:
                        url += f'?next={next_page}'
                    return redirect(url)
                    
                except Exception as e:
                    logger.error(f"Error fetching GA4 properties: {str(e)}", exc_info=True)
                    messages.error(request, "Failed to fetch Google Analytics properties.")
                    redirect_url = _get_redirect_url(request, client_id)
                    return redirect(redirect_url, client_id=client_id)
            
            elif service_type == 'sc':
                try:
                    # Get available Search Console properties
                    properties = get_search_console_properties(credentials)
                    if not properties:
                        messages.warning(request, "No Search Console properties found. Please verify your permissions.")
                        return redirect('seo_manager:client_detail', client_id=client_id)
                    
                    request.session['sc_properties'] = properties
                    return redirect('seo_manager:select_search_console_property', client_id=client_id)
                    
                except Exception as e:
                    logger.error(f"Error fetching Search Console properties: {str(e)}", exc_info=True)
                    messages.error(request, "Failed to fetch Search Console properties. Please verify your permissions.")
                    return redirect('seo_manager:client_detail', client_id=client_id)
            
        except Exception as e:
            logger.error(f"OAuth flow error: {str(e)}", exc_info=True)
            messages.error(request, "Authentication failed. Please try again.")
            return redirect('seo_manager:client_detail', client_id=client_id)
            
    except Exception as e:
        logger.error(f"OAuth callback error: {str(e)}", exc_info=True)
        messages.error(request, "Authentication failed. Please try again.")
        return redirect('seo_manager:dashboard')
    
    return redirect('seo_manager:client_detail', client_id=client_id)

@login_required
def add_ga_credentials_oauth(request, client_id):
    """Handle Google Analytics OAuth credential addition"""
    client = get_object_or_404(Client, id=client_id)
    
    if request.method == 'GET':
        try:
            # Create state key
            state_key = f"{client_id}_ga"
            
            # Get the current domain and scheme
            scheme = request.scheme
            domain = request.get_host()
            redirect_uri = f'{scheme}://{domain}/google/login/callback/'
            
            # Create OAuth flow with minimal required scopes for GA4
            flow = Flow.from_client_secrets_file(
                settings.GOOGLE_CLIENT_SECRETS_FILE,
                scopes=[
                    'https://www.googleapis.com/auth/analytics.readonly',
                    'https://www.googleapis.com/auth/userinfo.email'
                ],
                state=state_key,
                redirect_uri=redirect_uri
            )
            
            # Get authorization URL with proper parameters
            authorization_url, _ = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent'
            )
            
            # Store state in session
            request.session['oauth_state'] = state_key
            request.session['oauth_service_type'] = 'ga'
            request.session['oauth_client_id'] = client_id
            request.session['oauth_redirect_uri'] = redirect_uri
            request.session.modified = True
            
            return redirect(authorization_url)
            
        except Exception as e:
            logger.error(f"Error starting GA OAuth flow: {str(e)}")
            messages.error(request, "Failed to start authentication process")
            return redirect('seo_manager:client_detail', client_id=client_id)
    
    return redirect('seo_manager:client_detail', client_id=client_id)

@login_required
def add_ga_credentials_service_account(request, client_id):
    """Handle Google Analytics service account credential addition"""
    client = get_object_or_404(Client, id=client_id)
    
    if request.method == 'GET':
        return render(request, 'seo_manager/credentials/add_ga_service_account.html', {
            'client': client
        })
        
    elif request.method == 'POST':
        try:
            if 'service_account_file' not in request.FILES:
                raise AuthError("No service account file provided")
                
            service_account_file = request.FILES['service_account_file']
            service_account_json = json.load(service_account_file)
            
            ga_credentials, created = GoogleAnalyticsCredentials.objects.get_or_create(
                client=client,
                defaults={'user_email': request.user.email}
            )
            
            ga_credentials.handle_service_account(json.dumps(service_account_json))
            
            messages.success(request, "Service account credentials added successfully")
            return redirect('seo_manager:client_detail', client_id=client.id)
            
        except AuthError as e:
            messages.error(request, str(e))
        except json.JSONDecodeError:
            messages.error(request, "Invalid JSON file")
        except Exception as e:
            logger.error(f"Error adding service account: {str(e)}")
            messages.error(request, "Failed to add service account credentials")
            
        return redirect('seo_manager:client_detail', client_id=client.id)

@login_required
def remove_ga_credentials(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    if client.ga_credentials:
        client.ga_credentials.delete()
        user_activity_tool.run(request.user, 'delete', f"Removed Google Analytics credentials for client: {client.name}", client=client)
        messages.success(request, "Google Analytics credentials removed successfully.")
    
    return redirect('seo_manager:client_integrations', client_id=client.id)

@login_required
def client_detail(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    
    try:
        # Handle GA credentials check
        ga_credentials = getattr(client, 'ga_credentials', None)
        if ga_credentials:
            try:
                ga_credentials.validate_credentials()
            except AuthError:
                messages.warning(request, "Google Analytics credentials need to be re-authenticated.")
                ga_credentials.delete()
        
        # Handle SC credentials check similarly
        sc_credentials = getattr(client, 'sc_credentials', None)
        if sc_credentials:
            try:
                sc_credentials.validate_credentials()
            except AuthError:
                messages.warning(request, "Search Console credentials need to be re-authenticated.")
                sc_credentials.delete()
                
    except Exception as e:
        logger.error(f"Error checking credentials: {str(e)}")
        messages.error(request, "Error validating credentials")

    return redirect('seo_manager:client_integrations', client_id=client.id)

@login_required
def add_sc_credentials(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    
    # Start OAuth flow
    try:
        flow = OAuthManager.create_oauth_flow(
            request, 
            state=f"{client_id}_sc"
        )
        authorization_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        request.session['oauth_state'] = f"{client_id}_sc"
        return redirect(authorization_url)
        
    except Exception as e:
        logger.error(f"Error initiating Search Console OAuth: {str(e)}")
        messages.error(request, "Failed to start authentication process")
        return redirect('seo_manager:client_detail', client_id=client_id)

@login_required
def select_analytics_account(request, client_id):
    """Handle Analytics account selection"""
    client = get_object_or_404(Client, id=client_id)
    
    if request.method == 'POST':
        try:
            selected_account = request.POST.get('selected_account')
            if not selected_account:
                raise ValidationError("No account selected")
                
            credentials_dict = request.session.get('oauth_credentials')
            if not credentials_dict:
                raise AuthError("No OAuth credentials found in session")
            
            logger.info(f"Creating/updating GA credentials for client {client.name}")
            logger.debug(f"Credentials dict: {credentials_dict}")
                
            ga_credentials, created = GoogleAnalyticsCredentials.objects.get_or_create(
                client=client,
                defaults={'user_email': request.user.email}
            )
            
            # Save credentials and account info
            ga_credentials.handle_oauth_response(credentials_dict)
            ga_credentials.view_id = selected_account
            ga_credentials.save()
            
            logger.info(f"Successfully saved GA credentials for client {client.name}")
            
            # Clean up session
            for key in ['oauth_credentials', 'accounts', 'oauth_state', 'oauth_service_type', 'oauth_client_id']:
                request.session.pop(key, None)
            
            messages.success(request, "Google Analytics credentials added successfully")
            return redirect('seo_manager:client_integrations', client_id=client.id)
            
        except Exception as e:
            logger.error(f"Error saving GA credentials: {str(e)}", exc_info=True)
            messages.error(request, f"Failed to save Google Analytics credentials: {str(e)}")
            return redirect('seo_manager:client_integrations', client_id=client.id)
    
    # For GET requests
    context = {
        'client': client,
        'accounts': request.session.get('accounts', []),
    }
    return render(request, 'seo_manager/select_analytics_account.html', context)

@login_required
def select_search_console_property(request, client_id):
    """Handle Search Console property selection"""
    client = get_object_or_404(Client, id=client_id)
    
    if request.method == 'POST':
        try:
            selected_property = request.POST.get('selected_property')
            if not selected_property:
                raise ValidationError("No property selected")
                
            credentials_dict = request.session.get('oauth_credentials')
            if not credentials_dict:
                raise AuthError("No OAuth credentials found in session")
            
            logger.info(f"Creating/updating SC credentials for client {client.name}")
            logger.debug(f"Credentials dict: {credentials_dict}")
                
            sc_credentials, created = SearchConsoleCredentials.objects.get_or_create(
                client=client,
                defaults={}
            )
            
            # Save credentials and property info
            sc_credentials.handle_oauth_response(credentials_dict)
            sc_credentials.property_url = selected_property
            if request.user.email:
                sc_credentials.user_email = request.user.email
            sc_credentials.save()
            
            logger.info(f"Successfully saved SC credentials for client {client.name}")
            
            # Clean up session
            for key in ['oauth_credentials', 'sc_properties', 'oauth_state']:
                request.session.pop(key, None)
            
            messages.success(request, "Search Console credentials added successfully")
            return redirect('seo_manager:client_integrations', client_id=client.id)
            
        except Exception as e:
            logger.error(f"Error saving SC credentials: {str(e)}", exc_info=True)
            messages.error(request, f"Failed to save Search Console credentials: {str(e)}")
            return redirect('seo_manager:client_integrations', client_id=client.id)
    
    # Handle GET request
    properties = request.session.get('sc_properties', [])
    if not properties:
        messages.error(request, "No Search Console properties found in session. Please try authenticating again.")
        return redirect('seo_manager:client_integrations', client_id=client.id)
        
    return render(request, 'seo_manager/select_search_console_property.html', {
        'client': client,
        'properties': properties
    })

@login_required
def add_sc_credentials_service_account(request, client_id):
    """Handle Search Console service account credential addition"""
    client = get_object_or_404(Client, id=client_id)
    
    if request.method == 'GET':
        return render(request, 'seo_manager/credentials/add_sc_service_account.html', {
            'client': client
        })
        
    elif request.method == 'POST':
        try:
            if 'service_account_file' not in request.FILES:
                raise AuthError("No service account file provided")
                
            service_account_file = request.FILES['service_account_file']
            service_account_json = json.load(service_account_file)
            
            sc_credentials, created = SearchConsoleCredentials.objects.get_or_create(
                client=client,
                defaults={'user_email': request.user.email}
            )
            
            sc_credentials.handle_service_account(json.dumps(service_account_json))
            
            messages.success(request, "Service account credentials added successfully")
            return redirect('seo_manager:client_integrations', client_id=client.id)
            
        except AuthError as e:
            messages.error(request, str(e))
        except json.JSONDecodeError:
            messages.error(request, "Invalid JSON file")
        except Exception as e:
            logger.error(f"Error adding service account: {str(e)}")
            messages.error(request, "Failed to add service account credentials")
            
        return redirect('seo_manager:client_integrations', client_id=client.id)

