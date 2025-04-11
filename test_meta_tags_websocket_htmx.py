#!/usr/bin/env python
"""
Test script for meta tags WebSocket communication with HTMX.
Run this script with: python manage.py shell < test_meta_tags_websocket_htmx.py
"""

import json
import logging
import time
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()

# Get the first user
User = get_user_model()
user = User.objects.first()

print("\n\n=== Testing meta tags WebSocket messaging with HTMX ===\n")

try:
    # Create a mock task ID
    mock_task_id = "test_task_789"
    
    # Get the channel layer
    channel_layer = get_channel_layer()
    
    # Create a group name for the task
    group_name = f"metatags_task_{mock_task_id}"
    
    print(f"Sending a series of progress updates to group {group_name}...")
    
    # Send a series of progress updates
    for i in range(0, 101, 20):
        progress_data = {
            'percent': float(i),
            'step': 1 if i < 50 else 2,
            'action': 'Finding sitemaps and crawling website' if i < 50 else 'Processing URLs',
            'urls_found': 10,
            'urls_processed': int(i / 10),
            'total_urls': 10
        }
        
        print(f"\nSending progress update ({i}%):")
        print(json.dumps(progress_data, indent=2))
        
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'progress_update',
                'progress': progress_data
            }
        )
        
        # Sleep to simulate real-time updates
        time.sleep(1)
    
    print("\nSending status update (complete):")
    status_data = {
        'type': 'status_update',
        'status': 'complete',
        'result': {
            'success': True,
            'file_path': f"{user.id}/meta-tags/test_websocket_htmx.csv",
            'url': 'https://example.com'
        },
        'message': 'Meta tags snapshot completed successfully.'
    }
    print(json.dumps(status_data, indent=2))
    
    async_to_sync(channel_layer.group_send)(
        group_name,
        status_data
    )
    
    print("\nTest messages sent successfully.")
    print("Check the browser console for WebSocket messages.")
    
except Exception as e:
    print(f"\nError: {str(e)}")
    import traceback
    traceback.print_exc()

print("\n=== Test completed ===")
