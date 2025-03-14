import json
import logging
from datetime import datetime, timedelta

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange, Dimension, Filter, FilterExpression, Metric, RunReportRequest
)
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from apps.agents.tools.base_tool import BaseTool
from apps.agents.tools.google_analytics_tool.generic_google_analytics_tool import GenericGoogleAnalyticsTool
from apps.agents.tools.google_search_console_tool.generic_google_search_console_tool import GenericGoogleSearchConsoleTool
from typing import Any, Type, List, Optional, Dict, Union
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

class GoogleOverviewToolInput(BaseModel):
    """Input schema for GoogleOverviewTool."""
    days_ago: int = Field(
        default=90,
        description="Number of days to look back (default: 90)",
        ge=1,
        le=365
    )
    analytics_property_id: Union[str, int] = Field(
        description="The Google Analytics property ID"
    )
    analytics_credentials: Dict[str, Any] = Field(
        description="Credentials for Google Analytics API"
    )
    search_console_property_url: str = Field(
        description="The Search Console property URL"
    )
    search_console_credentials: Dict[str, Any] = Field(
        description="Credentials for Search Console API"
    )
    client_id: Optional[str] = Field(
        None,
        description="Optional client ID for reference"
    )

class GoogleOverviewTool(BaseTool):
    name: str = "Google Analytics and Search Console Overview Tool"
    description: str = "Fetches comprehensive overview reports from Google Analytics and Search Console."
    args_schema: Type[BaseModel] = GoogleOverviewToolInput
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Don't initialize tools here as they may not be called
        # when the tool is loaded dynamically
        self._analytics_tool = None
        self._search_console_tool = None
        logger.info("GoogleOverviewTool initialized")

    @property
    def analytics_tool(self):
        """Lazy loading of the analytics tool to ensure it's only created when needed"""
        if self._analytics_tool is None:
            self._analytics_tool = GenericGoogleAnalyticsTool()
            logger.info("GenericGoogleAnalyticsTool lazily initialized")
        return self._analytics_tool
        
    @property
    def search_console_tool(self):
        """Lazy loading of the search console tool to ensure it's only created when needed"""
        if self._search_console_tool is None:
            self._search_console_tool = GenericGoogleSearchConsoleTool()
            logger.info("GenericGoogleSearchConsoleTool lazily initialized")
        return self._search_console_tool

    def _run(
        self, 
        days_ago: int = 90,
        analytics_property_id: Union[str, int] = None,
        analytics_credentials: Dict[str, Any] = None,
        search_console_property_url: str = None,
        search_console_credentials: Dict[str, Any] = None,
        client_id: Optional[str] = None
    ) -> str:
        try:
            # Calculate dates
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")

            # Validate inputs
            if not analytics_property_id or not analytics_credentials:
                raise ValueError("Missing Google Analytics property ID or credentials")
                
            if not search_console_property_url or not search_console_credentials:
                raise ValueError("Missing Search Console property URL or credentials")
            
            # Validate credentials have the required fields
            ga_required_fields = ['access_token', 'refresh_token', 'ga_client_id', 'client_secret']
            ga_missing_fields = [field for field in ga_required_fields if not analytics_credentials.get(field)]
            if ga_missing_fields:
                ga_missing_fields_str = ', '.join(ga_missing_fields)
                logger.error(f"Missing required Analytics credential fields: {ga_missing_fields_str}")
                raise ValueError(f"Incomplete Google Analytics credentials. Missing: {ga_missing_fields_str}")
                
            # Search Console credentials validation is now handled by the GenericGoogleSearchConsoleTool
            # We'll check for required fields to provide a better error message earlier
            sc_required_fields = ['access_token', 'refresh_token', 'sc_client_id', 'client_secret']
            sc_missing_fields = [field for field in sc_required_fields if not search_console_credentials.get(field)]
            if sc_missing_fields:
                sc_missing_fields_str = ', '.join(sc_missing_fields)
                logger.error(f"Missing required Search Console credential fields: {sc_missing_fields_str}")
                raise ValueError(f"Incomplete Search Console credentials. Missing: {sc_missing_fields_str}")

            # 1. Device & Engagement Analysis
            device_engagement = self._fetch_analytics_report(
                analytics_property_id,
                analytics_credentials,
                start_date,
                end_date,
                "deviceCategory",
                "sessions,bounceRate,engagementRate,averageSessionDuration"
            )

            # 2. Traffic Sources Analysis
            traffic_sources = self._fetch_analytics_report(
                analytics_property_id,
                analytics_credentials,
                start_date,
                end_date,
                "sessionSource,sessionMedium",
                "sessions,newUsers,engagementRate"
            )

            # 3. Page Performance Analysis
            page_performance = self._fetch_analytics_report(
                analytics_property_id,
                analytics_credentials,
                start_date,
                end_date,
                "pagePath",
                "screenPageViews,averageSessionDuration,bounceRate"
            )

            # 4. Geographic Performance
            geo_performance = self._fetch_analytics_report(
                analytics_property_id,
                analytics_credentials,
                start_date,
                end_date,
                "country",
                "sessions,newUsers,engagementRate,averageSessionDuration"
            )

            # 5. Daily Trend Analysis
            daily_trends = self._fetch_analytics_report(
                analytics_property_id,
                analytics_credentials,
                start_date,
                end_date,
                "date",
                "sessions,newUsers,activeUsers,engagementRate"
            )

            # 6. Landing Page Performance
            landing_performance = self._fetch_analytics_report(
                analytics_property_id,
                analytics_credentials,
                start_date,
                end_date,
                "landingPage",
                "sessions,bounceRate,engagementRate,screenPageViews"
            )

            # 7. Browser & Platform Analysis
            tech_analysis = self._fetch_analytics_report(
                analytics_property_id,
                analytics_credentials,
                start_date,
                end_date,
                "browser,operatingSystem",
                "sessions,screenPageViews,bounceRate"
            )

            # 8. Channel Performance
            channel_performance = self._fetch_analytics_report(
                analytics_property_id,
                analytics_credentials,
                start_date,
                end_date,
                "sessionDefaultChannelGroup",
                "sessions,newUsers,engagementRate,averageSessionDuration"
            )

            # 9. Search Console Overview Report
            keyword_data = self._fetch_search_console_report(
                search_console_property_url,
                search_console_credentials,
                start_date,
                end_date,
                ["query", "country"],
                row_limit=50
            )

            # 10. Search Performance by Page Report
            landing_page_data = self._fetch_search_console_report(
                search_console_property_url,
                search_console_credentials,
                start_date,
                end_date,
                ["page"]
            )

            # 11. Search Performance by Device Report
            device_performance_sc = self._fetch_search_console_report(
                search_console_property_url,
                search_console_credentials,
                start_date,
                end_date,
                ["device"]
            )

            # Return all data in a structured format
            return json.dumps({
                'success': True,
                'device_engagement': device_engagement,
                'traffic_sources': traffic_sources,
                'page_performance': page_performance,
                'geo_performance': geo_performance,
                'daily_trends': daily_trends,
                'landing_performance': landing_performance,
                'tech_analysis': tech_analysis,
                'channel_performance': channel_performance,
                'keyword_data': keyword_data,
                'landing_page_data': landing_page_data,
                'device_performance_sc': device_performance_sc,
                'start_date': start_date,
                'end_date': end_date,
                'analytics_property_id': analytics_property_id,
                'search_console_property_url': search_console_property_url,
                'client_id': client_id
            })
        except Exception as e:
            logger.error(f"Error in GoogleOverviewTool: {str(e)}")
            return json.dumps({
                'success': False,
                'error': str(e),
                'error_details': str(e)
            })

    def _fetch_analytics_report(self, property_id: Union[str, int], credentials: Dict[str, Any], 
                             start_date: str, end_date: str, 
                             dimensions: str, metrics: str) -> List[dict]:
        """
        Use GenericGoogleAnalyticsTool to fetch analytics data
        """
        try:
            # Call the GenericGoogleAnalyticsTool._run method
            result = self.analytics_tool._run(
                analytics_property_id=property_id,
                analytics_credentials=credentials,
                start_date=start_date,
                end_date=end_date,
                dimensions=dimensions,
                metrics=metrics,
                limit=1000,
                data_format="raw"  # Use raw format to get all data points
            )
            
            # Check if the call was successful
            if result.get('success', False):
                # Return the analytics_data from the result
                return result.get('analytics_data', [])
            else:
                # Log the error and return an empty list
                logger.error(f"Error fetching analytics report: {result.get('error', 'Unknown error')}")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching analytics report: {str(e)}")
            return []

    def _fetch_search_console_report(self, property_url: str, credentials: Dict[str, Any],
                                   start_date: str, end_date: str, 
                                   dimensions: List[str], row_limit: int = 100) -> List[dict]:
        """
        Use GenericGoogleSearchConsoleTool to fetch search console data
        """
        try:
            # Parse response from GenericGoogleSearchConsoleTool
            result_str = self.search_console_tool._run(
                search_console_property_url=property_url,
                search_console_credentials=credentials,
                start_date=start_date,
                end_date=end_date,
                dimensions=dimensions,
                row_limit=row_limit,
                data_format="raw"  # Use raw format to get all data points
            )
            
            # Parse the JSON string result
            result = json.loads(result_str)
            
            # Check if the call was successful
            if result.get('success', False):
                # Return the search_console_data from the result
                return result.get('search_console_data', [])
            else:
                # Log the error and return an empty list
                logger.error(f"Error fetching search console report: {result.get('error', 'Unknown error')}")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching search console report: {str(e)}")
            return [] 