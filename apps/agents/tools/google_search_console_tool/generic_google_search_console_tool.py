import logging
from typing import Any, Type, List, Optional, ClassVar, Dict
from pydantic import (
    BaseModel, 
    ConfigDict, 
    Field, 
    field_validator,
    BaseModel as PydanticBaseModel
)
from apps.agents.tools.base_tool import BaseTool
from datetime import datetime
import json
from googleapiclient.errors import HttpError
from enum import Enum
import pandas as pd
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Import Django models
from django.core.exceptions import ObjectDoesNotExist
from apps.seo_manager.models import SearchConsoleCredentials

from apps.common.utils import DateProcessor

logger = logging.getLogger(__name__)

"""
Generic Google Search Console Tool for fetching search performance data.

Example usage:
    tool = GenericGoogleSearchConsoleTool()
    
    # Basic usage with required parameters
    result = tool._run(
        search_console_property_url="https://www.example.com/",
        search_console_credentials={
            "access_token": "your_access_token",
            "refresh_token": "your_refresh_token",
            "sc_client_id": "your_client_id",
            "client_secret": "your_client_secret"
        },
        start_date="7daysAgo",
        end_date="today"
    )
    
    # Custom query with filters
    result = tool._run(
        search_console_property_url="https://www.example.com/",
        search_console_credentials=credentials_dict,
        start_date="28daysAgo",
        end_date="today",
        dimensions=["query", "page", "device"],
        search_type="web",
        dimension_filters=[{
            "dimension": "country",
            "operator": "equals",
            "expression": "usa"
        }],
        row_limit=1000
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

class GoogleSearchConsoleRequest(BaseModel):
    """Schema for Google Search Console data requests."""
    
    model_config = {
        "use_enum_values": True,
        "extra": "ignore"
    }
    
    # Required credential fields
    search_console_credentials: Dict[str, Any] = Field(
        ...,
        description="Search Console credential dictionary containing required OAuth2 credentials: access_token, refresh_token, sc_client_id, client_secret"
    )
    
    search_console_property_url: str = Field(
        ...,
        description="Search Console property URL to fetch data from"
    )
    
    start_date: str = Field(
        default="28daysAgo",
        description="Start date (YYYY-MM-DD or relative like '7daysAgo')"
    )
    end_date: str = Field(
        default="yesterday",
        description="End date (YYYY-MM-DD or relative like 'today')"
    )
    dimensions: List[str] = Field(
        default=["query"],
        description="Dimensions to fetch (query, page, country, device, date)"
    )
    search_type: str = Field(
        default="web",
        description="Type of search results (web, discover, news, etc.)"
    )
    row_limit: int = Field(
        default=250,
        description="Number of rows to return (1-25000)"
    )
    start_row: int = Field(
        default=0,
        description="Starting row for pagination"
    )
    aggregation_type: str = Field(
        default="auto",
        description="How to aggregate results (auto, byPage, byProperty)"
    )
    data_state: str = Field(
        default="final",
        description="Data state to return (all, final)"
    )
    dimension_filters: Optional[List[dict]] = Field(
        default=None,
        description="List of dimension filters"
    )

    # Data Processing Options
    data_format: DataFormat = Field(
        default=DataFormat.RAW,
        description="""
        How to format the returned data:
        - 'raw': Returns all data points (use for detailed analysis)
        - 'summary': Returns statistical summary (min/max/mean/median) - best for high-level insights
        - 'compact': Returns top N results (good for finding top performers)
        
        Example use cases:
        - For keyword analysis: use 'raw' with query dimension
        - For performance overview: use 'summary'
        - For top pages: use 'compact' with top_n=10
        """
    )

    top_n: Optional[int] = Field(
        default=None,
        description="""
        Return only top N results by clicks or impressions.
        
        Example use cases:
        - top_n=10 with dimensions=['query'] → top 10 keywords
        - top_n=5 with dimensions=['page'] → top 5 pages
        - top_n=3 with dimensions=['country'] → top 3 countries
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
        - For daily CTR fluctuations: use 'daily'
        - For weekly performance trends: use 'weekly'
        - For long-term position changes: use 'monthly'
        """
    )

    metric_aggregation: MetricAggregation = Field(
        default=MetricAggregation.SUM,
        description="""
        How to aggregate metrics when grouping data.
        
        Note: 
        - 'sum' for clicks and impressions
        - 'average' for CTR and position
        """
    )

    include_percentages: bool = Field(
        default=False,
        description="""
        Add percentage calculations relative to totals.
        Adds '_pct' suffix to metrics (e.g., 'clicks_pct').
        
        Example use cases:
        - Click distribution across pages
        - Impression share by country
        - CTR comparison across devices
        """
    )

    normalize_metrics: bool = Field(
        default=False,
        description="""
        Scale numeric metrics to 0-1 range for easier comparison.
        Adds '_normalized' suffix to metrics.
        
        Use when:
        - Comparing high-impression vs low-impression queries
        - Analyzing position vs CTR correlation
        - Creating visualizations
        """
    )

    round_digits: Optional[int] = Field(
        default=2,
        description="Round numeric values to specified digits"
    )

    include_period_comparison: bool = Field(
        default=False,
        description="""
        Include comparison with previous period.
        
        Example use cases:
        - Month-over-month ranking changes
        - Year-over-year click growth
        - Week-over-week CTR improvement
        
        Returns additional fields:
        - previous_period_value
        - percentage_change
        """
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

    @field_validator("dimensions")
    @classmethod
    def validate_dimensions(cls, value: List[str]) -> List[str]:
        valid_dimensions = ["country", "device", "page", "query", "searchAppearance", "date"]
        for dim in value:
            if dim not in valid_dimensions:
                raise ValueError(f"Invalid dimension: {dim}. Must be one of {valid_dimensions}")
        return value

    @field_validator("search_type")
    @classmethod
    def validate_search_type(cls, value: str) -> str:
        valid_types = ["web", "discover", "googleNews", "news", "image", "video"]
        if value not in valid_types:
            raise ValueError(f"Invalid search type. Must be one of {valid_types}")
        return value

    @field_validator("row_limit")
    @classmethod
    def validate_row_limit(cls, value: int) -> int:
        if not 1 <= value <= 25000:
            raise ValueError("Row limit must be between 1 and 25000")
        return value

class SearchConsoleDataProcessor:
    @staticmethod
    def _add_period_comparison(df: pd.DataFrame) -> pd.DataFrame:
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
        metrics = ['clicks', 'impressions', 'ctr', 'position']
        comparison_data = {}
        
        for metric in metrics:
            if metric in df.columns:
                current_value = current_period[metric].mean()
                previous_value = previous_period[metric].mean()
                
                # Add comparison metrics
                df[f'{metric}_previous'] = previous_value
                df[f'{metric}_change'] = ((current_value - previous_value) / previous_value * 100 
                                        if previous_value != 0 else 0)
                
                comparison_data[metric] = {
                    'current_period': current_value,
                    'previous_period': previous_value,
                    'percent_change': ((current_value - previous_value) / previous_value * 100 
                                     if previous_value != 0 else 0)
                }
        
        # Add comparison summary to the DataFrame
        df.attrs['period_comparison'] = comparison_data
        
        return df

    @staticmethod
    def process_data(data: List[dict], params: GoogleSearchConsoleRequest) -> List[dict]:
        """Process the search console data based on request parameters"""
        if not data:
            return data

        df = pd.DataFrame(data)

        # Apply time granularity aggregation if needed
        if params.time_granularity != TimeGranularity.DAILY and 'date' in df.columns:
            df = SearchConsoleDataProcessor._aggregate_by_time(df, params.time_granularity)

        # Calculate moving averages if requested
        if params.moving_average_window and 'date' in df.columns:
            df = SearchConsoleDataProcessor._calculate_moving_averages(
                df,
                params.moving_average_window
            )

        # Add period comparison if requested
        if params.include_period_comparison and 'date' in df.columns:
            df = SearchConsoleDataProcessor._add_period_comparison(df)

        # Apply top N filter
        if params.data_format == DataFormat.COMPACT and params.top_n:
            df = df.nlargest(params.top_n, 'clicks')  # Default to sorting by clicks

        # Add percentages if requested
        if params.include_percentages:
            for metric in ['clicks', 'impressions']:
                total = df[metric].sum()
                if total > 0:
                    df[f'{metric}_pct'] = (df[metric] / total) * 100

        # Normalize metrics if requested
        if params.normalize_metrics:
            for metric in ['clicks', 'impressions', 'position']:
                min_val = df[metric].min()
                max_val = df[metric].max()
                if max_val > min_val:
                    df[f'{metric}_normalized'] = (df[metric] - min_val) / (max_val - min_val)

        # Round values
        if params.round_digits is not None:
            numeric_cols = df.select_dtypes(include=['float64', 'int64']).columns
            df[numeric_cols] = df[numeric_cols].round(params.round_digits)

        # Generate summary if requested
        if params.data_format == DataFormat.SUMMARY:
            return SearchConsoleDataProcessor._generate_summary(df)

        # Format the response to include period comparison data if it exists
        result = df.to_dict('records')
        if params.include_period_comparison and hasattr(df, 'attrs') and 'period_comparison' in df.attrs:
            return {
                'data': result,
                'period_comparison': df.attrs['period_comparison']
            }
        
        return result

    @staticmethod
    def _aggregate_by_time(df: pd.DataFrame, granularity: TimeGranularity) -> pd.DataFrame:
        df['date'] = pd.to_datetime(df['date'])
        
        # Get all non-date columns that should be preserved in grouping
        group_cols = [col for col in df.columns if col != 'date' and not pd.api.types.is_numeric_dtype(df[col])]
        
        if granularity == TimeGranularity.WEEKLY:
            df['date'] = df['date'].dt.strftime('%Y-W%W')
        elif granularity == TimeGranularity.MONTHLY:
            df['date'] = df['date'].dt.strftime('%Y-%m')
        
        # Add date back to group columns
        group_cols.append('date')
        
        # Define aggregation rules for different metric types
        agg_dict = {
            'clicks': 'sum',
            'impressions': 'sum',
            'ctr': 'mean',
            'position': 'mean'
        }
        
        # Group by all dimension columns including date
        return df.groupby(group_cols).agg(agg_dict).reset_index()

    @staticmethod
    def _generate_summary(df: pd.DataFrame) -> dict:
        """Generate statistical summary of the data"""
        metrics = ['clicks', 'impressions', 'ctr', 'position']
        summary = {
            'summary_stats': {},
            'total_rows': len(df)
        }

        for metric in metrics:
            summary['summary_stats'][metric] = {
                'min': float(df[metric].min()),
                'max': float(df[metric].max()),
                'mean': float(df[metric].mean()),
                'median': float(df[metric].median()),
                'total': float(df[metric].sum()) if metric in ['clicks', 'impressions'] else None
            }

        return summary

    @staticmethod
    def _calculate_moving_averages(df: pd.DataFrame, window: int) -> pd.DataFrame:
        """Calculate moving averages for core metrics"""
        if 'date' not in df.columns:
            return df
            
        # Ensure date is datetime for proper sorting
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        # Calculate moving averages for all numeric metrics
        metrics = ['clicks', 'impressions', 'ctr', 'position']
        for metric in metrics:
            if metric in df.columns:
                df[f'{metric}_ma{window}'] = df[metric].rolling(
                    window=window,
                    min_periods=1  # Allow partial windows at the start
                ).mean()
        
        return df

class GenericGoogleSearchConsoleTool(BaseTool):
    """Google Search Console data fetching tool."""
    name: str = "Search Console Data Tool"
    description: str = """
    Fetches data from Google Search Console with advanced processing capabilities.
    
    Required Parameters:
    - search_console_property_url: The property URL to fetch data from
    - search_console_credentials: Dictionary containing the required OAuth2 credentials:
        - access_token
        - refresh_token
        - sc_client_id
        - client_secret
    
    Optional Parameters (with defaults):
    - start_date: Start date for data range (default: "28daysAgo")
    - end_date: End date for data range (default: "yesterday")
    - dimensions: List of dimensions to fetch (default: ["query"])
    - search_type: Type of search results (default: "web")
    
    Key Features:
    - Flexible date ranges (e.g., '7daysAgo', '3monthsAgo', 'YYYY-MM-DD')
    - Core metrics: clicks, impressions, CTR, position
    - Dimensions: query, page, country, device, date
    - Data processing: aggregation, filtering, summaries
    
    Example Commands:
    1. Basic performance data:
       tool._run(
           search_console_property_url="https://www.example.com/",
           search_console_credentials=credentials_dict
       )
    
    2. Top queries analysis:
       tool._run(
           search_console_property_url="https://www.example.com/",
           search_console_credentials=credentials_dict,
           dimensions=["query"],
           data_format="compact",
           top_n=10
       )
    
    3. Device performance:
       tool._run(
           search_console_property_url="https://www.example.com/",
           search_console_credentials=credentials_dict,
           dimensions=["device"],
           include_period_comparison=True
       )
    """
    
    args_schema: Type[BaseModel] = GoogleSearchConsoleRequest

    def _run(
        self,
        start_date: str,
        end_date: str,
        dimensions: List[str] = ["query"],
        search_type: str = "web",
        row_limit: int = 250,
        start_row: int = 0,
        aggregation_type: str = "auto",
        data_state: str = "final",
        dimension_filters: Optional[List[dict]] = None,
        data_format: DataFormat = DataFormat.RAW,
        top_n: Optional[int] = None,
        time_granularity: TimeGranularity = TimeGranularity.AUTO,
        metric_aggregation: MetricAggregation = MetricAggregation.SUM,
        include_percentages: bool = False,
        normalize_metrics: bool = False,
        round_digits: Optional[int] = None,
        include_period_comparison: bool = False,
        moving_average_window: Optional[int] = None,
        search_console_credentials: Optional[Dict[str, Any]] = None,
        search_console_property_url: Optional[str] = None,
    ) -> str:
        """Execute the tool with validated parameters"""
        try:
            # Create a dictionary of all parameters to validate with Pydantic
            params_dict = {
                "start_date": start_date,
                "end_date": end_date,
                "dimensions": dimensions,
                "search_type": search_type,
                "row_limit": row_limit,
                "start_row": start_row,
                "aggregation_type": aggregation_type,
                "data_state": data_state,
                "dimension_filters": dimension_filters,
                "data_format": data_format,
                "top_n": top_n,
                "time_granularity": time_granularity,
                "metric_aggregation": metric_aggregation,
                "include_percentages": include_percentages,
                "normalize_metrics": normalize_metrics,
                "round_digits": round_digits,
                "include_period_comparison": include_period_comparison,
                "moving_average_window": moving_average_window,
                "search_console_credentials": search_console_credentials,
                "search_console_property_url": search_console_property_url
            }
            
            # Validate parameters using the schema
            params = self.args_schema(**params_dict)
            
            # Validate required parameters
            if not params.search_console_credentials:
                raise ValueError("Missing required parameter: search_console_credentials")
                
            if not params.search_console_property_url:
                raise ValueError("Missing required parameter: search_console_property_url")
            
            # Create service using provided credentials
            try:
                logger.debug("Creating credentials object")
                creds = Credentials(
                    token=params.search_console_credentials.get('access_token'),
                    refresh_token=params.search_console_credentials.get('refresh_token'),
                    token_uri=params.search_console_credentials.get('token_uri', 'https://oauth2.googleapis.com/token'),
                    client_id=params.search_console_credentials.get('sc_client_id'),
                    client_secret=params.search_console_credentials.get('client_secret'),
                    scopes=params.search_console_credentials.get('scopes', ['https://www.googleapis.com/auth/webmasters.readonly'])
                )
                
                # Try to refresh token if needed
                if creds.refresh_token:
                    try:
                        logger.debug("Attempting to refresh token")
                        request = Request()
                        creds.refresh(request)
                        logger.debug("Successfully refreshed token")
                    except Exception as refresh_error:
                        error_message = str(refresh_error)
                        logger.error(f"Failed to refresh token: {error_message}")
                        if "invalid_grant" in error_message.lower():
                            raise ValueError("Credentials have expired or are invalid. Please reconnect the account.")
                
                # Create service
                logger.debug("Building Search Console service")
                service = build('searchconsole', 'v1', credentials=creds)
                property_url = params.search_console_property_url
                
            except Exception as cred_error:
                logger.error(f"Failed to create Search Console service: {str(cred_error)}")
                raise ValueError(f"Failed to initialize Search Console service: {str(cred_error)}")

            # Prepare the request body
            request_body = {
                'startDate': params.start_date,
                'endDate': params.end_date,
                'dimensions': params.dimensions,
                'type': params.search_type,
                'rowLimit': params.row_limit,
                'startRow': params.start_row,
                'aggregationType': params.aggregation_type,
                'dataState': params.data_state
            }

            # Add dimension filters if provided
            if params.dimension_filters:
                filters = []
                for filter_dict in params.dimension_filters:
                    if isinstance(filter_dict['expression'], list):
                        # For notEquals/notContains, create an OR group of NOT conditions
                        if filter_dict['operator'] in ['notEquals', 'notContains']:
                            filters.append({
                                'groupType': 'or',
                                'filters': [{
                                    'dimension': filter_dict['dimension'],
                                    'operator': 'notContains' if filter_dict['operator'] == 'notContains' else 'notEquals',
                                    'expression': expr.lower()  # Case-insensitive matching
                                } for expr in filter_dict['expression']]
                            })
                        else:
                            # For other operators, create individual filters
                            for expr in filter_dict['expression']:
                                filters.append({
                                    'dimension': filter_dict['dimension'],
                                    'operator': filter_dict['operator'],
                                    'expression': expr.lower()  # Case-insensitive matching
                                })
                    else:
                        filters.append({
                            'dimension': filter_dict['dimension'],
                            'operator': filter_dict['operator'],
                            'expression': filter_dict['expression'].lower()  # Case-insensitive matching
                        })

                # Create the final filter group structure
                request_body['dimensionFilterGroups'] = [{
                    'groupType': 'and',
                    'filters': filters
                }]

            # Execute the request
            try:
                logger.debug(f"Executing Search Console query with dimensions: {params.dimensions}")
                response = service.searchanalytics().query(
                    siteUrl=property_url,
                    body=request_body
                ).execute()
                logger.debug(f"Received response with {len(response.get('rows', []))} rows")
            except HttpError as http_error:
                error_message = str(http_error)
                logger.error(f"HTTP error in Search Console API: {error_message}")
                
                # Create detailed error message based on exception content
                detailed_message = "Failed to execute Search Console query"
                
                if "403" in error_message or "permission" in error_message.lower():
                    detailed_message = "Permission denied. Ensure you have the correct access permissions."
                elif "429" in error_message or "quota" in error_message.lower():
                    detailed_message = "API quota exceeded. Please try again later."
                elif "401" in error_message or "unauthorized" in error_message.lower():
                    detailed_message = "Authentication failed. Please check your credentials."
                
                result = {
                    'success': False,
                    'error': detailed_message,
                    'error_details': error_message,
                    'property_url': property_url
                }
                
                # Convert to JSON string to match other working tools
                return json.dumps(result)

            # Process the response
            raw_data = self._format_response(response, params.dimensions)
            
            if raw_data['success']:
                processed_data = SearchConsoleDataProcessor.process_data(
                    raw_data['search_console_data'],
                    params
                )
                
                # Handle period comparison format
                if isinstance(processed_data, dict) and 'period_comparison' in processed_data:
                    result = {
                        'success': True,
                        'search_console_data': processed_data['data'],
                        'period_comparison': processed_data['period_comparison'],
                        'property_url': property_url,
                        'start_date': params.start_date,
                        'end_date': params.end_date
                    }
                else:
                    result = {
                    'success': True,
                        'search_console_data': processed_data,
                        'property_url': property_url,
                        'start_date': params.start_date,
                        'end_date': params.end_date
                }
            else:
                # Add property reference to raw data
                raw_data['property_url'] = property_url
                result = raw_data
            
            # Convert to JSON string to match other working tools
            return json.dumps(result)

        except Exception as e:
            logger.error(f"Search Console tool error: {str(e)}", exc_info=True)
            
            # Create detailed error message based on exception content
            error_message = str(e)
            detailed_message = "Failed to execute Search Console tool"
            
            if "credentials" in error_message.lower() or "authentication" in error_message.lower():
                detailed_message = "Authentication failed. Please check your credentials."
                if "expired" in error_message.lower() or "invalid_grant" in error_message.lower():
                    detailed_message = "Credentials have expired. Please reconnect your accounts."
            elif "quota" in error_message.lower() or "rate limit" in error_message.lower():
                detailed_message = "API quota exceeded. Please try again later."
            elif "permission" in error_message.lower() or "403" in error_message:
                detailed_message = "Permission denied. Ensure you have the correct access permissions."
            
            result = {
                'success': False,
                'error': detailed_message,
                'error_details': str(e),
                'search_console_data': []
            }
            
            # Convert to JSON string to match other working tools
            return json.dumps(result)

    def _format_response(self, response: dict, dimensions: List[str]) -> dict:
        """Format the Search Console API response into a structured format."""
        search_console_data = []
        
        # Clean dimension names - strip whitespace
        dimensions = [d.strip() for d in dimensions]
        
        for row in response.get('rows', []):
            data_point = {}
            
            # Process dimension values
            for i, dimension in enumerate(dimensions):
                value = row['keys'][i]
                data_point[dimension] = value
            
            # Add metrics
            data_point.update({
                'clicks': row.get('clicks', 0),
                'impressions': row.get('impressions', 0),
                'ctr': round(row.get('ctr', 0) * 100, 2),
                'position': round(row.get('position', 0), 2)
            })
            
            search_console_data.append(data_point)

        return {
            'success': True,
            'search_console_data': search_console_data
        }