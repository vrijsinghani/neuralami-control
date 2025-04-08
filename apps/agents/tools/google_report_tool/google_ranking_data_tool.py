import logging
from typing import Any, Type, List, Optional, Dict, Union
from pydantic import BaseModel, Field, field_validator
from apps.agents.tools.base_tool import BaseTool
from datetime import datetime, timedelta
import json
from googleapiclient.errors import HttpError
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from apps.common.utils import DateProcessor

logger = logging.getLogger(__name__)

class GoogleRankingDataToolInput(BaseModel):
    """Input schema for GoogleRankingDataTool."""
    start_date: Optional[str] = Field(
        None,
        description="The start date for the ranking data (YYYY-MM-DD or relative like '90daysAgo'). If None, defaults to 30 days ago."
    )
    end_date: Optional[str] = Field(
        None,
        description="The end date for the ranking data (YYYY-MM-DD or relative like 'yesterday'). If None, defaults to yesterday."
    )
    search_console_property_url: str = Field(
        description="The Search Console property URL"
    )
    search_console_credentials: Dict[str, Any] = Field(
        description="Credentials for Search Console API"
    )
    historical: bool = Field(
        False,
        description="If True, fetches data for the last 12 months in monthly periods. If False, fetches data for the specified date range as a single period."
    )

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_dates(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        try:
            return DateProcessor.process_relative_date(value)
        except ValueError as e:
            raise ValueError(str(e))

class GoogleRankingDataTool(BaseTool):
    name: str = "Google Search Console Rankings Data Fetcher"
    description: str = (
        "Fetches raw keyword ranking data from Google Search Console for a specified property and date range. "
        "Returns the data in a format suitable for storing in the database. "
        "Can fetch either recent data (last 30 days) or historical data (last 12 months in monthly periods)."
    )
    args_schema: Type[BaseModel] = GoogleRankingDataToolInput

    def _run(
        self,
        start_date: Optional[str],
        end_date: Optional[str],
        search_console_property_url: str,
        search_console_credentials: Dict[str, Any],
        historical: bool = False,
        **kwargs: Any
    ) -> str:
        """
        Fetch ranking data from Google Search Console.
        Returns the data in a format suitable for storing in the database.
        """
        try:
            # Validate credentials
            sc_required_fields = ['sc_client_id', 'client_secret', 'refresh_token']
            sc_missing_fields = [field for field in sc_required_fields if field not in search_console_credentials]

            if sc_missing_fields:
                sc_missing_fields_str = ', '.join(sc_missing_fields)
                logger.error(f"Missing required Search Console credential fields: {sc_missing_fields_str}")
                raise ValueError(f"Incomplete Search Console credentials. Missing: {sc_missing_fields_str}")

            # Create Search Console service
            search_console_service = self._create_search_console_service(search_console_credentials)
            if not search_console_service:
                raise ValueError("Failed to initialize Search Console service")

            if not search_console_property_url:
                raise ValueError("Missing or invalid Search Console property URL")

            # Determine date ranges based on historical flag
            if historical:
                # For historical data, fetch the last 12 months in monthly periods
                periods = self._get_monthly_periods(12)
                logger.info(f"Fetching historical data for {len(periods)} monthly periods")
            else:
                # For recent data, use the specified date range or default to last 30 days
                today = datetime.now().date()
                default_end_date = today - timedelta(days=1)  # GSC data lags
                default_start_date = default_end_date - timedelta(days=29)  # 30 days total
                
                # Process start_date
                if start_date is None:
                    final_start_date_str = default_start_date.strftime('%Y-%m-%d')
                else:
                    final_start_date_str = DateProcessor.process_relative_date(start_date)
                
                # Process end_date
                if end_date is None:
                    final_end_date_str = default_end_date.strftime('%Y-%m-%d')
                else:
                    final_end_date_str = DateProcessor.process_relative_date(end_date)
                
                periods = [(final_start_date_str, final_end_date_str)]
                logger.info(f"Fetching recent data for period: {final_start_date_str} to {final_end_date_str}")

            # Fetch data for each period
            keyword_data_periods = []
            for start_date_str, end_date_str in periods:
                # Fetch raw data for the period
                raw_keyword_data = self._get_search_console_data(
                    search_console_service,
                    search_console_property_url,
                    start_date_str,
                    end_date_str,
                    'query'
                )
                
                # Use the first day of the month as the reference date for the period
                reference_date = datetime.strptime(start_date_str, '%Y-%m-%d').replace(day=1).strftime('%Y-%m-%d')
                
                # Add the period data
                keyword_data_periods.append({
                    'date': reference_date,
                    'data': raw_keyword_data
                })
                
                logger.info(f"Fetched {len(raw_keyword_data)} keywords for period {start_date_str} to {end_date_str}")

            # Build the response
            response = {
                'success': True,
                'property_url': search_console_property_url,
                'periods': len(keyword_data_periods),
                'total_keywords': sum(len(period['data']) for period in keyword_data_periods),
                'keyword_data': keyword_data_periods,
                'error': None
            }

            if sum(len(period['data']) for period in keyword_data_periods) == 0:
                response['message'] = "No keyword data returned from Search Console for the specified period(s)."
                response['success'] = False

            return json.dumps(response, indent=2)

        except Exception as e:
            logger.error(f"Error in Google Ranking Data Tool: {str(e)}")
            error_response = {
                'success': False,
                'error': str(e),
                'property_url': search_console_property_url,
                'keyword_data': []
            }
            return json.dumps(error_response, indent=2)

    def _create_search_console_service(self, credentials: Dict[str, Any]):
        """Create Search Console service from credentials dictionary"""
        try:
            credentials_obj = Credentials(
                None,
                refresh_token=credentials.get('refresh_token'),
                token_uri='https://oauth2.googleapis.com/token',
                client_id=credentials.get('sc_client_id'),
                client_secret=credentials.get('client_secret')
            )
            credentials_obj.refresh(Request())
            search_console_service = build('searchconsole', 'v1', credentials=credentials_obj)
            return search_console_service
        except Exception as e:
            logger.error(f"Error creating Search Console service: {str(e)}")
            if 'invalid_grant' in str(e) or 'expired' in str(e):
                raise ValueError(f"Search Console authentication error: {str(e)}") from e
            return None

    def _get_search_console_data(self, service, property_url, start_date, end_date, dimension):
        """Fetch data from Google Search Console API"""
        try:
            # Simplified URL handling assuming it's usually just the URL string
            site_url = property_url
            logger.info(f"Using Search Console property URL: {site_url} for {start_date} to {end_date}")

            # Increase rowLimit to get more data
            ROW_LIMIT = 5000

            response = service.searchanalytics().query(
                siteUrl=site_url,
                body={
                    'startDate': start_date,
                    'endDate': end_date,
                    'dimensions': [dimension],
                    'rowLimit': ROW_LIMIT,
                    'dataState': 'all'  # Include fresh data if available
                }
            ).execute()

            search_console_data = []
            for row in response.get('rows', []):
                search_console_data.append({
                    'Keyword': row['keys'][0],
                    'Clicks': row.get('clicks', 0),
                    'Impressions': row.get('impressions', 0),
                    'CTR (%)': round(row.get('ctr', 0) * 100, 2),
                    'Avg Position': round(row.get('position', 999), 1)
                })

            logger.info(f"Fetched {len(search_console_data)} rows from Search Console.")
            return search_console_data

        except HttpError as error:
            logger.error(f"An HTTP error occurred while fetching Search Console data: {error.resp.status} {error.content}")
            error_details = f"HTTP {error.resp.status}"
            try:
                content = json.loads(error.content)
                error_details += f": {content.get('error', {}).get('message', 'No specific message')}"
            except json.JSONDecodeError:
                error_details += f": {error.content.decode('utf-8', errors='ignore')}"

            if error.resp.status in [403, 404]:
                raise ValueError(f"Search Console API Error: Check property URL ('{site_url}') and permissions. Details: {error_details}") from error
            else:
                raise RuntimeError(f"Search Console API Error: {error_details}") from error

        except Exception as e:
            logger.error(f"Unexpected error fetching Search Console data: {str(e)}")
            raise RuntimeError(f"Unexpected error during Search Console fetch: {str(e)}") from e

    def _get_monthly_periods(self, months: int = 12):
        """
        Generate monthly periods for the last N months.
        Returns a list of (start_date, end_date) tuples in YYYY-MM-DD format.
        """
        periods = []
        today = datetime.now().date()
        
        for i in range(months):
            # Calculate the end date for this month (last day of the month)
            end_month = today.month - i
            end_year = today.year
            
            # Adjust year if needed
            while end_month <= 0:
                end_month += 12
                end_year -= 1
                
            # Calculate the start date (first day of the month)
            start_date = datetime(end_year, end_month, 1).date()
            
            # Calculate the end date (last day of the month)
            if end_month == 12:
                end_date = datetime(end_year + 1, 1, 1).date() - timedelta(days=1)
            else:
                end_date = datetime(end_year, end_month + 1, 1).date() - timedelta(days=1)
            
            # Ensure we don't go beyond today
            if end_date > today:
                end_date = today
                
            # Add the period
            periods.append((start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')))
            
        return periods
