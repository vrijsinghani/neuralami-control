#!/usr/bin/env python
"""
Test script for meta tags progress tracking.
Run this script with: python manage.py shell < test_meta_tags_progress.py
"""

import logging
import time
from django.contrib.auth import get_user_model
from apps.seo_manager.tasks import ProgressTracker, send_progress_update
from apps.seo_manager.sitemap_extractor import extract_sitemap_and_meta_tags_from_url

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()

# Get the first user
User = get_user_model()
user = User.objects.first()

# Test URL
test_url = "https://www.example.com"

print("\n\n=== Testing meta tags progress tracking ===\n")

try:
    # Create a mock task ID
    mock_task_id = "test_task_123"
    
    # Create a progress tracker
    progress = ProgressTracker(mock_task_id)
    progress.update(step=1, action="Initializing test extraction")
    
    # Define a progress callback that uses our progress tracker
    def progress_callback(action, urls_found=None, urls_processed=None, total_urls=None):
        print(f"Progress callback: {action}")
        if urls_found is not None:
            print(f"  URLs found: {urls_found}")
        if urls_processed is not None:
            print(f"  URLs processed: {urls_processed}/{total_urls}")
        
        # Update step based on action
        step = progress.current_step
        if "Finding sitemaps" in action:
            step = 1
        elif "Processing URLs" in action:
            step = 2
        elif "Saving results" in action:
            step = 3
            
        # Update the progress tracker
        progress.update(
            step=step,
            action=action,
            urls_found=urls_found,
            urls_processed=urls_processed,
            total_urls=total_urls
        )
    
    # Set up file path
    import os
    from datetime import datetime
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    filename = f"test_progress_{timestamp}.csv"
    relative_path = f"{user.id}/meta-tags/{filename}"
    
    print(f"Starting extraction with progress tracking...")
    
    # Run the extraction with progress callback
    file_path = extract_sitemap_and_meta_tags_from_url(
        test_url,
        user,
        output_file=relative_path,
        progress_callback=progress_callback
    )
    
    print(f"\nSuccess! File saved to: {file_path}")
    
except Exception as e:
    print(f"\nError: {str(e)}")
    import traceback
    traceback.print_exc()

print("\n=== Test completed ===")
