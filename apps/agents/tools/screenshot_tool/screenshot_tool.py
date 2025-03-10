import os
import requests
import json
from typing import Any, Type
from pydantic import BaseModel, Field, ConfigDict
from apps.agents.tools.base_tool import BaseTool
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from urllib.parse import urlparse
import re
import logging
"""
You can use the ScreenshotTool by 
 1. importing 'from apps.agents.tools.screenshot_tool import screenshot_tool'' and 
 2. calling its run method with a URL as the argument: 'result = screenshot_tool.run(url=url)'
 """

logger = logging.getLogger(__name__)

class ScreenshotToolSchema(BaseModel):
    """Input schema for ScreenshotTool."""
    model_config = ConfigDict(
        extra='forbid',
        arbitrary_types_allowed=True
    )
    
    url: str = Field(description="The URL of the website to capture a screenshot.")

class ScreenshotTool(BaseTool):
    model_config = ConfigDict(
        extra='forbid',
        arbitrary_types_allowed=True
    )
    
    name: str = "Capture Website Screenshot"
    description: str = "Captures a screenshot of a given website URL."
    args_schema: Type[BaseModel] = ScreenshotToolSchema
    
    def _run(
        self, 
        url: str, 
        **kwargs: Any
    ) -> Any:
        """
        Run the screenshot tool and save to cloud storage.
        
        Args:
            url: The URL to screenshot
            **kwargs: Additional arguments
            
        Returns:
            dict: Contains either the screenshot URL or an error message
        """
        try:
            browserless_url = os.getenv('BROWSERLESS_BASE_URL')
            api_key = os.getenv('BROWSERLESS_API_KEY')
            
            if not browserless_url or not api_key:
                logger.error("Browserless configuration is missing")
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
                
                # Create the relative path for cloud storage
                relative_path = os.path.join('crawled_screenshots', filename)
                
                try:
                    # Save the image using default_storage
                    default_storage.save(relative_path, ContentFile(response.content))
                    
                    # Generate the URL for the saved image
                    image_url = default_storage.url(relative_path)
                    
                    logger.info(f"Screenshot saved successfully: {relative_path}")
                    return {'screenshot_url': image_url}
                    
                except Exception as e:
                    error_msg = f"Error saving screenshot: {str(e)}"
                    logger.error(error_msg)
                    return {'error': error_msg}
            else:
                error_msg = f'Failed to get screenshot. Status code: {response.status_code}'
                logger.error(error_msg)
                return {'error': error_msg}
                
        except Exception as e:
            error_msg = f"Error in screenshot tool: {str(e)}"
            logger.error(error_msg)
            return {'error': error_msg}

    def _check_screenshot_exists(self, url: str) -> str:
        """
        Check if a screenshot already exists for the given URL.
        
        Args:
            url: The URL to check
            
        Returns:
            str: The existing screenshot URL if found, None otherwise
        """
        try:
            parsed_url = urlparse(url)
            sanitized_name = re.sub(r'[^\w\-_\. ]', '_', parsed_url.netloc + parsed_url.path)
            filename = f"{sanitized_name[:200]}.png"
            relative_path = os.path.join('crawled_screenshots', filename)
            
            if default_storage.exists(relative_path):
                return default_storage.url(relative_path)
            return None
            
        except Exception as e:
            logger.error(f"Error checking screenshot existence: {str(e)}")
            return None

# Initialize the tool
screenshot_tool = ScreenshotTool()