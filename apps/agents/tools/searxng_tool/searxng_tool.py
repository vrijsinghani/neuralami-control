import os
import requests
import json
from typing import Any, Type, Optional
from pydantic import BaseModel, Field, ConfigDict
from crewai_tools.tools.base_tool import BaseTool

class SearxNGToolSchema(BaseModel):
    """Input schema for SearxNGSearchTool."""
    model_config = ConfigDict(
        extra='forbid',
        arbitrary_types_allowed=True
    )
    
    search_query: str = Field(description="The search query to be used.")

class SearxNGSearchTool(BaseTool):
    model_config = ConfigDict(
        extra='forbid',
        arbitrary_types_allowed=True
    )
    
    name: str = "Search the internet"
    description: str = "Searches the internet displaying titles, links, snippets, engines, and categories."
    args_schema: Type[BaseModel] = SearxNGToolSchema
    search_url: str = "https://search.neuralami.com"
    n_results: Optional[int] = None

    def _run(
        self, 
        search_query: str, 
        **kwargs: Any
    ) -> Any:
        payload = {        
            'q': search_query,
            'format': 'json',
            'pageno': '1',
            'language': 'en-US'
        }
        response = requests.get(self.search_url, params=payload)
        if response.ok:
            results = response.json()['results']
            formatted_results = []
            for result in results:
                try:
                    engines = ', '.join(result['engines']) if 'engines' in result else 'N/A'
                    formatted_results.append('\n'.join([
                        f"Title: {result.get('title', 'No Title')}",
                        f"Link: {result.get('url', 'No Link')}",
                        f"Score: {result.get('score', 'No Score')}",
                        f"Snippet: {result.get('content', 'No Snippet')}",
                        f"Engines: {engines}",
                        f"Category: {result.get('category', 'No Category')}",
                        "---"
                    ]))
                except KeyError as e:
                    print(f"Skipping an entry due to missing key: {e}")
                    continue

            content = '\n'.join(formatted_results)
            return f"Search results:\n{content}"
        else:
            return f"Failed to fetch search results. Status code: {response.status_code}"