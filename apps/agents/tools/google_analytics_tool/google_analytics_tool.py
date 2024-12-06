import os
import json
import logging
import sys
from typing import Any, Type, List, Optional
from pydantic import BaseModel, Field, field_validator
from crewai_tools.tools.base_tool import BaseTool
from google.analytics.data_v1beta.types import DateRange, Metric, Dimension, RunReportRequest, OrderBy
from datetime import datetime

# Import Django models
from django.core.exceptions import ObjectDoesNotExist
from apps.seo_manager.models import Client, GoogleAnalyticsCredentials

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
    client_id: int = Field(
        description="The ID of the client."
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
    description: str = "Fetches Google Analytics data for a specified client and date range."
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
            Metric(name="engagedSessions")
        ]

    def _run(self, start_date: str, end_date: str, client_id: int) -> dict:
        try:
            # Get client and credentials
            client = Client.objects.get(id=client_id)
            ga_credentials = client.ga_credentials
            
            if not ga_credentials:
                raise ValueError("Missing Google Analytics credentials")
            
            # Get authenticated service using model method
            service = ga_credentials.get_service()
            if not service:
                raise ValueError("Failed to initialize Analytics service")
            
            # Get property ID using model method
            property_id = ga_credentials.get_property_id()
            if not property_id:
                raise ValueError("Missing or invalid Google Analytics property ID")

            request = RunReportRequest(
                property=f"properties/{property_id}",
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
                'end_date': end_date
            }

        except Exception as e:
            logger.error(f"Error fetching GA4 data: {str(e)}")
            logger.error("Full error details:", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'analytics_data': []
            }
