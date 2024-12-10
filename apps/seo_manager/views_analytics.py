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

logger = logging.getLogger(__name__)

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

        try:
            logger.info("Fetching data using GoogleAnalyticsTool")
            ga_tool = GoogleAnalyticsTool()
            
            analytics_data = ga_tool._run(
                start_date=ga_start_date,
                end_date=ga_end_date,
                client_id=client_id
            )
            
            if analytics_data['success']:
                logger.info(f"Number of data points: {len(analytics_data['analytics_data'])}")
                if analytics_data['analytics_data']:
                    logger.info(f"Sample data point: {analytics_data['analytics_data'][0]}")
                
                context['analytics_data'] = json.dumps(analytics_data['analytics_data'])
                context['start_date'] = analytics_data['start_date']
                context['end_date'] = analytics_data['end_date']
            else:
                logger.warning(f"Failed to fetch GA data: {analytics_data.get('error')}")
                messages.warning(request, "Unable to fetch Google Analytics data.")
                
        except Exception as e:
            logger.error(f"Error fetching GA data: {str(e)}", exc_info=True)
            messages.warning(request, "Unable to fetch Google Analytics data.")

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
