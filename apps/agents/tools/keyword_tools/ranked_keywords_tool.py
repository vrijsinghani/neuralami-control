import os
import requests
from typing import Any, Type, List, Dict
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
import logging
import pandas as pd
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

BASE_URL = os.getenv('DATAFORSEO_BASE_URL', 'https://api.dataforseo.com')

class RankedKeywordsInput(BaseModel):
    """Input model for ranked keywords tool"""
    website_url: str = Field(description="Domain or webpage for keyword ranking analysis")
    model_config = {
        "arbitrary_types_allowed": True
    }

    @classmethod
    def get_fqdn(cls, url: str) -> str:
        parsed_url = urlparse(url)
        return parsed_url.netloc or parsed_url.path

class RankedKeywordsTool(BaseTool):
    name: str = "Ranked Keywords"
    description: str = "Provides a list of ranked keywords with various metrics"
    args_schema: Type[BaseModel] = RankedKeywordsInput

    def _run(self, website_url: str, location_code: int = 2840, language_code: str = "en", **kwargs: Any) -> Any:
        login, password = KeywordTools._dataforseo_credentials()
        cred = (login, password)
        url = f"{BASE_URL}/v3/dataforseo_labs/google/ranked_keywords/live"
        fqdn = RankedKeywordsInput.get_fqdn(website_url)

        payload = [
            {
                "target": fqdn,
                "location_code": location_code,
                "language_code": language_code,
                "limit": 100,
                "order_by": ["keyword_data.keyword_info.search_volume,desc"]
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
            results = self._transform_keyword_data(response.json())
        except Exception as e:
            logger.error(f"Error transforming keyword data: {e}")
            raise e

        return results

    def _transform_keyword_data(self, data: Dict) -> str:
        try:
            if data.get('tasks_error', 0) > 0:
                error_message = data.get('tasks', [{}])[0].get('status_message', 'Unknown error')
                return f"Error: {error_message}"

            all_results = data.get('tasks', [])[0].get('result', [])[0].get('items', [])
            if not all_results:
                return "Error: No results found in the response"

            # Create a DataFrame from the results
            df = pd.DataFrame(all_results)

            # Extract necessary fields and calculate additional metrics
            df['keyword'] = df['keyword_data'].apply(lambda x: x.get('keyword', 'N/A'))
            df['search_volume'] = df['keyword_data'].apply(lambda x: x.get('keyword_info', {}).get('search_volume', 0))
            df['keyword_difficulty'] = df['keyword_data'].apply(lambda x: x.get('keyword_properties', {}).get('keyword_difficulty', 0))
            df['competition_level'] = df['keyword_data'].apply(lambda x: x.get('keyword_info', {}).get('competition_level', 'N/A'))
            df['main_intent'] = df['keyword_data'].apply(lambda x: x.get('search_intent_info', {}).get('main_intent', 'N/A'))
            df['absolute_rank'] = df['ranked_serp_element'].apply(lambda x: x.get('serp_item', {}).get('rank_absolute', 0))
            df['etv'] = df['ranked_serp_element'].apply(lambda x: x.get('serp_item', {}).get('etv', 0))
            df['cpc'] = df['keyword_data'].apply(lambda x: x.get('keyword_info', {}).get('cpc', 0))

            # Define the columns to include in the output
            columns = [
                'keyword', 'search_volume', 'keyword_difficulty', 'competition_level',
                'main_intent', 'absolute_rank', 'etv'
            ]
            result_df = df[columns]

            # Convert the DataFrame to CSV format
            csv_output = result_df.to_csv(index=False, lineterminator='\n')
            return csv_output

        except Exception as e:
            logger.error(f"Error transforming keyword data: {e}")
            return f"Error: {str(e)}"

class KeywordTools:
    @staticmethod
    def _dataforseo_credentials():
        login = os.environ["DATAFORSEO_EMAIL"]
        password = os.environ["DATAFORSEO_PASSWORD"]
        return login, password
