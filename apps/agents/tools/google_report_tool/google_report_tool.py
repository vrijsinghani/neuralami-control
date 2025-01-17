import logging
from typing import Any, Type, List, Optional
from pydantic import BaseModel, Field, field_validator
from crewai.tools import BaseTool
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange, 
    Metric, 
    Dimension, 
    RunReportRequest, 
    OrderBy
)
from datetime import datetime
import json
from googleapiclient.errors import HttpError

# Import Django models
from django.core.exceptions import ObjectDoesNotExist
from apps.seo_manager.models import (
    Client, 
    KeywordRankingHistory,
    TargetedKeyword
)
from django.db import transaction

logger = logging.getLogger(__name__)

class GoogleReportToolInput(BaseModel):
    """Input schema for GoogleReportTool."""
    start_date: str = Field(description="The start date for the analytics data (YYYY-MM-DD).")
    end_date: str = Field(description="The end date for the analytics data (YYYY-MM-DD).")
    client_id: int = Field(description="The ID of the client to fetch Google Analytics data for.")

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_dates(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return value
        except ValueError:
            raise ValueError("Invalid date format. Use YYYY-MM-DD.")

class GoogleReportTool(BaseTool):
    name: str = "Google Analytics and Search Console Report Fetcher"
    description: str = "Fetches Google Analytics and Search Console reports for a specified client and date range."
    args_schema: Type[BaseModel] = GoogleReportToolInput

    def _run(self, start_date: str, end_date: str, client_id: int) -> str:
        try:
            # Get client and credentials
            client = Client.objects.get(id=client_id)
            ga_credentials = client.ga_credentials
            sc_credentials = client.sc_credentials
            
            if not ga_credentials or not sc_credentials:
                raise ValueError("Missing Google Analytics or Search Console credentials")

            # Get authenticated services using model methods
            analytics_service = ga_credentials.get_service()
            if not analytics_service:
                raise ValueError("Failed to initialize Analytics service")
                
            property_id = ga_credentials.get_property_id()
            if not property_id:
                raise ValueError("Missing or invalid Google Analytics property ID")

            search_console_service = sc_credentials.get_service()
            if not search_console_service:
                raise ValueError("Failed to initialize Search Console service")
                
            property_url = sc_credentials.get_property_url()
            if not property_url:
                raise ValueError("Missing or invalid Search Console property URL")

            # Fetch analytics data
            analytics_data = []
            try:
                general_request = RunReportRequest(
                    property=f"properties/{property_id}",
                    date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
                    dimensions=[
                        Dimension(name="sessionSourceMedium"),
                    ],
                    metrics=[
                        Metric(name="totalUsers"),
                        Metric(name="sessions"),
                        Metric(name="bounceRate"),
                        Metric(name="averageSessionDuration"),
                    ],
                    order_bys=[
                        OrderBy(metric=OrderBy.MetricOrderBy(metric_name="totalUsers"), desc=True)
                    ],
                    limit=10
                )        
                general_response = analytics_service.run_report(general_request)
                analytics_data = self._process_analytics_data(general_response)
                
                if not analytics_data:
                    logger.warning("No analytics data returned from Google Analytics")
                
            except Exception as e:
                logger.error(f"Failed to fetch analytics data: {str(e)}")
                if 'invalid_grant' in str(e) or 'expired' in str(e):
                    raise ValueError(f"Google Analytics credentials have expired: {str(e)}")
                raise
            
            # Fetch Search Console data
            keyword_data = []
            landing_page_data = []
            try:
                keyword_data = self._get_search_console_data(search_console_service, property_url, start_date, end_date, 'query')
                landing_page_data = self._get_search_console_data(search_console_service, property_url, start_date, end_date, 'page')
                
                if not keyword_data and not landing_page_data:
                    logger.warning("No data returned from Search Console")
                    
            except Exception as e:
                logger.error(f"Failed to fetch Search Console data: {str(e)}")
                if 'invalid_grant' in str(e) or 'expired' in str(e):
                    raise ValueError(f"Search Console credentials have expired: {str(e)}")
                raise
            
            # Check if we got any data at all
            if not analytics_data and not keyword_data and not landing_page_data:
                return json.dumps({
                    'success': False,
                    'error': "No data was collected from either Google Analytics or Search Console",
                    'analytics_data': [],
                    'keyword_data': [],
                    'landing_page_data': [],
                    'start_date': start_date,
                    'end_date': end_date,
                    'client_id': client_id
                })
            
            return json.dumps({
                'success': True,
                'analytics_data': analytics_data,
                'keyword_data': keyword_data,
                'landing_page_data': landing_page_data,
                'start_date': start_date,
                'end_date': end_date,
                'client_id': client_id
            })
            
        except Exception as e:
            error_message = f"Error fetching GA4 data: {str(e)}"
            logger.error(error_message)
            logger.error("Full error details:", exc_info=True)
            # Return error as string
            return json.dumps({
                'success': False,
                'error': str(e),
                'analytics_data': []
            })

    def _process_analytics_data(self, response):
        processed_data = []
        try:
            for row in response.rows:
                source_medium = row.dimension_values[0].value
                total_users = int(row.metric_values[0].value)
                sessions = int(row.metric_values[1].value)
                bounce_rate = float(row.metric_values[2].value)
                avg_session_duration = float(row.metric_values[3].value)
                
                processed_data.append({
                    'source_medium': source_medium,
                    'total_users': total_users,
                    'sessions': sessions,
                    'bounce_rate': bounce_rate,
                    'avg_session_duration': avg_session_duration
                })
            
            processed_data.sort(key=lambda x: x['total_users'], reverse=True)
        except Exception as e:
            logger.error(f"Error processing analytics data: {str(e)}", exc_info=True)
        return processed_data

    def _get_search_console_data(self, service, property_url, start_date, end_date, dimension):
        try:
            response = service.searchanalytics().query(
                siteUrl=property_url,
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
            return search_console_data[:50]
        except HttpError as error:
            logger.error(f"An error occurred while fetching Search Console data: {error}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching Search Console data: {str(e)}")
            return []
