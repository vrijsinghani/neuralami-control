#!/usr/bin/env python
"""
Script to fix OAuth credentials after the centralized OAuth implementation.

This script can be run as a Django management command:

python manage.py shell < scripts/fix_oauth_credentials.py
"""

import logging
import sys
import time
from django.db import transaction
from apps.seo_manager.models import Client, GoogleAnalyticsCredentials, SearchConsoleCredentials, GoogleAdsCredentials

# Set up logging to output to console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stdout)
logger = logging.getLogger(__name__)

# Print a clear start message
print("\n===================================================")
print("STARTING OAUTH CREDENTIALS FIX SCRIPT")
print("===================================================\n")

def fix_ga_credentials():
    """Fix Google Analytics credentials"""
    print("Starting GA credentials fix...")
    logger.info("=== Fixing Google Analytics Credentials ===")

    # Get all clients with GA credentials
    clients_with_ga = Client.objects.filter(googleanalyticscredentials__isnull=False)
    count = clients_with_ga.count()
    print(f"Found {count} clients with Google Analytics credentials")
    logger.info(f"Found {count} clients with Google Analytics credentials")

    for client in clients_with_ga:
        try:
            with transaction.atomic():
                ga_credentials = client.googleanalyticscredentials
                logger.info(f"Fixing GA credentials for client: {client.name}")

                # Ensure scopes are set correctly
                from apps.seo_manager.models import OAuthManager
                if not ga_credentials.scopes:
                    ga_credentials.scopes = [
                        OAuthManager.OAUTH_SCOPES['analytics']['readonly'],
                        OAuthManager.OAUTH_SCOPES['analytics']['full'],
                        OAuthManager.OAUTH_SCOPES['common']['email']
                    ]
                    ga_credentials.save(update_fields=['scopes'])
                    logger.info(f"Updated scopes for {client.name}")

                # Test the credentials
                try:
                    service = ga_credentials.get_service()
                    if service:
                        logger.info(f"Successfully created analytics service for {client.name}")
                    else:
                        logger.warning(f"Failed to create analytics service for {client.name}")
                except Exception as e:
                    logger.error(f"Error testing GA credentials for {client.name}: {str(e)}")
        except Exception as e:
            logger.error(f"Error fixing GA credentials for {client.name}: {str(e)}")

def fix_sc_credentials():
    """Fix Search Console credentials"""
    print("Starting SC credentials fix...")
    logger.info("\n=== Fixing Search Console Credentials ===")

    # Get all clients with SC credentials
    clients_with_sc = Client.objects.filter(searchconsolecredentials__isnull=False)
    count = clients_with_sc.count()
    print(f"Found {count} clients with Search Console credentials")
    logger.info(f"Found {count} clients with Search Console credentials")

    for client in clients_with_sc:
        try:
            with transaction.atomic():
                sc_credentials = client.searchconsolecredentials
                logger.info(f"Fixing SC credentials for client: {client.name}")

                # Ensure scopes are set correctly
                from apps.seo_manager.models import OAuthManager
                if not sc_credentials.scopes:
                    sc_credentials.scopes = [
                        OAuthManager.OAUTH_SCOPES['search_console']['readonly'],
                        OAuthManager.OAUTH_SCOPES['common']['email']
                    ]
                    sc_credentials.save(update_fields=['scopes'])
                    logger.info(f"Updated scopes for {client.name}")

                # Test the credentials
                try:
                    service = sc_credentials.get_service()
                    if service:
                        logger.info(f"Successfully created search console service for {client.name}")
                    else:
                        logger.warning(f"Failed to create search console service for {client.name}")
                except Exception as e:
                    logger.error(f"Error testing SC credentials for {client.name}: {str(e)}")
        except Exception as e:
            logger.error(f"Error fixing SC credentials for {client.name}: {str(e)}")

def fix_ads_credentials():
    """Fix Google Ads credentials"""
    print("Starting Ads credentials fix...")
    logger.info("\n=== Fixing Google Ads Credentials ===")

    # Get all clients with Ads credentials
    clients_with_ads = Client.objects.filter(googleadscredentials__isnull=False)
    count = clients_with_ads.count()
    print(f"Found {count} clients with Google Ads credentials")
    logger.info(f"Found {count} clients with Google Ads credentials")

    for client in clients_with_ads:
        try:
            with transaction.atomic():
                ads_credentials = client.googleadscredentials
                logger.info(f"Fixing Ads credentials for client: {client.name}")

                # Ensure scopes are set correctly
                from apps.seo_manager.models import OAuthManager
                if not ads_credentials.scopes:
                    ads_credentials.scopes = [
                        OAuthManager.OAUTH_SCOPES['adwords']['full'],
                        OAuthManager.OAUTH_SCOPES['common']['email']
                    ]
                    ads_credentials.save(update_fields=['scopes'])
                    logger.info(f"Updated scopes for {client.name}")

                # Test the credentials
                try:
                    creds_dict = ads_credentials.get_credentials()
                    if creds_dict:
                        logger.info(f"Successfully created ads credentials for {client.name}")
                    else:
                        logger.warning(f"Failed to create ads credentials for {client.name}")
                except Exception as e:
                    logger.error(f"Error testing Ads credentials for {client.name}: {str(e)}")
        except Exception as e:
            logger.error(f"Error fixing Ads credentials for {client.name}: {str(e)}")

def main():
    """Run all fixes"""
    print("Starting main function...")
    logger.info("=== Starting OAuth Credentials Fix ===")

    # Fix Google Analytics credentials
    fix_ga_credentials()

    # Fix Search Console credentials
    fix_sc_credentials()

    # Fix Google Ads credentials
    fix_ads_credentials()

    logger.info("=== Fix Complete ===")
    logger.info("If you see any warnings above, please address them before proceeding.")
    logger.info("If all fixes passed, your OAuth credentials should now be working correctly.")
    logger.info("If you still have issues, you may need to reauthorize your Google accounts.")

    # Print a clear completion message
    print("\n===================================================")
    print("SCRIPT COMPLETED SUCCESSFULLY")
    print("===================================================\n")

if __name__ == "__main__":
    main()
