from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from ..models import Client, SearchConsoleCredentials
from ..google_auth import get_google_auth_flow, get_search_console_properties
from apps.common.tools.user_activity_tool import user_activity_tool
import json
import logging

logger = logging.getLogger(__name__)

@login_required
def client_search_console(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    return render(request, 'seo_manager/client_search_console.html', {'client': client})

@login_required
def add_sc_credentials(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    
    # Check if client already has credentials
    if hasattr(client, 'sc_credentials'):
        messages.warning(request, "Search Console credentials already exist for this client. Remove them first to add new ones.")
        return redirect('seo_manager:client_detail', client_id=client.id)
    
    # Handle POST request for property selection
    if request.method == 'POST':
        selected_property = request.POST.get('selected_property')
        if selected_property:
            try:
                # Extract just the URL
                try:
                    property_data = json.loads(selected_property)
                    logger.info(f"property_data: {property_data}")
                    property_url = property_data['url']
                except (json.JSONDecodeError, KeyError):
                    property_url = selected_property

                logger.info(f"""
                    Storing Search Console credentials for {client.name}:
                    property_url: {property_url}
                    access_token: {bool(request.session.get('access_token'))}
                    refresh_token: {bool(request.session.get('refresh_token'))}
                    token_uri: {bool(request.session.get('token_uri'))}
                    client_id: {bool(request.session.get('client_id'))}
                    client_secret: {bool(request.session.get('client_secret'))}
                """)

                credentials = SearchConsoleCredentials.objects.update_or_create(
                    client=client,
                    defaults={
                        'property_url': property_url,
                        'access_token': request.session.get('access_token'),
                        'refresh_token': request.session.get('refresh_token'),
                        'token_uri': request.session.get('token_uri'),
                        'sc_client_id': request.session.get('client_id'),
                        'client_secret': request.session.get('client_secret'),
                    }
                )[0]
                user_activity_tool.run(request.user, 'create', f"Added Search Console credentials for client: {client.name}", client=client)
                messages.success(request, "Search Console credentials added successfully.")
                
                # Clean up session
                for key in ['properties', 'access_token', 'refresh_token', 'token_uri', 'client_id', 'client_secret']:
                    request.session.pop(key, None)
                
                return redirect('seo_manager:client_detail', client_id=client.id)
            except Exception as e:
                messages.error(request, f"Error saving Search Console credentials: {str(e)}")
        else:
            messages.error(request, "Please select a property.")
    
    # If we have properties in session, show selection page
    if 'properties' in request.session:
        return render(request, 'seo_manager/select_search_console_property.html', {
            'client': client,
            'properties': request.session['properties'],
        })
    
    # Start OAuth flow if no properties in session
    flow = get_google_auth_flow(request)
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        state=f"{client_id}_sc",
        prompt='consent'
    )
    request.session['oauth_state'] = state
    return redirect(authorization_url)

@login_required
def remove_sc_credentials(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    try:
        if hasattr(client, 'sc_credentials'):
            client.sc_credentials.delete()
            user_activity_tool.run(request.user, 'delete', f"Removed Search Console credentials for client: {client.name}", client=client)
            messages.success(request, "Search Console credentials removed successfully.")
        else:
            messages.warning(request, "No Search Console credentials found for this client.")
    except Exception as e:
        messages.error(request, f"Error removing Search Console credentials: {str(e)}")
    
    for key in ['properties', 'access_token', 'refresh_token', 'token_uri', 'client_id', 'client_secret']:
        request.session.pop(key, None)
    
    return redirect('seo_manager:client_detail', client_id=client.id)

@login_required
def add_sc_credentials_service_account(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    
    # Clear any existing session data
    for key in ['properties', 'service_account_json']:
        request.session.pop(key, None)
    
    if request.method == 'POST':
        if 'selected_property' in request.POST:
            selected_property = request.POST.get('selected_property')
            if selected_property:
                properties = request.session.get('properties', [])
                property_data = next((prop for prop in properties if prop['url'] == selected_property), None)
                if property_data:
                    SearchConsoleCredentials.objects.update_or_create(
                        client=client,
                        defaults={
                            'service_account_json': request.session.get('service_account_json', ''),
                            'property_url': property_data['url'],
                        }
                    )
                    user_activity_tool.run(request.user, 'create', f"Added Search Console credentials (Service Account) for client: {client.name}", client=client)
                    messages.success(request, "Search Console credentials (Service Account) added successfully.")
                    return redirect('seo_manager:client_detail', client_id=client.id)
                else:
                    messages.error(request, "Selected property not found. Please try again.")
            else:
                messages.error(request, "Please select a property.")
        elif 'service_account_file' in request.FILES:
            service_account_file = request.FILES['service_account_file']
            try:
                service_account_info = json.load(service_account_file)
                service_account_json = json.dumps(service_account_info)
                properties = get_search_console_properties(service_account_json)
                request.session['properties'] = properties
                request.session['service_account_json'] = service_account_json
                return render(request, 'seo_manager/select_search_console_property.html', {
                    'client': client,
                    'properties': properties,
                })
            except json.JSONDecodeError:
                messages.error(request, "Invalid JSON file. Please upload a valid service account JSON file.")
        else:
            messages.error(request, "No file uploaded. Please select a service account JSON file.")
    
    # If no POST or no properties in session, show the upload form
    return render(request, 'seo_manager/add_sc_credentials_service_account.html', {'client': client})

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
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        return []

__all__ = [
    'client_search_console',
    'add_sc_credentials',
    'add_sc_credentials_service_account',
    'remove_sc_credentials'
]
