#!/usr/bin/env python
"""
Simple test script for verifying the OAuth implementation.

This script can be run as a Django management command:

python manage.py shell < scripts/test_oauth_simple.py
"""

import sys
from django.db.models import Count
from apps.seo_manager.models import Client
from apps.organizations.models import Organization

# Function to set organization context
def set_organization_context(org):
    from django.db.models.signals import pre_init
    from apps.organizations.models.mixins import OrganizationModelMixin

    # Set the organization context for the current thread
    OrganizationModelMixin._organization_context.set(org)
    print(f"Organization context set to: {org.name}")

# Print a clear start message
print("\n===================================================")
print("STARTING SIMPLE OAUTH TEST SCRIPT")
print("===================================================\n")

# Set organization context
organizations = Organization.objects.all()
if organizations.exists():
    org = organizations.first()
    print(f"Setting organization context to: {org.name}")
    set_organization_context(org)
else:
    print("No organizations found")

# Get all clients
clients = Client.objects.all()
print(f"Found {clients.count()} clients in total")

# List all clients
for client in clients:
    print(f"Client: {client.name} (ID: {client.id})")

    # Check for GA credentials
    has_ga = hasattr(client, 'ga_credentials')
    print(f"  - GA credentials: {'Yes' if has_ga else 'No'}")

    # Check for SC credentials
    has_sc = hasattr(client, 'sc_credentials')
    print(f"  - SC credentials: {'Yes' if has_sc else 'No'}")

    # Check for Ads credentials
    has_ads = hasattr(client, 'ads_credentials')
    print(f"  - Ads credentials: {'Yes' if has_ads else 'No'}")

    print("")

# Print a clear completion message
print("\n===================================================")
print("SCRIPT COMPLETED SUCCESSFULLY")
print("===================================================\n")
