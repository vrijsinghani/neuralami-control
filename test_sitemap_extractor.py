#!/usr/bin/env python
"""
Test script for sitemap extractor.
Run this script with: python manage.py shell < test_sitemap_extractor.py
"""

import logging
from django.contrib.auth import get_user_model
from apps.seo_manager.sitemap_extractor import extract_sitemap_and_meta_tags_from_url

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()

# Get the first user
User = get_user_model()
user = User.objects.first()

# Test URL
test_url = "https://www.example.com"

print("\n\n=== Testing sitemap extractor ===\n")

try:
    # Define a simple progress callback
    def progress_callback(action, **kwargs):
        print(f"Progress: {action}")
        if kwargs:
            print(f"  Details: {kwargs}")
    
    # Run the extractor
    file_path = extract_sitemap_and_meta_tags_from_url(
        url=test_url,
        user=user,
        progress_callback=progress_callback
    )
    
    print(f"\nSuccess! File saved to: {file_path}")
    
except Exception as e:
    print(f"\nError: {str(e)}")
    import traceback
    traceback.print_exc()

print("\n=== Test completed ===")
