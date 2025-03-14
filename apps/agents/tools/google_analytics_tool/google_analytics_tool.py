import os
import json
import logging
import sys
from typing import Any, Type, List, Optional, Dict, Union
from pydantic import BaseModel, Field, field_validator
from apps.agents.tools.base_tool import BaseTool
from google.analytics.data_v1beta.types import DateRange, Metric, Dimension, RunReportRequest, OrderBy
from datetime import datetime

# Import only what's necessary
from django.core.exceptions import ObjectDoesNotExist

logger = logging.getLogger(__name__)

class GoogleAnalyticsToolInput(BaseModel):
    """Input schema for GoogleAnalyticsTool."""
    start_date: str = Field(
        default="28daysAgo",
        description="Start date (YYYY-MM-DD) or relative date ('today', 'yesterday', 'NdaysAgo', etc)."
    )
    end_date: str = Field(
        default="today",
        description="End date (YYYY-MM-DD) or relative date ('today', 'yesterday', 'NdaysAgo', etc)."
    )
    analytics_property_id: Union[str, int] = Field(
        description="The Google Analytics property ID to use for fetching data."
    )
    analytics_credentials: Dict[str, Any] = Field(
        description="The credentials needed to authenticate with Google Analytics."
    )
    client_id: Optional[str] = Field(
        None, 
        description="Optional client ID for reference purposes only."
    )

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_dates(cls, value: str) -> str:
        # Allow relative dates
        relative_dates = ['today', 'yesterday', '7daysAgo', '14daysAgo', '28daysAgo', '30daysAgo', '90daysAgo']
        if value in relative_dates or cls.is_relative_date(value):
            return value
        
        # Validate actual dates
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return value
        except ValueError:
            raise ValueError("Invalid date format. Use YYYY-MM-DD or relative dates (today, yesterday, NdDaysAgo, etc)")

    @field_validator("analytics_property_id")
    @classmethod
    def ensure_property_id_is_string(cls, value) -> str:
        """Ensure the property ID is always a string."""
        if value is None:
            raise ValueError("Analytics property ID cannot be None")
        
        # Convert to string if it's not already
        return str(value)
            
    @classmethod
    def is_relative_date(cls, value: str) -> bool:
        """Check if the value is in the format of NdDaysAgo."""
        if len(value) > 8 and value.endswith("daysAgo"):
            try:
                int(value[:-8])  # Check if the prefix is an integer
                return True
            except ValueError:
                return False
        return False
    
class GoogleAnalyticsTool(BaseTool):
    name: str = "Google Analytics Data Fetcher"
    description: str = "Fetches Google Analytics data for a specified date range using provided credentials."
    args_schema: Type[BaseModel] = GoogleAnalyticsToolInput
    
    def __init__(self, **kwargs):
        super().__init__()
        logger.info("GoogleAnalyticsTool initialized")
        self._initialize_dimensions_metrics()

    def _initialize_dimensions_metrics(self):
        """Initialize the dimensions and metrics for GA4 reporting"""
        self._dimensions = [
            Dimension(name="date")
        ]
        
        self._metrics = [
            Metric(name="totalUsers"),
            Metric(name="sessions"),
            Metric(name="averageSessionDuration"),
            Metric(name="screenPageViews"),
            Metric(name="screenPageViewsPerSession"),
            Metric(name="newUsers"),
            Metric(name="bounceRate"),
            Metric(name="engagedSessions"),
            Metric(name="keyEvents")
        ]

    def _run(
        self, 
        start_date: str, 
        end_date: str, 
        analytics_property_id: Union[str, int],
        analytics_credentials: Dict[str, Any]
    ) -> dict:
        try:
            # No need to fetch client, use the provided credentials directly
            if not analytics_property_id:
                raise ValueError("Missing Google Analytics property ID")
            
            # Convert property_id to string if it's not already
            analytics_property_id = str(analytics_property_id)
            
            if not analytics_credentials:
                raise ValueError("Missing Google Analytics credentials")
            
            # Validate credentials before attempting to use them
            required_fields = ['access_token', 'refresh_token', 'ga_client_id', 'client_secret']
            missing_fields = [field for field in required_fields if not analytics_credentials.get(field)]
            if missing_fields:
                missing_fields_str = ', '.join(missing_fields)
                logger.error(f"Missing required credential fields: {missing_fields_str}")
                raise ValueError(f"Incomplete Google Analytics credentials. Missing: {missing_fields_str}")
            
            # Create analytics service from credentials
            from google.analytics.data_v1beta import BetaAnalyticsDataClient
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            
            # Log incoming credentials for debugging
            logger.debug(f"Analytics property ID: {analytics_property_id}")
            logger.debug(f"Credential fields available: {list(analytics_credentials.keys())}")
            
            # Create credentials object from the provided dictionary
            # Match the format expected by Google's API
            credentials = Credentials(
                token=analytics_credentials.get('access_token'),
                refresh_token=analytics_credentials.get('refresh_token'),
                token_uri=analytics_credentials.get('token_uri', 'https://oauth2.googleapis.com/token'),
                client_id=analytics_credentials.get('ga_client_id'),
                client_secret=analytics_credentials.get('client_secret'),
                scopes=analytics_credentials.get('scopes', [
                    'https://www.googleapis.com/auth/analytics.readonly',
                    'https://www.googleapis.com/auth/userinfo.email'
                ])
            )
            
            # Try to refresh the token if we have a refresh token
            if credentials.refresh_token:
                try:
                    logger.debug("Attempting to refresh credentials token")
                    request = Request()
                    credentials.refresh(request)
                    logger.debug("Successfully refreshed credentials token")
                except Exception as e:
                    logger.error(f"Failed to refresh token: {str(e)}")
                    if 'invalid_grant' in str(e).lower():
                        raise ValueError("Google Analytics credentials have expired. Please reconnect your Google Analytics account.")
                    # Continue with the possibly expired token and let the API call handle any auth errors
            
            # Log what we're doing for debugging
            logger.debug(f"Creating Google Analytics client with property ID: {analytics_property_id}")
            
            # Create the analytics service
            service = BetaAnalyticsDataClient(credentials=credentials)
            
            request = RunReportRequest(
                property=f"properties/{analytics_property_id}",
                dimensions=self._dimensions,
                metrics=self._metrics,
                date_ranges=[DateRange(
                    start_date=start_date,
                    end_date=end_date
                )],
                order_bys=[
                    OrderBy(
                        dimension=OrderBy.DimensionOrderBy(
                            dimension_name="date"
                        ),
                        desc=False
                    )
                ]
            )

            response = service.run_report(request)
            analytics_data = []
            
            for row in response.rows:
                date_str = row.dimension_values[0].value
                formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
                
                try:
                    data_point = {
                        'date': formatted_date,
                        'active_users': int(float(row.metric_values[0].value or 0)),
                        'sessions': int(float(row.metric_values[1].value or 0)),
                        'avg_session_duration': float(row.metric_values[2].value or 0),
                        'page_views': int(float(row.metric_values[3].value or 0)),
                        'pages_per_session': float(row.metric_values[4].value or 0),
                        'new_users': int(float(row.metric_values[5].value or 0)),
                        'bounce_rate': float(row.metric_values[6].value or 0) * 100,
                        'engaged_sessions': int(float(row.metric_values[7].value or 0))
                    }
                    analytics_data.append(data_point)
                except (ValueError, IndexError) as e:
                    logger.error(f"Error processing row {date_str}: {str(e)}")
                    continue

            analytics_data.sort(key=lambda x: x['date'])

            return {
                'success': True,
                'analytics_data': analytics_data,
                'start_date': start_date,
                'end_date': end_date,
                'property_id': analytics_property_id
            }

        except Exception as e:
            error_str = str(e)
            logger.error(f"Error fetching GA4 data: {error_str}")
            logger.error("Full error details:", exc_info=True)
            
            # Provide more specific error messages
            if 'invalid_grant' in error_str.lower() or 'invalid authentication credentials' in error_str.lower():
                error_message = "Google Analytics credentials have expired or are invalid. Please reconnect your Google Analytics account."
            elif 'quota' in error_str.lower():
                error_message = "Google Analytics API quota exceeded. Please try again later."
            elif 'permission' in error_str.lower() or 'access' in error_str.lower():
                error_message = "Insufficient permissions to access Google Analytics data. Please check your account permissions."
            elif not analytics_credentials.get('access_token'):
                error_message = "Missing access token in Google Analytics credentials."
            elif not analytics_credentials.get('refresh_token'):
                error_message = "Missing refresh token in Google Analytics credentials."
            elif not analytics_credentials.get('ga_client_id') or not analytics_credentials.get('client_secret'):
                error_message = "Missing client credentials in Google Analytics configuration."
            else:
                error_message = f"Error fetching Google Analytics data: {error_str}"
                
            return {
                'success': False,
                'error': error_message,
                'analytics_data': []
            }
