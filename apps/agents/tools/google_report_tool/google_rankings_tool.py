import logging
from typing import Any, Type, List, Optional, Dict, Union
from pydantic import BaseModel, Field, field_validator
from apps.agents.tools.base_tool import BaseTool
from datetime import datetime
import json
from googleapiclient.errors import HttpError
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# Remove Django model imports that are only needed for database operations
from django.core.exceptions import ObjectDoesNotExist

# Keep the get_monthly_date_ranges utility
from apps.seo_manager.utils import get_monthly_date_ranges

logger = logging.getLogger(__name__)

class GoogleRankingsToolInput(BaseModel):
    """Input schema for GoogleRankingsTool."""
    start_date: Optional[str] = Field(
        None,
        description="The start date for the analytics data (YYYY-MM-DD). If None, will use the last 12 months."
    )
    end_date: Optional[str] = Field(
        None,
        description="The end date for the analytics data (YYYY-MM-DD). If None, will use the last 12 months."
    )
    search_console_property_url: str = Field(
        description="The Search Console property URL"
    )
    search_console_credentials: Dict[str, Any] = Field(
        description="Credentials for Search Console API"
    )

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_dates(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return value
        except ValueError:
            raise ValueError("Invalid date format. Use YYYY-MM-DD.")

class GoogleRankingsTool(BaseTool):
    name: str = "Google Search Console Rankings Fetcher"
    description: str = "Fetches Google Search Console ranking data for a specified property and date range."
    args_schema: Type[BaseModel] = GoogleRankingsToolInput

    def _run(
        self, 
        start_date: Optional[str], 
        end_date: Optional[str], 
        search_console_property_url: str,
        search_console_credentials: Dict[str, Any],
        **kwargs: Any
    ) -> str:
        """
        Fetch ranking data from Google Search Console without storing in the database.
        Returns the raw data for the caller to process as needed.
        """
        try:
            # Validate credentials
            sc_required_fields = ['sc_client_id', 'client_secret', 'refresh_token']
            sc_missing_fields = [field for field in sc_required_fields if field not in search_console_credentials]
            
            if sc_missing_fields:
                sc_missing_fields_str = ', '.join(sc_missing_fields)
                logger.error(f"Missing required Search Console credential fields: {sc_missing_fields_str}")
                raise ValueError(f"Incomplete Search Console credentials. Missing: {sc_missing_fields_str}")
            
            # Create Search Console service using credentials
            search_console_service = self._create_search_console_service(search_console_credentials)
            if not search_console_service:
                raise ValueError("Failed to initialize Search Console service")
                
            if not search_console_property_url:
                raise ValueError("Missing or invalid Search Console property URL")
            
            # Check if specific dates were provided
            if start_date and end_date:
                date_ranges = [(
                    datetime.strptime(start_date, '%Y-%m-%d').date(),
                    datetime.strptime(end_date, '%Y-%m-%d').date()
                )]
            else:
                # For backfill operations, get last 12 months
                date_ranges = get_monthly_date_ranges(12)
            
            all_keyword_data = []
            
            for range_start, range_end in date_ranges:
                try:
                    logger.info(f"Fetching data for period: {range_start} to {range_end}")
                    
                    keyword_data = self._get_search_console_data(
                        search_console_service, 
                        search_console_property_url, 
                        range_start.strftime('%Y-%m-%d'),
                        range_end.strftime('%Y-%m-%d'),
                        'query'
                    )
                    
                    if keyword_data:  # Only process if we got data
                        all_keyword_data.append({
                            'period': f"{range_start} to {range_end}",
                            'date': range_start.strftime('%Y-%m-%d'),
                            'year': range_start.year,
                            'month': range_start.month,
                            'data': keyword_data
                        })
                    else:
                        logger.warning(f"No keyword data returned for period {range_start} to {range_end}")
                    
                except Exception as e:
                    logger.error(f"Error fetching data for period {range_start} to {range_end}: {str(e)}")
                    if 'invalid_grant' in str(e) or 'expired' in str(e):
                        raise  # Re-raise auth errors to be handled above
                    continue
            
            # Build the response structure
            response = {
                'success': len(all_keyword_data) > 0,
                'property_url': search_console_property_url,
                'periods_fetched': len(date_ranges),
                'periods_with_data': len(all_keyword_data),
                'keyword_data': all_keyword_data
            }
            
            if not all_keyword_data:
                response['error'] = "No ranking data was collected"
            
            return json.dumps(response)
            
        except Exception as e:
            logger.error(f"Error in ranking tool: {str(e)}")
            return json.dumps({
                'success': False,
                'error': str(e)
            })

    def _create_search_console_service(self, credentials: Dict[str, Any]):
        """Create Search Console service from credentials dictionary"""
        try:
            # Create OAuth credentials
            credentials_obj = Credentials(
                None,  # No token
                refresh_token=credentials.get('refresh_token'),
                token_uri='https://oauth2.googleapis.com/token',
                client_id=credentials.get('sc_client_id'),
                client_secret=credentials.get('client_secret')
            )
            
            # Refresh the credentials
            credentials_obj.refresh(Request())
            
            # Create the search console service
            search_console_service = build('searchconsole', 'v1', credentials=credentials_obj)
            return search_console_service
        except Exception as e:
            logger.error(f"Error creating Search Console service: {str(e)}")
            return None

    def _get_search_console_data(self, service, property_url, start_date, end_date, dimension):
        """Fetch data from Google Search Console API"""
        try:
            # Parse the property URL if needed
            if isinstance(property_url, str) and '{' in property_url:
                try:
                    data = json.loads(property_url.replace("'", '"'))  # Replace single quotes with double quotes
                    site_url = data['url']
                except (json.JSONDecodeError, KeyError):
                    site_url = property_url
            elif isinstance(property_url, dict):
                site_url = property_url['url']
            else:
                site_url = property_url

            logger.info(f"Using Search Console property URL: {site_url}")

            response = service.searchanalytics().query(
                siteUrl=site_url,
                body={
                    'startDate': start_date,
                    'endDate': end_date,
                    'dimensions': [dimension],
                    'rowLimit': 1000
                }
            ).execute()
            
            search_console_data = []
            for row in response.get('rows', []):
                search_console_data.append({
                    'Keyword' if dimension == 'query' else 'Landing Page': row['keys'][0],
                    'Clicks': row['clicks'],
                    'Impressions': row['impressions'],
                    'CTR (%)': round(row['ctr'] * 100, 2),
                    'Avg Position': round(row['position'], 1)
                })
            
            search_console_data.sort(key=lambda x: x['Impressions'], reverse=True)
            return search_console_data[:1000]
        except HttpError as error:
            logger.error(f"An error occurred while fetching Search Console data: {error}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching Search Console data: {str(e)}")
            return []
