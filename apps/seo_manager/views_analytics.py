import json
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Client, GoogleAnalyticsCredentials, SearchConsoleCredentials
from .google_auth import get_search_console_properties
from datetime import datetime, timedelta
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError
from apps.agents.tools.google_analytics_tool.google_analytics_tool import GoogleAnalyticsTool
from django.core.serializers.json import DjangoJSONEncoder
from apps.common.tools.user_activity_tool import user_activity_tool
from django.urls import reverse

logger = logging.getLogger(__name__)

def get_analytics_data(client_id, start_date, end_date):
    """Get Google Analytics data with proper error handling"""
    try:
        # Get the client and its analytics credentials
        client = get_object_or_404(Client, id=client_id)
        
        try:
            ga_credentials = GoogleAnalyticsCredentials.objects.get(client=client)
        except GoogleAnalyticsCredentials.DoesNotExist:
            logger.warning(f"No Google Analytics credentials found for client: {client.name}")
            return None
            
        # Get the credentials as a dictionary
        credentials_dict = {
            'access_token': ga_credentials.access_token,
            'refresh_token': ga_credentials.refresh_token,
            'token_uri': ga_credentials.token_uri or 'https://oauth2.googleapis.com/token',
            'ga_client_id': ga_credentials.ga_client_id,
            'client_secret': ga_credentials.client_secret,
            'scopes': ga_credentials.scopes
        }
        
        # Get the property ID using the method from the model
        analytics_property_id = ga_credentials.get_property_id()
        
        if not analytics_property_id:
            logger.warning(f"No Analytics property ID found for client: {client.name}")
            return None
        
        # Initialize the tool and run it with proper parameters
        ga_tool = GoogleAnalyticsTool()
        analytics_data = ga_tool._run(
            start_date=start_date,
            end_date=end_date,
            analytics_property_id=analytics_property_id,
            analytics_credentials=credentials_dict
        )
        
        if analytics_data['success']:
            return analytics_data
        else:
            logger.warning(f"Failed to fetch GA data: {analytics_data.get('error')}")
            return None
            
    except Exception as e:
        error_str = str(e)
        logger.error(f"Error fetching GA data: {error_str}")
        
        # Check for invalid grant error
        if 'invalid_grant' in error_str.lower():
            try:
                # Find the client and remove invalid credentials
                client = Client.objects.get(id=client_id)
                if hasattr(client, 'ga_credentials'):
                    client.ga_credentials.delete()
                    
                    # Log the removal
                    logger.info(f"Removed invalid Google Analytics credentials for client: {client.name}")
                    
                    # Log the activity
                    user_activity_tool.run(
                        None,  # System action
                        'delete',
                        f"Google Analytics credentials automatically removed due to invalid grant",
                        client=client
                    )
            except Client.DoesNotExist:
                logger.error(f"Could not find client with ID: {client_id}")
            except Exception as inner_e:
                logger.error(f"Error handling invalid credentials: {str(inner_e)}")
        
        return None

@login_required
def client_analytics(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    
    # Get credentials without forcing 404
    try:
        ga_credentials = GoogleAnalyticsCredentials.objects.get(client=client)
    except GoogleAnalyticsCredentials.DoesNotExist:
        ga_credentials = None
        
    try:
        sc_credentials = SearchConsoleCredentials.objects.get(client=client)
    except SearchConsoleCredentials.DoesNotExist:
        sc_credentials = None

    context = {
        'page_title': 'Client Analytics',
        'client': client,
        'analytics_data': None,
        'search_console_data': None,
    }

    # Only process GA data if credentials exist
    if ga_credentials:
        ga_range = request.GET.get('ga_range', '30')
        ga_end_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        if ga_range == 'custom':
            ga_start_date = request.GET.get('ga_start_date')
            ga_end_date = request.GET.get('ga_end_date')
            if not ga_start_date or not ga_end_date:
                messages.error(request, "Invalid GA date range provided")
                return redirect('seo_manager:client_analytics', client_id=client_id)
        else:
            try:
                days = int(ga_range)
                ga_start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            except ValueError:
                messages.error(request, "Invalid GA date range")
                return redirect('seo_manager:client_analytics', client_id=client_id)

        context.update({
            'ga_start_date': ga_start_date,
            'ga_end_date': ga_end_date,
            'selected_ga_range': ga_range,
        })

        analytics_data = get_analytics_data(client_id, ga_start_date, ga_end_date)
        
        if analytics_data:
            context['analytics_data'] = json.dumps(analytics_data['analytics_data'])
            context['start_date'] = analytics_data['start_date']
            context['end_date'] = analytics_data['end_date']
        else:
            # Check if credentials were removed due to invalid grant
            try:
                ga_credentials.refresh_from_db()
            except GoogleAnalyticsCredentials.DoesNotExist:
                messages.error(request, {
                    'title': 'Google Analytics Connection Expired',
                    'text': 'Your Google Analytics connection has expired or been revoked. Please reconnect your account.',
                    'icon': 'error',
                    'redirect_url': reverse('seo_manager:client_integrations', args=[client_id])
                }, extra_tags='sweetalert')
                return redirect('seo_manager:client_integrations', client_id=client.id)
            else:
                messages.error(request, {
                    'title': 'Error',
                    'text': 'An error occurred accessing Google Analytics. Please try again later.',
                    'icon': 'error',
                    'redirect_url': reverse('seo_manager:client_detail', args=[client_id])
                }, extra_tags='sweetalert')

    # Only process SC data if credentials exist
    if sc_credentials:
        sc_range = request.GET.get('sc_range', '30')
        sc_end_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        if sc_range == 'custom':
            sc_start_date = request.GET.get('sc_start_date')
            sc_end_date = request.GET.get('sc_end_date')
            if not sc_start_date or not sc_end_date:
                messages.error(request, "Invalid SC date range provided")
                return redirect('seo_manager:client_analytics', client_id=client_id)
        else:
            try:
                days = int(sc_range)
                sc_start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            except ValueError:
                messages.error(request, "Invalid SC date range")
                return redirect('seo_manager:client_analytics', client_id=client_id)

        context.update({
            'sc_start_date': sc_start_date,
            'sc_end_date': sc_end_date,
            'selected_sc_range': sc_range,
        })

        try:
            search_console_service = sc_credentials.get_service()
            if search_console_service:
                property_url = sc_credentials.get_property_url()
                if property_url:
                    search_console_data = get_search_console_data(
                        search_console_service, 
                        property_url,
                        sc_start_date,
                        sc_end_date
                    )
                    context['search_console_data'] = search_console_data
                else:
                    messages.warning(request, "Invalid Search Console property URL format.")
            else:
                messages.warning(request, "Search Console credentials are incomplete.")
        except Exception as e:
            logger.error(f"Error fetching Search Console data: {str(e)}")
            messages.warning(request, "Unable to fetch Search Console data.")

    return render(request, 'seo_manager/client_analytics.html', context)

def get_search_console_service(credentials, request):
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    
    creds = Credentials(
        token=credentials.access_token,
        refresh_token=credentials.refresh_token,
        token_uri=credentials.token_uri,
        client_id=credentials.sc_client_id,
        client_secret=credentials.client_secret
    )
    
    return build('searchconsole', 'v1', credentials=creds)

def get_search_console_data(service, property_url, start_date, end_date):
    try:
        response = service.searchanalytics().query(
            siteUrl=property_url,
            body={
                'startDate': start_date,
                'endDate': end_date,
                'dimensions': ['query'],
                'rowLimit': 1000
            }
        ).execute()
        
        search_console_data = []
        for row in response.get('rows', []):
            search_console_data.append({
                'query': row['keys'][0],
                'clicks': row['clicks'],
                'impressions': row['impressions'],
                'ctr': row['ctr'] * 100,  # Convert to percentage
                'position': row['position']
            })
        
        search_console_data.sort(key=lambda x: x['impressions'], reverse=True)
        
        return search_console_data
    except HttpError as error:
        print(f"An error occurred: {error}")
        return []
