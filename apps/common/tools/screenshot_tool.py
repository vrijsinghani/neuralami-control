import os
import requests
import json
from typing import Any, Type
from pydantic import BaseModel, Field
from crewai_tools.tools.base_tool import BaseTool
from django.conf import settings
from urllib.parse import urlparse
import re
"""
You can use the ScreenshotTool by 
 1. importing 'from apps.common.tools.screenshot_tool import screenshot_tool'' and 
 2. calling its run method with a URL as the argument: 'result = screenshot_tool.run(url=url)'
 """

class ScreenshotToolSchema(BaseModel):
    """Input schema for ScreenshotTool."""
    url: str = Field(..., description="The URL of the website to capture a screenshot.")

class ScreenshotTool(BaseTool):
    name: str = "Capture Website Screenshot"
    description: str = "Captures a screenshot of a given website URL."
    args_schema: Type[BaseModel] = ScreenshotToolSchema
    
    def _run(
        self, 
        url: str, 
        **kwargs: Any
    ) -> Any:
        browserless_url = os.getenv('BROWSERLESS_BASE_URL')
        api_key = os.getenv('BROWSERLESS_API_KEY')
        
        if not browserless_url or not api_key:
            return {'error': 'Browserless configuration is missing'}
        
        screenshot_url = f"{browserless_url}/screenshot?token={api_key}"
        
        payload = {
            "url": url,
            "options": {
                "fullPage": False,
                "type": "png"
            }
        }
        
        response = requests.post(screenshot_url, json=payload)
        
        if response.status_code == 200:
            # Generate a sanitized filename based on the URL
            parsed_url = urlparse(url)
            sanitized_name = re.sub(r'[^\w\-_\. ]', '_', parsed_url.netloc + parsed_url.path)
            filename = f"{sanitized_name[:200]}.png"  # Limit filename length
            filepath = os.path.join(settings.MEDIA_ROOT, 'crawled_screenshots', filename)
            # Ensure the directory exists
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            # Save the image
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            # Generate the URL for the saved image
            image_url = f"{settings.MEDIA_URL}crawled_screenshots/{filename}"
            
            return {'screenshot_url': image_url}
        else:
            return {'error': f'Failed to get screenshot. Status code: {response.status_code}'}

# Initialize the tool
screenshot_tool = ScreenshotTool()