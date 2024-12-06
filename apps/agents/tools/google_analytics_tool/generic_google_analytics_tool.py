import os
import json
import logging
import sys
from typing import Any, Type, List, Optional, ClassVar
from pydantic import BaseModel, Field, field_validator
from crewai_tools.tools.base_tool import BaseTool
from google.analytics.data_v1beta.types import DateRange, Metric, Dimension, RunReportRequest, OrderBy, RunReportResponse
from datetime import datetime
from crewai_tools.tools.base_tool import BaseTool
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import CheckCompatibilityRequest

# Import Django models (assuming this is your setup)
from django.core.exceptions import ObjectDoesNotExist
from apps.seo_manager.models import Client, GoogleAnalyticsCredentials

logger = logging.getLogger(__name__)

"""
Generic Google Analytics Tool for fetching customizable GA4 data.

Example usage:
    tool = GenericGoogleAnalyticsTool()
    
    # Basic usage with defaults
    result = tool._run(client_id=123)
    
    # Custom query
    result = tool._run(
        client_id=123,
        start_date="7daysAgo",
        end_date="today", 
        metrics="totalUsers,sessions,bounceRate",
        dimensions="date,country,deviceCategory",
        dimension_filter="country==United States",
        metric_filter="sessions>100",
        currency_code="USD",
        limit=2000
    )
"""

class GoogleAnalyticsRequest(BaseModel):
    """Input schema for the generic Google Analytics Request tool."""
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
    metrics: str = Field(
        default="totalUsers,sessions",
        description="Comma-separated list of metric names."
    )
    dimensions: str = Field(
        default="date",
        description="Comma-separated list of dimension names (e.g., 'date,country,deviceCategory')."
    )
    dimension_filter: Optional[str] = Field(
        default=None,
        description="Filter expression for dimensions (e.g., 'country==United States')."
    )
    metric_filter: Optional[str] = Field(
        default="sessions>10",
        description="Filter expression for metrics (e.g., 'sessions>100')."
    )
    currency_code: Optional[str] = Field(
        default=None,
        description="The currency code for metrics involving currency (e.g., 'USD')."
    )
    keep_empty_rows: Optional[bool] = Field(
        default=False,
        description="Whether to keep empty rows in the response."
    )
    limit: Optional[int] = Field(
        default=1000,
        description="Optional limit on the number of rows to return (default 1000, max 100000)."
    )
    offset: Optional[int] = Field(
        default=None,
        description="Optional offset for pagination."
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
    
class GenericGoogleAnalyticsTool(BaseTool):
    name: str = "Generic Google Analytics Data Fetcher"
    description: str = "Fetches Google Analytics data with customizable metrics and dimensions."
    args_schema: Type[BaseModel] = GoogleAnalyticsRequest
    
    def __init__(self, **kwargs):
        super().__init__()
        logger.info("GenericGoogleAnalyticsTool initialized")
        self._initialize_dimensions_metrics()

    def _initialize_dimensions_metrics(self):
        """Initialize the available dimensions and metrics"""
        self._available_metrics = [
            "totalUsers",
            "sessions",
            "averageSessionDuration",
            "screenPageViews",
            "screenPageViewsPerSession",
            "newUsers",
            "bounceRate",
            "engagedSessions",
            "engagementRate",
            "activeUsers",
            "eventCount",
            "conversions",
            "userEngagementDuration"
        ]
        self._available_dimensions = [
            "date",
            "deviceCategory",
            "platform",
            "sessionSource",
            "sessionMedium",
            "sessionCampaignName",
            "sessionDefaultChannelGroup",
            "country",
            "city",
            "landingPage",
            "pagePath",
            "browser",
            "operatingSystem"
        ]

    def _check_compatibility(self, service, property_id: str, metrics: List[str], dimensions: List[str]) -> tuple[bool, str]:
        """
        Check if the requested metrics and dimensions are compatible.
        Returns a tuple of (is_compatible: bool, error_message: str)
        """
        try:
            # Create separate metric and dimension objects
            metric_objects = [Metric(name=m.strip()) for m in metrics]
            dimension_objects = [Dimension(name=d.strip()) for d in dimensions]

            request = CheckCompatibilityRequest(
                property=f"properties/{property_id}",
                metrics=metric_objects,
                dimensions=dimension_objects
            )
            
            response = service.check_compatibility(request=request)

            # Check for dimension errors
            if response.dimension_compatibilities:
                for dim_compat in response.dimension_compatibilities:
                    dim_name = getattr(dim_compat.dimension_metadata, 'api_name', 'unknown')
                    if dim_name in dimensions:
                        if dim_compat.compatibility == 'INCOMPATIBLE':
                            error_msg = f"Incompatible dimension: {dim_name}"
                            logger.error(error_msg)
                            return False, error_msg
            
            # Check for metric errors
            if response.metric_compatibilities:
                for metric_compat in response.metric_compatibilities:
                    metric_name = getattr(metric_compat.metric_metadata, 'api_name', 'unknown')
                    if metric_name in metrics:
                        if metric_compat.compatibility == 'INCOMPATIBLE':
                            error_msg = f"Incompatible metric: {metric_name}"
                            logger.error(error_msg)
                            return False, error_msg
            
            return True, "Compatible"

        except Exception as e:
            logger.error(f"Error checking compatibility: {str(e)}", exc_info=True)
            # Return a more graceful fallback - assume compatible if check fails
            return True, "Compatibility check failed, proceeding with request"

    def _run(self, 
             client_id: int,
             start_date: str = "28daysAgo", 
             end_date: str = "today", 
             metrics: str = "totalUsers,sessions", 
             dimensions: str = "date",
             dimension_filter: Optional[str] = None,
             metric_filter: str = "sessions>10",
             currency_code: Optional[str] = None,
             keep_empty_rows: bool = False,
             limit: int = 1000,
             offset: Optional[int] = None) -> dict:
        try:
            # Get client and credentials
            client = Client.objects.get(id=client_id)
            ga_credentials = client.ga_credentials
            if not ga_credentials:
                raise ValueError("Missing Google Analytics credentials")
            
            service = ga_credentials.get_service()
            if not service:
                raise ValueError("Failed to initialize Analytics service")
            
            property_id = ga_credentials.get_property_id()
            if not property_id:
                raise ValueError("Missing or invalid Google Analytics property ID")

            # Check compatibility before running the report
            metrics_list = [m.strip() for m in metrics.split(',')]
            dimensions_list = [d.strip() for d in dimensions.split(',')]
            
            # Validate metrics and dimensions against available lists
            for metric in metrics_list:
                if metric not in self._available_metrics:
                    return {
                        'success': False,
                        'error': f"Invalid metric: {metric}. Available metrics: {', '.join(self._available_metrics)}",
                        'analytics_data': []
                    }
            
            for dimension in dimensions_list:
                if dimension not in self._available_dimensions:
                    return {
                        'success': False,
                        'error': f"Invalid dimension: {dimension}. Available dimensions: {', '.join(self._available_dimensions)}",
                        'analytics_data': []
                    }
            
            is_compatible, error_message = self._check_compatibility(
                service, 
                property_id, 
                metrics_list, 
                dimensions_list
            )
            
            if not is_compatible:
                return {
                    'success': False,
                    'error': error_message,
                    'analytics_data': []
                }

            # Create the RunReportRequest
            request = RunReportRequest({
                "property": f"properties/{property_id}",
                "date_ranges":[DateRange(
                    start_date=start_date,
                    end_date=end_date
                )],
                "metrics": [{"name": m.strip()} for m in metrics.split(',')],
                "dimensions": [{"name": d.strip()} for d in dimensions.split(',')],
                "dimension_filter": self._parse_filter(dimension_filter) if dimension_filter else None,
                "metric_filter": self._parse_filter(metric_filter) if metric_filter else None,
                "currency_code": currency_code,
                "keep_empty_rows": keep_empty_rows,
                "limit": limit,
                "offset": offset,
                "order_bys": [
                    {
                        "dimension": {
                            "dimension_name": "date"
                        },
                        "desc": False
                    }
                ] if "date" in dimensions else None,
                "return_property_quota": True
            })

            response = service.run_report(request)
            return self._format_response(response, metrics.split(','), dimensions.split(','))

        except Exception as e:
            logger.error(f"Error fetching GA4 data: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'analytics_data': []
            }

    def _parse_filter(self, filter_string: str) -> dict:
        """
        Parse filter string into GA4 filter object.
        Examples:
            - "country==United States" -> exact string match
            - "sessions>100" -> numeric greater than
        """
        try:
            if '==' in filter_string:
                field, value = filter_string.split('==')
                return {
                    "filter": {
                        "field_name": field.strip(),
                        "string_filter": {
                            "value": value.strip(),
                            "match_type": "EXACT",
                            "case_sensitive": False
                        }
                    }
                }
            elif '>' in filter_string:
                field, value = filter_string.split('>')
                return {
                    "filter": {
                        "field_name": field.strip(),
                        "numeric_filter": {
                            "operation": "GREATER_THAN",
                            "value": {
                                "int64_value": int(float(value.strip()))
                            }
                        }
                    }
                }
            
            raise ValueError(f"Unsupported filter format: {filter_string}")
        except Exception as e:
            logger.error(f"Error parsing filter: {str(e)}")
            return None
        
    def _format_response(self, response, metrics: List[str], dimensions: List[str]) -> dict:
        analytics_data = []
        for row in response.rows:
            data_point = {}
            for i, dim in enumerate(dimensions):
                value = row.dimension_values[i].value
                if dim == 'date':
                    value = f"{value[:4]}-{value[4:6]}-{value[6:]}"
                data_point[dim] = value
            for i, metric in enumerate(metrics):
                data_point[metric] = float(row.metric_values[i].value) if row.metric_values[i].value else 0
            analytics_data.append(data_point)
        
        return {
            'success': True,
            'analytics_data': analytics_data
        }