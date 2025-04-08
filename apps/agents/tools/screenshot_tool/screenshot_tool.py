import os
import logging
import base64
from typing import Any, Type, Dict
from pydantic import BaseModel, Field, ConfigDict
from apps.agents.tools.base_tool import BaseTool
from django.conf import settings
from core.storage import SecureFileStorage
from django.core.files.base import ContentFile
from urllib.parse import urlparse
import re

from apps.agents.utils.scraper_adapters.playwright_adapter import PlaywrightAdapter

"""
Screenshot tool for capturing website screenshots using Playwright.

You can use the ScreenshotTool by
 1. importing 'from apps.agents.tools.screenshot_tool import screenshot_tool'' and
 2. calling its run method with a URL as the argument: 'result = screenshot_tool.run(url=url)'
"""

logger = logging.getLogger(__name__)

# Instantiate SecureFileStorage for screenshots
screenshot_storage = SecureFileStorage(private=True, collection='crawled_screenshots')

class ScreenshotToolSchema(BaseModel):
    """Input schema for ScreenshotTool."""
    model_config = ConfigDict(
        extra='forbid',
        arbitrary_types_allowed=True
    )

    url: str = Field(description="The URL of the website to capture a screenshot.")
    mobile: bool = Field(default=False, description="Whether to use mobile emulation.")
    full_page: bool = Field(default=True, description="Whether to capture the full page or just the viewport.")
    timeout: int = Field(default=60000, description="Timeout in milliseconds.")
    stealth: bool = Field(default=True, description="Whether to use stealth mode.")

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
        mobile: bool = False,
        full_page: bool = True,
        timeout: int = 60000,
        stealth: bool = True,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Run the screenshot tool and save to cloud storage.

        Args:
            url: The URL to screenshot
            mobile: Whether to use mobile emulation
            full_page: Whether to capture the full page or just the viewport
            timeout: Timeout in milliseconds
            stealth: Whether to use stealth mode
            **kwargs: Additional arguments

        Returns:
            dict: Contains either the screenshot URL or an error message
        """
        try:
            # Check if screenshot already exists
            existing_url = self._check_screenshot_exists(url)
            if existing_url:
                logger.info(f"Using existing screenshot for URL: {url}")
                return {'screenshot_url': existing_url}

            # Initialize the Playwright adapter
            adapter = PlaywrightAdapter()

            # Setup additional parameters
            additional_params = {
                'fullPage': full_page
            }

            # Request screenshot from Playwright
            result = adapter.scrape(
                url=url,
                formats=['screenshot'],
                timeout=timeout,
                mobile=mobile,
                stealth=stealth,
                **additional_params
            )

            # Check for errors
            if 'error' in result:
                error_msg = f"Failed to get screenshot: {result['error']}"
                logger.error(error_msg)
                return {'error': error_msg}

            # Check if screenshot was returned
            if 'screenshot' not in result:
                error_msg = "No screenshot data in response"
                logger.error(error_msg)
                return {'error': error_msg}

            # Get screenshot data
            screenshot_data = result['screenshot']

            if not screenshot_data:
                error_msg = "No screenshot data in response"
                logger.error(error_msg)
                return {'error': error_msg}

            # Generate a sanitized filename based on the URL
            parsed_url = urlparse(url)
            sanitized_name = re.sub(r'[^\w\-_\. ]', '_', parsed_url.netloc + parsed_url.path)
            filename = f"{sanitized_name[:200]}.png"  # Limit filename length

            # Create the relative path for cloud storage
            relative_path = os.path.join('crawled_screenshots', filename)

            try:
                # Convert base64 screenshot data to bytes and save
                import base64
                screenshot_bytes = base64.b64decode(screenshot_data.split(',')[1] if ',' in screenshot_data else screenshot_data)

                # Save the image using SecureFileStorage
                saved_path = screenshot_storage._save(relative_path, ContentFile(screenshot_bytes))

                # Generate the URL for the saved image using SecureFileStorage
                image_url = screenshot_storage.url(saved_path)

                logger.info(f"Screenshot saved successfully: {saved_path}")
                return {'screenshot_url': image_url}

            except Exception as e:
                error_msg = f"Error saving screenshot: {str(e)}"
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
            # Use the collection defined in screenshot_storage instance implicitly
            # relative_path = os.path.join('crawled_screenshots', filename)
            # Construct path without the collection prefix, SecureFileStorage adds it
            relative_path_in_collection = filename

            # Check existence using SecureFileStorage
            if screenshot_storage.exists(relative_path_in_collection):
                # Get URL using SecureFileStorage
                return screenshot_storage.url(relative_path_in_collection)
            return None

        except Exception as e:
            logger.error(f"Error checking screenshot existence: {str(e)}")
            return None

# Initialize the tool
screenshot_tool = ScreenshotTool()