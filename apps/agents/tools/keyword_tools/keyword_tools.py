import os
import requests
from typing import Any, Type, List, Dict, Tuple, Optional, Union
from pydantic import BaseModel, Field, ConfigDict, field_validator
from crewai.tools import BaseTool
import logging
import json
import csv
import io
import pandas as pd
import numpy as np
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

BASE_URL = os.getenv('DATAFORSEO_BASE_URL', 'https://api.dataforseo.com')

class KeywordsForSiteInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        arbitrary_types_allowed=True
    )
    
    website_url: str = Field(description="Fully qualified domain name (FQDN) for keyword analysis")

    @classmethod
    def get_fqdn(cls, url: str) -> str:
        parsed_url = urlparse(url)
        return parsed_url.netloc or parsed_url.path

class KeywordSuggestionsInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        arbitrary_types_allowed=True
    )
    
    seed_keyword: str = Field(description="Seed keyword for suggestions")
    filters: List[Tuple[str, str, float]] = Field(description="List of filters", default=[])

class KeywordIdeasInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        arbitrary_types_allowed=True
    )
    
    keywords: List[str] = Field(description="Single keyword or list of keywords")
    filters: List[Tuple[str, str, float]] = Field(description="List of filters", default=[])

    @field_validator('keywords', mode='before')
    @classmethod
    def validate_keywords(cls, value):
        if isinstance(value, str):
            return [value]
        return value

class SearchVolumeInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        arbitrary_types_allowed=True
    )
    
    keywords: List[str] = Field(description="Single keyword or list of keywords to get search volume for")
    sort_by: str = Field(default="relevance", description="Sort results by this field")

    @field_validator('keywords', mode='before')
    @classmethod
    def validate_keywords(cls, value):
        if isinstance(value, str):
            return [value]
        return value

class KeywordsForSiteTool(BaseTool):
    model_config = ConfigDict(
        extra='forbid',
        arbitrary_types_allowed=True
    )
    
    name: str = "Keywords for Site"
    description: str = "Provides a list of keywords relevant to the target domain. Each keyword is supplied with relevant categories, search volume data for the last month, cost-per-click, competition, and search volume trend values for the past 12 months"
    args_schema: Type[BaseModel] = KeywordsForSiteInput

    def _run(self, website_url: str, **kwargs: Any) -> Any:
        login, password = KeywordTools._dataforseo_credentials()
        cred = (login, password)
        url = f"{BASE_URL}/v3/keywords_data/google_ads/keywords_for_site/live"
        
        fqdn = KeywordsForSiteInput.get_fqdn(website_url)
        
        payload = [
            {
                "target": fqdn,
                "language_code": "en",
                "location_code": 2840,
            }
        ]
        headers = {"Content-Type": "application/json"}
        try:
            response = requests.post(url, json=payload, headers=headers, auth=cred)
            response.raise_for_status()

        except Exception as e:
            logger.error(f"Error making request to DataForSEO: {e}")
            raise e

        try:
            results = KeywordTools._transform_keyword_data(response.json())
        except Exception as e:
            logger.error(f"Error transforming keyword data: {e}")
            raise e

        return results

    async def _arun(self, target: str, **kwargs: Any) -> Any:
        raise NotImplementedError("KeywordsForSiteTool does not support async")

class KeywordSuggestionsTool(BaseTool):
    model_config = ConfigDict(
        extra='forbid',
        arbitrary_types_allowed=True
    )
    
    name: str = "Keyword Suggestions"
    description: str = "Provides a list of keywords relevant to the target domain. Each keyword is supplied with relevant categories, search volume data for the last month, cost-per-click, competition, and search volume trend values for the past 12 months"
    args_schema: Type[BaseModel] = KeywordSuggestionsInput

    def _run(self, seed_keyword: str, filters: List = None, **kwargs: Any) -> Any:
        login, password = KeywordTools._dataforseo_credentials()
        cred = (login, password)
        url = f"{BASE_URL}/v3/dataforseo_labs/google/keyword_suggestions/live"
        payload = [
            {
                "keyword": seed_keyword,
                "location_code": 2840,
                "language_code": "en",
                "include_serp_info": True,
                "include_seed_keyword": True,
                "limit": 50,
            }
        ]
        if filters:
            payload[0]["filters"] = filters
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, json=payload, headers=headers, auth=cred)
        response.raise_for_status()
        
        try:
            results = KeywordTools._transform_keyword_data(response.json())
        except Exception as e:
            logger.error(f"Error transforming keyword data: {e}")
            raise e
        
        return results

    async def _arun(self, seed_keyword: str, filters: List = None, **kwargs: Any) -> Any:
        raise NotImplementedError("KeywordSuggestionsTool does not support async")

class KeywordIdeasTool(BaseTool):
    model_config = ConfigDict(
        extra='forbid',
        arbitrary_types_allowed=True
    )
    
    name: str = "Keyword Ideas"
    description: str = "Provides search terms that are relevant to the product or service categories of the specified keywords. The algorithm selects the keywords which fall into the same categories as the seed keywords specified"
    args_schema: Type[BaseModel] = KeywordIdeasInput

    def _run(self, keywords: List[str], filters: List[Tuple[str, str, float]] = None, **kwargs: Any) -> Any:
        login, password = KeywordTools._dataforseo_credentials()
        cred = (login, password)
        url = f"{BASE_URL}/v3/dataforseo_labs/google/keyword_ideas/live"
        payload = [
            {
                "keywords": keywords,
                "location_code": 2840,
                "language_code": "en",
                "include_serp_info": True,
                "limit": 100,
            }
        ]
        if filters:
            payload[0]["filters"] = filters
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, json=payload, headers=headers, auth=cred)
        response.raise_for_status()

        try:
            results = KeywordTools._transform_keyword_data(response.json())
        except Exception as e:
            logger.error(f"Error transforming keyword data: {e}")
            raise e
        return results

    async def _arun(self, keywords: List[str], filters: List[Tuple[str, str, float]] = None, **kwargs: Any) -> Any:
        raise NotImplementedError("KeywordIdeasTool does not support async")

class SearchVolumeTool(BaseTool):
    model_config = ConfigDict(
        extra='forbid',
        arbitrary_types_allowed=True
    )
    
    name: str = "Search Volume"
    description: str = "Provides search volume data for a list of keywords"
    args_schema: Type[BaseModel] = SearchVolumeInput

    def _run(self, keywords: List[str], sort_by: str = "relevance", **kwargs: Any) -> Any:
        login, password = KeywordTools._dataforseo_credentials()
        cred = (login, password)
        url = f"{BASE_URL}/v3/keywords_data/google_ads/search_volume/live"
        payload = [
            {
                "keywords": keywords,
                "sort_by": sort_by
            }
        ]
        headers = {"Content-Type": "application/json"}
        try:
            response = requests.post(url, json=payload, headers=headers, auth=cred)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Error making request to DataForSEO: {e}")
            raise e

        try:
            results = KeywordTools._transform_keyword_data(response.json())
        except Exception as e:
            logger.error(f"Error transforming keyword data: {e}")
            raise e
        return results

    async def _arun(self, keywords: List[str], sort_by: str = "relevance", **kwargs: Any) -> Any:
        raise NotImplementedError("SearchVolumeTool does not support async")

class KeywordTools:
    @staticmethod
    def tools():
        return [KeywordsForSiteTool(), KeywordSuggestionsTool(), KeywordIdeasTool(), SearchVolumeTool()]

    @staticmethod
    def _dataforseo_credentials():
        login = os.environ["DATAFORSEO_EMAIL"]
        password = os.environ["DATAFORSEO_PASSWORD"]
        return login, password

    @staticmethod
    def _transform_keyword_data(data: Dict) -> str:
        try:
            if data.get('tasks_error', 0) > 0:
                error_message = data.get('tasks', [{}])[0].get('status_message', 'Unknown error')
                return f"Error: {error_message}"

            path = data.get('tasks', [{}])[0].get('path', [])
            if len(path) >= 4:
                tool_type = path[3]
            else:
                return "Error: Unable to determine tool type from response"

            if tool_type == "keywords_for_site":
                all_results = data.get('tasks', [])[0].get('result', [])
            elif tool_type in ["keyword_suggestions", "keyword_ideas"]:
                result = data.get('tasks', [])[0].get('result', [])
                if result:
                    all_results = result[0].get('items', [])
                else:
                    return "Error: No results found in the response"
            elif tool_type == "search_volume":
                all_results = data.get('tasks', [])[0].get('result', [])
            else:
                return f"Error: Unknown tool type: {tool_type}"

            if not all_results:
                return "Error: No results found in the response"

            df = pd.DataFrame(all_results)

            columns = ['keyword', 'search_volume', 'cpc', 'competition']
            if 'keyword_info' in df.columns:
                df['search_volume'] = df['keyword_info'].apply(lambda x: x.get('search_volume', 0))
                df['cpc'] = df['keyword_info'].apply(lambda x: x.get('cpc', 0))
                df['competition'] = df['keyword_info'].apply(lambda x: x.get('competition', 0))
            if 'keyword_properties' in df.columns:
                df['keyword_difficulty'] = df['keyword_properties'].apply(lambda x: x.get('keyword_difficulty', 0))
                columns.append('keyword_difficulty')
            if 'low_top_of_page_bid' in df.columns:
                columns.extend(['low_top_of_page_bid', 'high_top_of_page_bid'])

            result_df = df[columns]
            result_df = result_df.rename(columns={
                'search_volume': 'avg_search_volume',
                'keyword_difficulty': 'difficulty',
                'low_top_of_page_bid': 'low_top_bid',
                'high_top_of_page_bid': 'high_top_bid'
            })

            if 'competition' in result_df.columns and result_df['competition'].dtype == 'object':
                competition_map = {'LOW': 0, 'MEDIUM': 0.5, 'HIGH': 1}
                result_df['competition'] = result_df['competition'].map(competition_map)

            fill_values = {col: 0 for col in result_df.columns if col != 'keyword'}
            fill_values['keyword'] = 'N/A'
            result_df = result_df.fillna(fill_values)

            result_df = result_df.sort_values('cpc', ascending=False)
            result_df = result_df[result_df['avg_search_volume'] >= 500]

            csv_output = result_df.to_csv(index=False)
            return csv_output

        except Exception as e:
            logger.error(f"Error transforming keyword data: {e}")
            return f"Error: {str(e)}"
