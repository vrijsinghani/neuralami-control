import os
import requests
from typing import Any, Type, List, Dict, Optional
from pydantic import BaseModel, Field, ConfigDict
from apps.agents.tools.base_tool import BaseTool
import logging
import pandas as pd
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

BASE_URL = os.getenv('DATAFORSEO_BASE_URL', 'https://api.dataforseo.com')

class CompetitorsDomainInput(BaseModel):
    model_config = ConfigDict(
        extra='ignore',
        arbitrary_types_allowed=True
    )
    
    website_url: str = Field(description="Fully qualified domain name (FQDN) for competitor analysis")
    # location_code: int = Field(default=2840, description="Location code for the analysis")
    # language_code: str = Field(default="en", description="Language code for the analysis")
    # min_intersection_percentile: float = Field(
    #     default=25.0,
    #     description="Minimum percentile for keyword intersections (0-100)",
    #     ge=0.0,
    #     le=100.0
    # )
    # max_traffic_ratio: float = Field(
    #     default=100.0,
    #     description="Maximum ratio of competitor's traffic value to target site's traffic value",
    #     gt=0.0
    # )

class CompetitorsDomainTool(BaseTool):
    model_config = ConfigDict(
        extra='ignore',
        arbitrary_types_allowed=True
    )
    
    name: str = "Competitors Domain"
    description: str = "Provides a list of competitor domains with various metrics"
    args_schema: Type[BaseModel] = CompetitorsDomainInput

    @staticmethod
    def get_fqdn(url: str) -> str:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc or parsed_url.path
        
        # Remove www. prefix if present
        if domain.startswith('www.'):
            domain = domain[4:]
            
        return domain

    def _run(self, website_url: str, location_code: int = 2840, language_code: str = "en", 
             min_intersection_percentile: float = 25.0, max_traffic_ratio: float = 100.0, **kwargs: Any) -> Any:
        login, password = KeywordTools._dataforseo_credentials()
        cred = (login, password)
        url = f"{BASE_URL}/v3/dataforseo_labs/google/competitors_domain/live"
        
        # Extract FQDN from the provided URL
        fqdn = self.get_fqdn(website_url)
        
        payload = [
            {
                "target": fqdn,
                "location_code": location_code,
                "language_code": language_code,
                "exclude_top_domains": False,
                "include_clickstream_data": False,
                "item_types": ["organic"],
                "limit": 100,
                "order_by": ["intersections,desc"]
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
            results = self._transform_competitor_data(
                response.json(), 
                website_url, 
                min_intersection_percentile, 
                max_traffic_ratio
            )
        except Exception as e:
            logger.error(f"Error transforming competitor data: {e}")
            raise e

        return results

    def _transform_competitor_data(self, data: Dict, website_url: str, 
                                  min_intersection_percentile: float = 25.0, 
                                  max_traffic_ratio: float = 100.0) -> str:
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
            df['avg_position'] = df['avg_position'].round(2)
            df['etv'] = df['full_domain_metrics'].apply(lambda x: x['organic']['etv'])
            df['estimated_paid_traffic_cost'] = df['full_domain_metrics'].apply(lambda x: x['organic']['estimated_paid_traffic_cost'])
            df['rank_distribution_top_10'] = df['full_domain_metrics'].apply(lambda x: x['organic']['pos_4_10'])
            df['rank_distribution_11_20'] = df['full_domain_metrics'].apply(lambda x: x['organic']['pos_11_20'])
            df['rank_distribution_21_100'] = df['full_domain_metrics'].apply(lambda x: sum(x['organic'][f'pos_{i}_{i+9}'] for i in range(21, 100, 10)))

            # Get target site's metrics
            target_domain = self.get_fqdn(website_url)
            target_df = df[df['domain'] == target_domain]
            
            if target_df.empty:
                return f"Error: Target domain '{target_domain}' not found in the API results. Please verify the domain is correct."
            
            target_site = target_df.iloc[0]
            target_etv = target_site['etv']

            # Calculate intersection percentile threshold
            min_intersections = df['intersections'].quantile(min_intersection_percentile / 100)

            # Filter for relevant competitors
            df = df[
                # Must have meaningful intersection (keyword overlap)
                (df['intersections'] >= min_intersections) &
                # Filter based on relative traffic value
                (df['etv'] <= target_etv * max_traffic_ratio)
            ]

            # Sort by relevance (using intersections as primary metric)
            df = df.sort_values('intersections', ascending=False)

            # Define the columns to include in the output
            columns = [
                'domain', 'avg_position', 'intersections', 'etv', 
                'estimated_paid_traffic_cost', 'rank_distribution_top_10', 
                'rank_distribution_11_20', 'rank_distribution_21_100'
            ]
            result_df = df[columns]

            # Convert the DataFrame to CSV format
            csv_output = result_df.to_csv(index=False)
            return csv_output

        except Exception as e:
            logger.error(f"Error transforming competitor data: {e}")
            return f"Error: {str(e)}"

class KeywordTools:
    @staticmethod
    def _dataforseo_credentials():
        login = os.environ["DATAFORSEO_EMAIL"]
        password = os.environ["DATAFORSEO_PASSWORD"]
        return login, password
