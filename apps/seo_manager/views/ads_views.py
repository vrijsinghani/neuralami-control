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
    # Initialize customer_objects to an empty list
    customer_objects = []

    try:
        client = get_object_or_404(Client, id=client_id)
        logger.debug(f"select_ads_account called for client ID: {client_id}")

        # Check request method
        logger.debug(f"Request method: {request.method}")

        if request.method == 'GET':
            logger.debug("GET request to select_ads_account, checking for oauth_credentials in session")
            # Check if we have OAuth credentials in session
            oauth_credentials = request.session.get('oauth_credentials')
            logger.debug(f"oauth_credentials in session: {bool(oauth_credentials)}")

            if oauth_credentials:
                logger.debug(f"Credentials keys: {list(oauth_credentials.keys())}")

                # Initialize customer_objects here for the template
                customer_objects = []

                # Try to initialize the GoogleAdsClient and fetch customers
                try:
                    logger.debug("Attempting to initialize GoogleAdsClient from GET request handler")

                    # Import necessary modules
                    from google.oauth2.credentials import Credentials

                    # Create the credentials object directly
                    logger.debug("Creating OAuth credentials object with the following parameters:")
                    logger.debug(f"  token: {'Present' if oauth_credentials.get('token') else 'Missing'}")
                    logger.debug(f"  refresh_token: {'Present' if oauth_credentials.get('refresh_token') else 'Missing'}")

                    oauth_creds = Credentials(
                        token=oauth_credentials.get('token'),
                        refresh_token=oauth_credentials.get('refresh_token'),
                        token_uri=oauth_credentials.get('token_uri', 'https://oauth2.googleapis.com/token'),
                        client_id=oauth_credentials.get('client_id'),
                        client_secret=oauth_credentials.get('client_secret'),
                        scopes=oauth_credentials.get('scopes')
                    )

                    # Initialize the GoogleAdsClient with the credentials object directly
                    logger.debug("Initializing GoogleAdsClient with credentials object...")
                    ads_client = GoogleAdsClient(
                        credentials=oauth_creds,
                        developer_token=settings.GOOGLE_ADS_DEVELOPER_TOKEN,
                        use_proto_plus=True
                    )
                    logger.debug("GoogleAdsClient initialized successfully.")

                    # Fetch accessible customers
                    logger.info("Attempting to list accessible Google Ads customers...")
                    customer_service = ads_client.get_service("CustomerService")
                    accessible_customers = customer_service.list_accessible_customers()

                    # Log the number of customers retrieved
                    logger.info(f"Successfully listed {len(accessible_customers.resource_names)} Google Ads customers.")

                    # Extract customer IDs from resource names
                    customer_ids = [
                        resource_name.split('/')[-1]
                        for resource_name in accessible_customers.resource_names
                    ]
                    logger.info(f"Stored customer IDs in session: {customer_ids}")

                    # For the template, we need to create objects with id and name properties
                    # Since we can't get detailed information due to developer token limitations,
                    # we'll just use the account IDs we already have
                    customer_objects = []

                    # Try to get the account names from the list_accessible_customers response
                    # The resource_names might contain additional information we can extract
                    for customer_id in customer_ids:
                        # Create a basic customer object with the ID
                        customer_objects.append({
                            'id': customer_id,
                            'name': f"Google Ads Account {customer_id}",
                            'status': 'Active',  # Assume active since we can access it
                            'currency_code': None,
                            'time_zone': None,
                            'manager': False  # Default to regular account
                        })

                    # Log the customer objects we created
                    logger.debug(f"Created {len(customer_objects)} customer objects with basic information for template")
                except Exception as e:
                    logger.error(f"Error initializing GoogleAdsClient in GET handler: {str(e)}", exc_info=True)

        if request.method == 'POST':
            # Add logging to see what's in the POST data
            logger.debug(f"POST data: {request.POST}")

            # Get the selected customer ID from the form
            customer_id = request.POST.get('selected_customer_id')
            login_customer_id = request.POST.get('selected_login_customer_id')

            logger.debug(f"Selected customer_id: {customer_id}, login_customer_id: {login_customer_id}")

            if not customer_id:
                raise ValidationError("No customer ID selected")

            # Get OAuth credentials from session
            credentials_dict = request.session.get('oauth_credentials')
            logger.debug(f"OAuth credentials from session: {'Present' if credentials_dict else 'Missing'}")

            if not credentials_dict:
                logger.error("OAuth credentials not found in session")
                raise ValidationError("OAuth credentials not found")

            # Log the structure of the credentials dict
            logger.debug(f"Credentials dict keys: {list(credentials_dict.keys())}")
            logger.debug(f"Credentials dict contains token: {'Yes' if 'token' in credentials_dict else 'No'}")
            logger.debug(f"Credentials dict contains refresh_token: {'Yes' if 'refresh_token' in credentials_dict else 'No'}")

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
        logger.debug("GET request to select_ads_account, checking for oauth_credentials in session")
        credentials_dict = request.session.get('oauth_credentials')
        logger.debug(f"oauth_credentials in session: {credentials_dict is not None}")
        if credentials_dict:
            # Log credentials (excluding sensitive data)
            safe_creds = {k: ('***REDACTED***' if k in ['token', 'refresh_token', 'client_secret'] else v)
                         for k, v in credentials_dict.items()}
            logger.debug(f"Credentials keys: {list(credentials_dict.keys())}")
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

                # The GoogleAdsClient expects a dictionary with specific keys
                logger.debug("Creating credentials dictionary for GoogleAdsClient...")

                # Add detailed logging to diagnose the issue
                logger.debug("Creating credentials directly instead of using load_from_dict")

                # Import necessary modules
                from google.oauth2.credentials import Credentials
                from google.auth.transport.requests import Request

                # Create the credentials object directly
                logger.debug("Creating OAuth credentials object with the following parameters:")
                logger.debug(f"  token: {'Present' if credentials_dict.get('token') else 'Missing'}")
                logger.debug(f"  refresh_token: {'Present' if credentials_dict.get('refresh_token') else 'Missing'}")
                logger.debug(f"  token_uri: {credentials_dict.get('token_uri', 'https://oauth2.googleapis.com/token')}")
                logger.debug(f"  client_id: {'Present' if credentials_dict.get('client_id') else 'Missing'}")
                logger.debug(f"  client_secret: {'Present' if credentials_dict.get('client_secret') else 'Missing'}")
                logger.debug(f"  scopes: {credentials_dict.get('scopes')}")

                oauth_credentials = Credentials(
                    token=credentials_dict.get('token'),
                    refresh_token=credentials_dict.get('refresh_token'),
                    token_uri=credentials_dict.get('token_uri', 'https://oauth2.googleapis.com/token'),
                    client_id=credentials_dict.get('client_id'),
                    client_secret=credentials_dict.get('client_secret'),
                    scopes=credentials_dict.get('scopes')
                )

                # Log the credentials object attributes
                logger.debug(f"Created credentials object with refresh_token: {'Present' if oauth_credentials.refresh_token else 'Missing'}")
                logger.debug(f"Created credentials object with token_uri: {oauth_credentials.token_uri}")
                logger.debug(f"Created credentials object with client_id: {'Present' if oauth_credentials.client_id else 'Missing'}")
                logger.debug(f"Created credentials object with client_secret: {'Present' if oauth_credentials.client_secret else 'Missing'}")

                # Initialize the GoogleAdsClient with the credentials object directly
                logger.debug("Initializing GoogleAdsClient with credentials object...")
                try:
                    ads_client = GoogleAdsClient(
                        credentials=oauth_credentials,
                        developer_token=settings.GOOGLE_ADS_DEVELOPER_TOKEN,
                        use_proto_plus=True
                    )
                    logger.debug("GoogleAdsClient initialized successfully.")
                    logger.debug(f"GoogleAdsClient configuration: developer_token={settings.GOOGLE_ADS_DEVELOPER_TOKEN[:5]}..., use_proto_plus={True}")
                except Exception as client_e:
                    logger.error(f"Error initializing GoogleAdsClient: {str(client_e)}", exc_info=True)
                    if hasattr(client_e, '__dict__'):
                        logger.error(f"Error attributes: {client_e.__dict__}")
                    raise

                # Fetch accessible customers
                logger.info("Attempting to list accessible Google Ads customers...")
                try:
                    # Log the client configuration
                    logger.debug(f"GoogleAdsClient configuration: developer_token={settings.GOOGLE_ADS_DEVELOPER_TOKEN[:5]}..., use_proto_plus={True}")

                    # Get the customer service
                    logger.debug("Getting CustomerService from ads_client...")
                    customer_service = ads_client.get_service("CustomerService")
                    logger.debug("Successfully got CustomerService from ads_client")

                    # Add more detailed logging
                    logger.debug("About to call list_accessible_customers()...")
                    try:
                        # Log the customer service object
                        logger.debug(f"CustomerService object: {customer_service}")

                        # Try to get the service path
                        try:
                            service_path = customer_service._service_path
                            logger.debug(f"CustomerService path: {service_path}")
                        except Exception as path_e:
                            logger.debug(f"Could not get service path: {str(path_e)}")

                        # Call list_accessible_customers with detailed logging
                        logger.debug("Calling list_accessible_customers() now...")
                        accessible_customers = customer_service.list_accessible_customers()

                        # Log the result
                        if hasattr(accessible_customers, 'resource_names'):
                            logger.info(f"Successfully listed {len(accessible_customers.resource_names)} Google Ads customers.")
                        else:
                            logger.warning("list_accessible_customers() returned an object without resource_names attribute")
                            logger.debug(f"Return type: {type(accessible_customers)}, value: {accessible_customers}")

                        # Log each resource name for debugging
                        for i, resource_name in enumerate(accessible_customers.resource_names):
                            logger.debug(f"  Customer resource {i+1}: {resource_name}")
                    except Exception as inner_e:
                        logger.error(f"Error in list_accessible_customers(): {str(inner_e)}", exc_info=True)
                        # Try to get more details about the error
                        if hasattr(inner_e, 'failure') and hasattr(inner_e.failure, 'errors'):
                            for error in inner_e.failure.errors:
                                logger.error(f"Google Ads API error: {error}")
                        raise
                except Exception as e:
                    logger.error(f"Error setting up customer service: {str(e)}", exc_info=True)
                    # Try to get more details about the error
                    if hasattr(e, '__dict__'):
                        logger.error(f"Error attributes: {e.__dict__}")
                    raise

                # Store customer IDs in session
                logger.debug(f"Processing resource_names from accessible_customers: {accessible_customers.resource_names}")
                logger.debug(f"Number of resource_names: {len(accessible_customers.resource_names)}")

                # Log each resource name individually for better debugging
                for i, resource_name in enumerate(accessible_customers.resource_names):
                    logger.debug(f"Resource name {i+1}: {resource_name}")

                # Extract customer IDs from resource names
                customer_ids = []
                for resource_name in accessible_customers.resource_names:
                    try:
                        # Extract the customer ID from the resource name
                        customer_id = resource_name.split('/')[-1]
                        logger.debug(f"Extracted customer ID: {customer_id} from resource name: {resource_name}")
                        customer_ids.append(customer_id)
                    except Exception as extract_e:
                        logger.error(f"Error extracting customer ID from resource name {resource_name}: {str(extract_e)}", exc_info=True)

                logger.debug(f"Final extracted customer IDs: {customer_ids}")
                request.session['customer_ids'] = customer_ids
                logger.info(f"Stored customer IDs in session: {customer_ids}")

                # For the template, we need to create objects with id and name properties
                # Since we don't have the actual names, we'll use the IDs as names for now
                customer_objects = []
                for customer_id in customer_ids:
                    try:
                        customer_obj = {'id': customer_id, 'name': f"Account {customer_id}"}
                        customer_objects.append(customer_obj)
                        logger.debug(f"Created customer object: {customer_obj}")
                    except Exception as obj_e:
                        logger.error(f"Error creating customer object for ID {customer_id}: {str(obj_e)}", exc_info=True)

                # Log the customer objects for debugging
                logger.debug(f"Created {len(customer_objects)} customer objects for template")
                for i, obj in enumerate(customer_objects):
                    logger.debug(f"  Customer {i+1}: id={obj['id']}, name={obj['name']}")

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

        # Render the template with customer IDs
        logger.debug(f"Rendering select_ads_account.html template with {len(customer_objects) if customer_objects else 0} customer objects")
        logger.debug(f"Template context: client={client.id}, customer_ids={customer_objects}")

        # Check if customer_objects is empty
        if not customer_objects:
            logger.warning("No customer objects available to display in template")
            messages.warning(request, "No Google Ads accounts were found for your account. Please make sure you have access to at least one Google Ads account.")

        return render(request, 'seo_manager/select_ads_account.html', {
            'client': client,
            'customer_ids': customer_objects,
            'debug': True  # Enable debug information in the template
        })

    except Exception as e:
        logger.error(f"Error in select_ads_account: {str(e)}", exc_info=True)
        # Add more detailed logging to understand the exact error
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
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