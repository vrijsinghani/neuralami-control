import os
import json
import logging
import sys
from typing import Any, Type, List, Optional, ClassVar
from pydantic import BaseModel, Field, field_validator
from google.analytics.data_v1beta.types import DateRange, Metric, Dimension, RunReportRequest, OrderBy, RunReportResponse
from datetime import datetime
from apps.agents.tools.base_tool import BaseTool
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import CheckCompatibilityRequest
from enum import Enum
from typing import Optional, List, Union
import pandas as pd
from datetime import datetime, timedelta
from apps.common.utils import DateProcessor

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

class TimeGranularity(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    AUTO = "auto"

class DataFormat(str, Enum):
    RAW = "raw"
    SUMMARY = "summary"
    COMPACT = "compact"

class MetricAggregation(str, Enum):
    SUM = "sum"
    AVERAGE = "average"
    MIN = "min"
    MAX = "max"

class GoogleAnalyticsRequest(BaseModel):
    """Input schema for the generic Google Analytics Request tool."""
    start_date: str = Field(
        default="28daysAgo",
        description="""
        Start date in one of these formats:
        - YYYY-MM-DD (e.g., 2024-03-15)
        - Relative days: 'today', 'yesterday', 'NdaysAgo' (e.g., 7daysAgo)
        - Relative months: 'NmonthsAgo' (e.g., 3monthsAgo)
        
        Note: While GA4 API only supports days, this tool automatically converts
        month-based dates to the appropriate day format.
        """
    )
    end_date: str = Field(
        default="yesterday",
        description="""
        End date in one of these formats:
        - YYYY-MM-DD (e.g., 2024-03-15)
        - Relative days: 'today', 'yesterday', 'NdaysAgo' (e.g., 7daysAgo)
        - Relative months: 'NmonthsAgo' (e.g., 3monthsAgo)
        """
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
        default=None,
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
    data_format: DataFormat = Field(
        default=DataFormat.RAW,
        description="""
        How to format the returned data:
        - 'raw': Returns all data points (use for detailed analysis)
        - 'summary': Returns statistical summary (min/max/mean/median) - best for high-level insights
        - 'compact': Returns top N results (good for finding top performers)
        
        Example use cases:
        - For trend analysis: use 'raw' with date dimension
        - For performance overview: use 'summary'
        - For top traffic sources: use 'compact' with top_n=5
        """
    )
    top_n: Optional[int] = Field(
        default=None,
        description="""
        Return only top N results by primary metric.
        
        Example use cases:
        - top_n=5 with dimensions="country" → top 5 countries
        - top_n=10 with dimensions="pagePath" → top 10 pages
        - top_n=3 with dimensions="sessionSource" → top 3 traffic sources
        """
    )
    time_granularity: TimeGranularity = Field(
        default=TimeGranularity.AUTO,
        description="""
        Time period to aggregate data by:
        - 'daily': Keep daily granularity (best for 1-7 day ranges)
        - 'weekly': Group by weeks (best for 8-60 day ranges)
        - 'monthly': Group by months (best for 60+ day ranges)
        - 'auto': Automatically choose based on date range
        
        Example use cases:
        - For last week analysis: use 'daily'
        - For quarterly trends: use 'monthly'
        - For year-over-year: use 'monthly'
        """
    )
    aggregate_by: Optional[List[str]] = Field(
        default=None,
        description="""
        Dimensions to group data by. Combines all other dimensions.
        
        Example use cases:
        - ['country'] → aggregate all metrics by country
        - ['deviceCategory'] → combine data across all devices
        - ['sessionSource', 'country'] → group by both source and country
        
        Common combinations:
        - Traffic analysis: ['sessionSource', 'sessionMedium']
        - Geographic insights: ['country', 'city']
        - Device analysis: ['deviceCategory', 'browser']
        """
    )
    metric_aggregation: MetricAggregation = Field(
        default=MetricAggregation.SUM,
        description="How to aggregate metrics when grouping data"
    )
    include_percentages: bool = Field(
        default=False,
        description="""
        Add percentage calculations relative to totals.
        Adds '_pct' suffix to metric names (e.g., 'sessions_pct').
        
        Example use cases:
        - Traffic distribution: see % of sessions by country
        - Device share: % of users by deviceCategory
        - Source attribution: % of conversions by source
        """
    )
    normalize_metrics: bool = Field(
        default=False,
        description="""
        Scale numeric metrics to 0-1 range for easier comparison.
        Adds '_normalized' suffix to metric names.
        
        Use when:
        - Comparing metrics with different scales
        - Looking for relative performance
        - Creating visualizations
        """
    )
    round_digits: Optional[int] = Field(
        default=None,
        description="Round numeric values to specified digits"
    )
    include_period_comparison: bool = Field(
        default=False,
        description="""
        Include comparison with previous period.
        
        Example use cases:
        - Month-over-month growth
        - Year-over-year comparison
        - Week-over-week performance
        
        Returns additional fields:
        - previous_period_value
        - percentage_change
        """
    )
    detect_anomalies: bool = Field(
        default=False,
        description="Identify significant deviations from normal patterns"
    )
    moving_average_window: Optional[int] = Field(
        default=None,
        description="""
        Calculate moving averages over specified number of periods.
        Only applies when data includes the 'date' dimension.
        
        Example use cases:
        - 7-day moving average for smoothing daily fluctuations
        - 30-day moving average for trend analysis
        - 90-day moving average for long-term patterns
        
        Adds '_ma{window}' suffix to metric names (e.g., 'sessions_ma7')
        """
    )

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_dates(cls, value: str) -> str:
        return DateProcessor.process_relative_date(value)

class GenericGoogleAnalyticsTool(BaseTool):
    name: str = "GA4 Analytics Data Tool"
    description: str = """
    Fetches data from Google Analytics 4 (GA4) with powerful data processing capabilities.
    
    Key Features:
    - Flexible date ranges (e.g., '7daysAgo', '3monthsAgo', 'YYYY-MM-DD')
    - Common metrics: sessions, users, pageviews, bounce rate, etc.
    - Dimensions: date, country, device, source, medium, etc.
    - Data processing: aggregation, filtering, summaries
    
    Example Commands:
    1. Basic traffic data:
       tool._run(client_id=123, metrics="sessions,users", dimensions="date")
    
    2. Top countries by sessions:
       tool._run(
           client_id=123,
           metrics="sessions",
           dimensions="country",
           data_format="compact",
           top_n=5
       )
    
    3. Monthly trend with comparisons:
       tool._run(
           client_id=123,
           start_date="6monthsAgo",
           time_granularity="monthly",
           include_period_comparison=True
       )
    """
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
            "firstVisit",
            "bounceRate",
            "engagedSessions",
            "engagementRate",
            "activeUsers",
            "eventCount",
            "eventsPerSession",
            "keyEvents",
            "conversions",
            "userEngagementDuration",
            "grossPurchaseRevenue",
            "averagePurchaseRevenuePerPayingUser",
            "averageRevenuePerUser",
            "addToCarts",
            "ecommercePurchases",
            "advertiserAdCost",
            "advertiserAdCostPerClick",
            "advertiserAdImpressions",
            "advertiserAdClicks",
            "totalRevenue"
        ]
        
        # Add metric type classifications
        self._summable_metrics = {
            "totalUsers",
            "sessions",
            "screenPageViews",
            "newUsers",
            "firstVisit",
            "engagedSessions",
            "activeUsers",
            "eventCount",
            "keyEvents",
            "conversions",
            "userEngagementDuration",
            "totalRevenue",
            "advertiserAdClicks",
            "advertiserAdImpressions",
            "advertiserAdCost",
            "grossPurchaseRevenue",
            "totalRevenue",
 

        }
        
        self._averaged_metrics = {
            "averageSessionDuration",
            "screenPageViewsPerSession",
            "bounceRate",
            "engagementRate",
            "eventsPerSession",
            "averagePurchaseRevenuePerPayingUser",
            "averageRevenuePerUser",
            "advertiserAdCostPerClick",
            "averageSessionDuration"
        }

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
            "operatingSystem",
            "sessionCampaignName",
            "sessionGoogleAdsAdGroupName",
            "firstUserGoogleAdsGroupName",
            "defaultChannelGroup",
            "sessionSourceMedium",
            "userGender",
            "city",
            "country",
            "continent",
            "region",
            "metro",
            "brandingInterests",
            "dayOfWeek",
            "dayofWeekName",
            "Hour",
            "newVsReturning",
            "userAgeBracket",
            "eventName",
            "landingPage",
            "firstUserSourceMedium",
            "firstUserMedium",
            "firstUserPrimaryChannelGroup",
            "firstUserDefaultChannelGroup",
            "firstUserSource",
            "firstUserSourcePlatform",
            "firstUserCampaignName",
            "sessiongoogleAdsAdGroupName",
            "firstUserGoogleAdsKeyword",
            "firstuserGoogleAdsQuery",
            "googleAdsKeyword",
            "googleAdsQuery"
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
             metric_filter: Optional[str] = None,
             currency_code: Optional[str] = None,
             keep_empty_rows: bool = False,
             limit: int = 1000,
             offset: Optional[int] = None,
             data_format: DataFormat = DataFormat.RAW,
             top_n: Optional[int] = None,
             time_granularity: TimeGranularity = TimeGranularity.AUTO,
             aggregate_by: Optional[List[str]] = None,
             metric_aggregation: MetricAggregation = MetricAggregation.SUM,
             include_percentages: bool = False,
             normalize_metrics: bool = False,
             round_digits: Optional[int] = None,
             include_period_comparison: bool = False,
             detect_anomalies: bool = False,
             moving_average_window: Optional[int] = None) -> dict:
        try:
            # Convert kwargs to GoogleAnalyticsRequest
            request_params = GoogleAnalyticsRequest(
                client_id=client_id,
                start_date=start_date,
                end_date=end_date,
                metrics=metrics,
                dimensions=dimensions,
                dimension_filter=dimension_filter,
                metric_filter=metric_filter,
                currency_code=currency_code,
                keep_empty_rows=keep_empty_rows,
                limit=limit,
                offset=offset,
                data_format=data_format,
                top_n=top_n,
                time_granularity=time_granularity,
                aggregate_by=aggregate_by,
                metric_aggregation=metric_aggregation,
                include_percentages=include_percentages,
                normalize_metrics=normalize_metrics,
                round_digits=round_digits,
                include_period_comparison=include_period_comparison,
                detect_anomalies=detect_anomalies,
                moving_average_window=moving_average_window
            )
            
            # Get client and credentials
            client = Client.objects.get(id=request_params.client_id)
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
            metrics_list = [m.strip() for m in request_params.metrics.split(',')]
            dimensions_list = [d.strip() for d in request_params.dimensions.split(',')]
            
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
            # Log the request parameters for debugging
            logger.debug("Creating RunReportRequest with parameters: %s", {
                "property": f"properties/{property_id}",
                "date_ranges": [{
                    "start_date": request_params.start_date,
                    "end_date": request_params.end_date
                }],
                "metrics": [{"name": m.strip()} for m in request_params.metrics.split(',')],
                "dimensions": [{"name": d.strip()} for d in request_params.dimensions.split(',')],
                "dimension_filter": request_params.dimension_filter,
                "metric_filter": request_params.metric_filter,
                "currency_code": request_params.currency_code,
                "keep_empty_rows": request_params.keep_empty_rows,
                "limit": request_params.limit,
                "offset": request_params.offset,
                "order_bys": [
                    {
                        "dimension": {
                            "dimension_name": "date"
                        },
                        "desc": False
                    }
                ] if "date" in dimensions_list else None,
                "return_property_quota": True
            })
            # Create the RunReportRequest
            request = RunReportRequest({
                "property": f"properties/{property_id}",
                "date_ranges":[DateRange(
                    start_date=request_params.start_date,
                    end_date=request_params.end_date
                )],
                "metrics": [{"name": m.strip()} for m in request_params.metrics.split(',')],
                "dimensions": [{"name": d.strip()} for d in request_params.dimensions.split(',')],
                "dimension_filter": self._parse_filter(request_params.dimension_filter) if request_params.dimension_filter else None,
                "metric_filter": self._parse_filter(request_params.metric_filter) if request_params.metric_filter else None,
                "currency_code": request_params.currency_code,
                "keep_empty_rows": request_params.keep_empty_rows,
                "limit": request_params.limit,
                "offset": request_params.offset,
                "order_bys": [
                    {
                        "dimension": {
                            "dimension_name": "date"
                        },
                        "desc": False
                    }
                ] if "date" in dimensions_list else None,
                "return_property_quota": True
            })

            # Get the raw response
            response = service.run_report(request)
            
            # Format the raw response
            raw_data = self._format_response(response, 
                                           request_params.metrics.split(','), 
                                           request_params.dimensions.split(','))
            
            # Process the data according to the request parameters
            if raw_data['success']:
                processed_data = DataProcessor.process_data(
                    raw_data['analytics_data'], 
                    request_params,
                    self._averaged_metrics
                )
                
                # Handle period comparison format
                if isinstance(processed_data, dict) and 'period_comparison' in processed_data:
                    return {
                        'success': True,
                        'analytics_data': processed_data['data'],
                        'period_comparison': processed_data['period_comparison']
                    }
                
                return {
                    'success': True,
                    'analytics_data': processed_data
                }
            
            return raw_data

        except Exception as e:
            logger.error(f"Error in Google Analytics tool: {str(e)}", exc_info=True)
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
        try:
            analytics_data = []
            # Clean dimension names - strip whitespace
            dimensions = [d.strip() for d in dimensions]



            if not hasattr(response, 'rows'):
                return {
                    'success': False,
                    'error': 'No rows in response',
                    'analytics_data': []
                }

            for row in response.rows:
                data_point = {}
                for i, dim in enumerate(dimensions):
                    value = row.dimension_values[i].value
                    if dim == 'date':
                        value = f"{value[:4]}-{value[4:6]}-{value[6:]}"
                    data_point[dim] = value
                for i, metric in enumerate(metrics):
                    try:
                        data_point[metric] = float(row.metric_values[i].value) if row.metric_values[i].value else 0
                    except (ValueError, TypeError):
                        data_point[metric] = 0
                analytics_data.append(data_point)

            return {
                'success': True,
                'analytics_data': analytics_data
            }
        except Exception as e:
            logger.error(f"Error formatting response: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': f"Failed to format response: {str(e)}",
                'analytics_data': []
            }

class DataProcessor:
    @staticmethod
    def determine_granularity(start_date: str, end_date: str) -> TimeGranularity:
        """Automatically determine appropriate time granularity"""
        try:
            start = datetime.strptime(start_date[:10], "%Y-%m-%d")
            end = datetime.strptime(end_date[:10], "%Y-%m-%d")
            days_difference = (end - start).days
            
            if days_difference <= 7:
                return TimeGranularity.DAILY
            elif days_difference <= 60:
                return TimeGranularity.WEEKLY
            return TimeGranularity.MONTHLY
        except ValueError:
            return TimeGranularity.DAILY

    @staticmethod
    def _calculate_moving_averages(df: pd.DataFrame, window: int, metrics: List[str]) -> pd.DataFrame:
        """Calculate moving averages for specified metrics"""
        if 'date' not in df.columns:
            return df
            
        # Ensure date is datetime for proper sorting
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        for metric in metrics:
            if metric in df.columns:
                df[f'{metric}_ma{window}'] = df[metric].rolling(
                    window=window,
                    min_periods=1  # Allow partial windows at the start
                ).mean()
        
        return df

    @staticmethod
    def _add_period_comparison(df: pd.DataFrame, metrics: List[str]) -> pd.DataFrame:
        """Add period-over-period comparison metrics"""
        if 'date' not in df.columns:
            return df
        
        # Ensure date is datetime for proper sorting
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        # Calculate the period length
        total_days = (df['date'].max() - df['date'].min()).days
        period_length = total_days // 2
        
        # Create a cutoff date for splitting current and previous periods
        cutoff_date = df['date'].max() - pd.Timedelta(days=period_length)
        
        # Split into current and previous periods
        current_period = df[df['date'] > cutoff_date].copy()
        previous_period = df[df['date'] <= cutoff_date].copy()
        
        # Calculate metrics for both periods
        comparison_data = {}
        
        for metric in metrics:
            if metric in df.columns:
                current_value = float(current_period[metric].mean())  # Convert to float
                previous_value = float(previous_period[metric].mean())  # Convert to float
                
                # Add comparison metrics
                df[f'{metric}_previous'] = previous_value
                df[f'{metric}_change'] = ((current_value - previous_value) / previous_value * 100 
                                        if previous_value != 0 else 0)
                
                comparison_data[metric] = {
                    'current_period': current_value,
                    'previous_period': previous_value,
                    'percent_change': float((current_value - previous_value) / previous_value * 100 
                                         if previous_value != 0 else 0)
                }
        
        # Add comparison summary to the DataFrame
        df.attrs['period_comparison'] = comparison_data
        
        return df

    @staticmethod
    def process_data(data: List[dict], params: GoogleAnalyticsRequest, averaged_metrics: set) -> List[dict]:
        """Process the analytics data based on request parameters"""
        if not data:
            return data

        df = pd.DataFrame(data)

        # Convert date column to datetime if it exists and isn't already datetime
        if 'date' in df.columns and not pd.api.types.is_datetime64_any_dtype(df['date']):
            df['date'] = pd.to_datetime(df['date'])

        # Apply time granularity aggregation if needed
        if params.time_granularity != TimeGranularity.DAILY and 'date' in df.columns:
            df = DataProcessor._aggregate_by_time(df, params.time_granularity, averaged_metrics)

        # Calculate moving averages if requested
        if params.moving_average_window and 'date' in df.columns:
            df = DataProcessor._calculate_moving_averages(
                df,
                params.moving_average_window,
                params.metrics.split(',')
            )

        # Add period comparison if requested
        if params.include_period_comparison and 'date' in df.columns:
            df = DataProcessor._add_period_comparison(
                df,
                params.metrics.split(',')
            )

        # Apply dimension aggregation if specified
        if params.aggregate_by:
            df = DataProcessor._aggregate_by_dimensions(
                df, 
                params.aggregate_by, 
                params.metric_aggregation
            )

        # Apply top N filter
        if params.data_format == DataFormat.COMPACT and params.top_n:
            primary_metric = params.metrics.split(',')[0]
            df = df.nlargest(params.top_n, primary_metric)

        # Add percentages if requested
        if params.include_percentages:
            DataProcessor._add_percentages(df, params.metrics.split(','))

        # Normalize metrics if requested
        if params.normalize_metrics:
            DataProcessor._normalize_metrics(df, params.metrics.split(','))

        # Round values if specified
        if params.round_digits is not None:
            numeric_cols = df.select_dtypes(include=['float64', 'int64']).columns
            df[numeric_cols] = df[numeric_cols].round(params.round_digits)

        # Generate summary if requested
        if params.data_format == DataFormat.SUMMARY:
            return DataProcessor._generate_summary(df, params)

        # Before returning, convert datetime objects to strings if they exist
        if 'date' in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df['date']):
                df['date'] = df['date'].dt.strftime('%Y-%m-%d')
            elif isinstance(df['date'].iloc[0], str) and 'W' in df['date'].iloc[0]:
                # Already in week format, leave as is
                pass
            elif isinstance(df['date'].iloc[0], str) and len(df['date'].iloc[0].split('-')) == 2:
                # Already in month format, leave as is
                pass
            else:
                # Try to format as date string if possible
                try:
                    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
                except:
                    pass  # Keep original format if conversion fails

        # Format the response to include period comparison data if it exists
        result = df.to_dict('records')
        if params.include_period_comparison and hasattr(df, 'attrs') and 'period_comparison' in df.attrs:
            # Ensure datetime objects in comparison data are converted to strings
            comparison_data = df.attrs['period_comparison']
            for metric, values in comparison_data.items():
                if isinstance(values.get('current_period'), pd.Timestamp):
                    values['current_period'] = values['current_period'].strftime('%Y-%m-%d')
                if isinstance(values.get('previous_period'), pd.Timestamp):
                    values['previous_period'] = values['previous_period'].strftime('%Y-%m-%d')
            
            return {
                'data': result,
                'period_comparison': comparison_data
            }
        
        return result

    @staticmethod
    def _aggregate_by_time(df: pd.DataFrame, granularity: TimeGranularity, 
                          averaged_metrics: set) -> pd.DataFrame:
        """
        Aggregate time-based data with proper handling of averaged metrics.
        
        Args:
            df: DataFrame to aggregate
            granularity: TimeGranularity enum value
            averaged_metrics: Set of metrics that should be averaged (weighted)
        """
        # Ensure date is datetime
        df = df.copy()  # Create a copy to avoid modifying original
        df['date'] = pd.to_datetime(df['date'])
        
        # Get all non-date columns that should be preserved in grouping
        group_cols = [col for col in df.columns if col != 'date' and not pd.api.types.is_numeric_dtype(df[col])]
        
        # Create a grouping date column while preserving original
        if granularity == TimeGranularity.WEEKLY:
            df['grouping_date'] = df['date'].dt.strftime('%Y-W%W')
        elif granularity == TimeGranularity.MONTHLY:
            df['grouping_date'] = df['date'].dt.strftime('%Y-%m')
        else:
            df['grouping_date'] = df['date'].dt.strftime('%Y-%m-%d')
        
        # Add grouping_date to group columns
        group_cols.append('grouping_date')
        
        # Create aggregation dictionary based on metric type
        agg_dict = {}
        
        for col in df.select_dtypes(include=['float64', 'int64']).columns:
            # For metrics like bounceRate, we need to calculate weighted average
            if col in averaged_metrics:
                # For bounce rate and engagement rate, weight by sessions
                if col in ['bounceRate', 'engagementRate']:
                    # Calculate weighted sum
                    df[f'{col}_weighted'] = df[col] * df['sessions']
                    agg_dict[f'{col}_weighted'] = 'sum'
                    agg_dict['sessions'] = 'sum'
                # For averageSessionDuration, weight by number of sessions
                elif col == 'averageSessionDuration':
                    df[f'{col}_weighted'] = df[col] * df['sessions']
                    agg_dict[f'{col}_weighted'] = 'sum'
                    agg_dict['sessions'] = 'sum'
                # For screenPageViewsPerSession, weight by sessions
                elif col == 'screenPageViewsPerSession':
                    df[f'{col}_weighted'] = df[col] * df['sessions']
                    agg_dict[f'{col}_weighted'] = 'sum'
                    agg_dict['sessions'] = 'sum'
            else:
                # For regular summable metrics, just sum
                agg_dict[col] = 'sum'
        
        # Perform the grouping
        grouped_df = df.groupby(group_cols).agg(agg_dict).reset_index()
        
        # Calculate final weighted averages
        for col in averaged_metrics:
            if col in df.columns:
                if col in ['bounceRate', 'engagementRate', 'averageSessionDuration', 'screenPageViewsPerSession']:
                    grouped_df[col] = grouped_df[f'{col}_weighted'] / grouped_df['sessions']
                    grouped_df.drop(f'{col}_weighted', axis=1, inplace=True)
        
        # Rename grouping_date back to date
        grouped_df = grouped_df.rename(columns={'grouping_date': 'date'})
        
        # Sort by date
        grouped_df = grouped_df.sort_values('date')
        
        return grouped_df

    @staticmethod
    def _aggregate_by_dimensions(df: pd.DataFrame, dimensions: List[str], 
                               agg_method: MetricAggregation) -> pd.DataFrame:
        numeric_cols = df.select_dtypes(include=['float64', 'int64']).columns
        
        if agg_method == MetricAggregation.SUM:
            return df.groupby(dimensions)[numeric_cols].sum().reset_index()
        elif agg_method == MetricAggregation.AVERAGE:
            return df.groupby(dimensions)[numeric_cols].mean().reset_index()
        elif agg_method == MetricAggregation.MIN:
            return df.groupby(dimensions)[numeric_cols].min().reset_index()
        elif agg_method == MetricAggregation.MAX:
            return df.groupby(dimensions)[numeric_cols].max().reset_index()

    @staticmethod
    def _add_percentages(df: pd.DataFrame, metrics: List[str]):
        for metric in metrics:
            if metric in df.columns:
                total = df[metric].sum()
                if total > 0:
                    df[f'{metric}_pct'] = (df[metric] / total) * 100

    @staticmethod
    def _normalize_metrics(df: pd.DataFrame, metrics: List[str]):
        for metric in metrics:
            if metric in df.columns:
                min_val = df[metric].min()
                max_val = df[metric].max()
                if max_val > min_val:
                    df[f'{metric}_normalized'] = (df[metric] - min_val) / (max_val - min_val)

    @staticmethod
    def _generate_summary(df: pd.DataFrame, params: GoogleAnalyticsRequest) -> dict:
        metrics = params.metrics.split(',')
        summary = {
            'summary_stats': {},
            'total_rows': len(df)
        }

        for metric in metrics:
            if metric in df.columns:
                summary['summary_stats'][metric] = {
                    'min': float(df[metric].min()),
                    'max': float(df[metric].max()),
                    'mean': float(df[metric].mean()),
                    'median': float(df[metric].median()),
                    'total': float(df[metric].sum())
                }

        return summary