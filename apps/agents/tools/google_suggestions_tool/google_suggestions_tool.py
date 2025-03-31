from typing import Any, Type, Optional
from pydantic import BaseModel, Field, ConfigDict
from apps.agents.tools.base_tool import BaseTool
import requests
import xml.etree.ElementTree as ET
import logging

logger = logging.getLogger(__name__)

class GoogleSuggestionsInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        arbitrary_types_allowed=True
    )
    
    keyword: str = Field(description="The keyword to get suggestions for")
    country_code: str = Field(default="us", description="The country code for localized suggestions")

class GoogleSuggestionsTool(BaseTool):
    model_config = ConfigDict(
        extra='forbid',
        arbitrary_types_allowed=True
    )
    
    name: str = "Google Suggestions Fetcher"
    description: str = "Retrieves Google search suggestions for a given keyword."
    args_schema: Type[BaseModel] = GoogleSuggestionsInput

    def _run(self, keyword: str, country_code: str = "us", **kwargs: Any) -> Any:
        """Use the tool to get Google search suggestions."""
        logger.debug(f"Running GoogleSuggestionsTool with keyword: '{keyword}', country_code: '{country_code}'")

        # Use default country code if an empty string is provided
        effective_country_code = country_code if country_code else "us"
        logger.debug(f"Effective country code: '{effective_country_code}'")

        # Build the Google Search query URL - Removed "is " prefix
        search_query = keyword # Corrected search query
        google_search_url = f"http://google.com/complete/search?output=toolbar&gl={effective_country_code}&q={search_query}"
        logger.debug(f"Requesting Google Suggestions URL: {google_search_url}")

        suggestions = []
        try:
            # Call the URL and read the data
            result = requests.get(google_search_url, timeout=10) # Added timeout
            logger.debug(f"Google Suggestions response status code: {result.status_code}")

            if result.status_code == 200:
                logger.debug(f"Raw response content: {result.content}")
                # Check if content is valid XML before parsing
                if result.content and result.content.strip():
                    try:
                        tree = ET.ElementTree(ET.fromstring(result.content))
                        root = tree.getroot()

                        # Extract the suggestions from the XML response
                        for suggestion in root.findall('CompleteSuggestion'):
                            suggestion_data = suggestion.find('suggestion').attrib.get('data')
                            if suggestion_data:
                                suggestions.append(suggestion_data)
                        logger.debug(f"Extracted suggestions: {suggestions}")
                    except ET.ParseError as e:
                        logger.error(f"Error parsing XML response: {e}")
                        logger.error(f"Response content that failed parsing: {result.content}")
                        return f"Error: Could not parse suggestions response from Google. Invalid XML received."
                else:
                    logger.warning("Received empty or whitespace-only response from Google Suggestions API.")
                    return "Received empty response from Google Suggestions API."
            else:
                logger.error(f"Google Suggestions API request failed with status code {result.status_code}. Response: {result.text}")
                return f"Error: Google Suggestions request failed with status {result.status_code}."

        except requests.exceptions.RequestException as e:
            logger.error(f"Error during Google Suggestions API request: {e}")
            return f"Error: Could not connect to Google Suggestions API. {e}"
        except Exception as e:
            logger.error(f"An unexpected error occurred in GoogleSuggestionsTool: {e}")
            return f"Error: An unexpected error occurred. {e}"

        # Return the suggestions as a comma-separated string
        output = ", ".join(suggestions)
        logger.info(f"GoogleSuggestionsTool finished successfully. Output: '{output[:100]}...'") # Log truncated output
        return output

    async def _arun(self, keyword: str, country_code: str = "us", **kwargs: Any) -> Any:
        """Use the tool asynchronously."""
        raise NotImplementedError("GoogleSuggestionsTool does not support async")
