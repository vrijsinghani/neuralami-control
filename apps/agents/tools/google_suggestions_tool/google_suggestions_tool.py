from typing import Any, Type, Optional
from pydantic import BaseModel, Field, ConfigDict
from crewai.tools import BaseTool
import requests
import xml.etree.ElementTree as ET

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
        # Build the Google Search query URL
        search_query = f"is {keyword}"
        google_search_url = f"http://google.com/complete/search?output=toolbar&gl={country_code}&q={search_query}"

        # Call the URL and read the data
        result = requests.get(google_search_url)
        tree = ET.ElementTree(ET.fromstring(result.content))
        root = tree.getroot()

        # Extract the suggestions from the XML response
        suggestions = []
        for suggestion in root.findall('CompleteSuggestion'):
            question = suggestion.find('suggestion').attrib.get('data')
            suggestions.append(question)

        # Return the suggestions as a comma-separated string
        return ", ".join(suggestions)

    async def _arun(self, keyword: str, country_code: str = "us", **kwargs: Any) -> Any:
        """Use the tool asynchronously."""
        raise NotImplementedError("GoogleSuggestionsTool does not support async")
