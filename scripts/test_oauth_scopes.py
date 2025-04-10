#!/usr/bin/env python
"""
Test script for verifying Google OAuth scopes.

This script tests the OAuth flow with both analytics.readonly and analytics (full) scopes.
It can be run as a Django management command:

python manage.py shell < scripts/test_oauth_scopes.py
"""

from apps.seo_manager.models import OAuthManager
from django.test.client import RequestFactory
from django.conf import settings
from django.contrib.sessions.middleware import SessionMiddleware
import json
import os

# Create a mock request with a valid hostname
factory = RequestFactory()

# Get APP_DOMAIN directly from environment variables
app_domain = os.environ.get('APP_DOMAIN', '').split(',')[0]
valid_host = app_domain if app_domain else 'localhost'
print(f"Using host: {valid_host}")

# Create the request with the valid host
request = factory.get('/', HTTP_HOST=valid_host)

# Add session to request
def add_session_to_request(request):
    middleware = SessionMiddleware(lambda req: None)
    middleware.process_request(request)
    request.session.save()

add_session_to_request(request)

# Test flow creation for Google Analytics with both scopes
try:
    # Create flow for GA with both scopes
    flow = OAuthManager.create_oauth_flow(request, service_type='ga')

    # Get the scopes from the flow
    scopes = flow.oauth2session.scope

    print("=== Google Analytics OAuth Flow Test ===")
    print(f"Scopes requested: {scopes}")

    # Check if both analytics scopes are included
    readonly_scope = OAuthManager.OAUTH_SCOPES['analytics']['readonly']
    full_scope = OAuthManager.OAUTH_SCOPES['analytics']['full']

    if readonly_scope in scopes and full_scope in scopes:
        print("SUCCESS: Both analytics.readonly and analytics (full) scopes are included.")
    else:
        print("ERROR: Missing one or both analytics scopes.")
        if readonly_scope not in scopes:
            print(f"  - Missing: {readonly_scope}")
        if full_scope not in scopes:
            print(f"  - Missing: {full_scope}")

    # Get the authorization URL
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )

    print(f"\nAuthorization URL: {auth_url}")
    print("\nNote: This URL includes both analytics scopes. You can verify this by checking")
    print("the 'scope' parameter in the URL, which should include both:")
    print(f"  - {readonly_scope}")
    print(f"  - {full_scope}")

except Exception as e:
    print(f"Error testing OAuth flow: {str(e)}")

# Test environment variable support if enabled
print("\n=== Environment Variable Support Test ===")
use_env = getattr(settings, 'GOOGLE_OAUTH_USE_ENV', False)
if use_env:
    print("Environment variable mode is ENABLED.")

    # Check if required environment variables are set
    client_id = getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', None)
    client_secret = getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', None)

    if client_id and client_secret:
        print("Required OAuth client environment variables are set.")
    else:
        print("WARNING: Some required OAuth client environment variables are missing:")
        if not client_id:
            print("  - GOOGLE_OAUTH_CLIENT_ID is not set")
        if not client_secret:
            print("  - GOOGLE_OAUTH_CLIENT_SECRET is not set")

    # Check service account environment variables
    sa_project_id = getattr(settings, 'GOOGLE_SA_PROJECT_ID', None)
    sa_private_key = getattr(settings, 'GOOGLE_SA_PRIVATE_KEY', None)
    sa_client_email = getattr(settings, 'GOOGLE_SA_CLIENT_EMAIL', None)

    if sa_project_id and sa_private_key and sa_client_email:
        print("Required service account environment variables are set.")
    else:
        print("WARNING: Some required service account environment variables are missing:")
        if not sa_project_id:
            print("  - GOOGLE_SA_PROJECT_ID is not set")
        if not sa_private_key:
            print("  - GOOGLE_SA_PRIVATE_KEY is not set")
        if not sa_client_email:
            print("  - GOOGLE_SA_CLIENT_EMAIL is not set")
else:
    print("Environment variable mode is DISABLED.")
    print("The application is using JSON files for credentials.")

    # Check if the JSON files exist
    client_secrets_file = getattr(settings, 'GOOGLE_CLIENT_SECRETS_FILE', None)
    service_account_file = getattr(settings, 'SERVICE_ACCOUNT_FILE', None)

    if client_secrets_file:
        try:
            with open(client_secrets_file, 'r') as f:
                json.load(f)
            print(f"Client secrets file exists and is valid JSON: {client_secrets_file}")
        except FileNotFoundError:
            print(f"WARNING: Client secrets file not found: {client_secrets_file}")
        except json.JSONDecodeError:
            print(f"WARNING: Client secrets file is not valid JSON: {client_secrets_file}")
    else:
        print("WARNING: GOOGLE_CLIENT_SECRETS_FILE setting is not defined")

    if service_account_file:
        try:
            with open(service_account_file, 'r') as f:
                json.load(f)
            print(f"Service account file exists and is valid JSON: {service_account_file}")
        except FileNotFoundError:
            print(f"WARNING: Service account file not found: {service_account_file}")
        except json.JSONDecodeError:
            print(f"WARNING: Service account file is not valid JSON: {service_account_file}")
    else:
        print("WARNING: SERVICE_ACCOUNT_FILE setting is not defined")

print("\n=== Test Complete ===")
print("If you see any warnings above, please address them before proceeding.")
print("If all tests passed, your OAuth configuration is correctly set up for both")
print("analytics.readonly and analytics (full) scopes.")
