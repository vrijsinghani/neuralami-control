import logging
from typing import Any, Type, List, Optional
from pydantic import BaseModel, Field, field_validator
from crewai_tools.tools.base_tool import BaseTool
from datetime import datetime
import json
from googleapiclient.errors import HttpError
from enum import Enum
import pandas as pd

# Import Django models
from django.core.exceptions import ObjectDoesNotExist
from apps.seo_manager.models import Client, SearchConsoleCredentials

from apps.common.utils import DateProcessor

logger = logging.getLogger(__name__)

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
    """Input schema for the generic Google Search Console Request tool."""
    start_date: str = Field(
        description="""
        Start date in one of these formats:
        - YYYY-MM-DD (e.g., 2024-03-15)
        - Relative days: 'today', 'yesterday', 'NdaysAgo' (e.g., 7daysAgo)
        - Relative months: 'NmonthsAgo' (e.g., 3monthsAgo)
        
        Note: While Search Console API requires YYYY-MM-DD format, this tool
        automatically converts relative dates to the appropriate format.
        """
    )
    end_date: str = Field(
        description="""
        End date in one of these formats:
        - YYYY-MM-DD (e.g., 2024-03-15)
        - Relative days: 'today', 'yesterday', 'NdaysAgo' (e.g., 7daysAgo)
        - Relative months: 'NmonthsAgo' (e.g., 3monthsAgo)
        """
    )
    client_id: int = Field(
        description="The ID of the client"
    )
    dimensions: List[str] = Field(
        default=["query"],
        description="List of dimensions (country, device, page, query, searchAppearance, date)"
    )
    search_type: str = Field(
        default="web",
        description="Type of search results (web, discover, googleNews, news, image, video)"
    )
    row_limit: int = Field(
        default=50,
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
    name: str = "Search Console Data Tool"
    description: str = """
    Fetches data from Google Search Console with advanced processing capabilities.
    
    Key Features:
    - Flexible date ranges (e.g., '7daysAgo', '3monthsAgo', 'YYYY-MM-DD')
    - Core metrics: clicks, impressions, CTR, position
    - Dimensions: query, page, country, device, date
    - Data processing: aggregation, filtering, summaries
    
    Example Commands:
    1. Top performing queries:
       tool._run(
           client_id=123,
           dimensions=["query"],
           data_format="compact",
           top_n=10
       )
    
    2. Page performance over time:
       tool._run(
           client_id=123,
           dimensions=["page", "date"],
           time_granularity="weekly"
       )
    
    3. Country-wise click distribution:
       tool._run(
           client_id=123,
           dimensions=["country"],
           include_percentages=True
       )
    """
    args_schema: Type[BaseModel] = GoogleSearchConsoleRequest

    def _run(self,
             client_id: int,
             start_date: str,
             end_date: str,
             dimensions: List[str] = ["query"],
             search_type: str = "web",
             row_limit: int = 50,
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
             round_digits: Optional[int] = 2,
             include_period_comparison: bool = False,
             moving_average_window: Optional[int] = None) -> dict:
        try:
            # Convert kwargs to request object
            request_params = GoogleSearchConsoleRequest(
                client_id=client_id,
                start_date=start_date,
                end_date=end_date,
                dimensions=dimensions,
                search_type=search_type,
                row_limit=row_limit,
                start_row=start_row,
                aggregation_type=aggregation_type,
                data_state=data_state,
                dimension_filters=dimension_filters,
                data_format=data_format,
                top_n=top_n,
                time_granularity=time_granularity,
                metric_aggregation=metric_aggregation,
                include_percentages=include_percentages,
                normalize_metrics=normalize_metrics,
                round_digits=round_digits,
                include_period_comparison=include_period_comparison,
                moving_average_window=moving_average_window
            )
            
            # Get client and credentials
            client = Client.objects.get(id=request_params.client_id)
            sc_credentials = client.sc_credentials
            if not sc_credentials:
                raise ValueError("Missing Search Console credentials")

            service = sc_credentials.get_service()
            if not service:
                raise ValueError("Failed to initialize Search Console service")

            property_url = sc_credentials.get_property_url()
            if not property_url:
                raise ValueError("Missing or invalid Search Console property URL")

            # Prepare the request body
            request_body = {
                'startDate': request_params.start_date,
                'endDate': request_params.end_date,
                'dimensions': request_params.dimensions,
                'type': request_params.search_type,
                'rowLimit': request_params.row_limit,
                'startRow': request_params.start_row,
                'aggregationType': request_params.aggregation_type,
                'dataState': request_params.data_state
            }

            # Add dimension filters if provided
            if request_params.dimension_filters:
                request_body['dimensionFilterGroups'] = [{
                    'filters': request_params.dimension_filters
                }]

            # Execute the request
            response = service.searchanalytics().query(
                siteUrl=property_url,
                body=request_body
            ).execute()

            # Process the response
            raw_data = self._format_response(response, request_params.dimensions)
            
            if raw_data['success']:
                processed_data = SearchConsoleDataProcessor.process_data(
                    raw_data['search_console_data'],
                    request_params
                )
                
                # Handle period comparison format
                if isinstance(processed_data, dict) and 'period_comparison' in processed_data:
                    return {
                        'success': True,
                        'search_console_data': processed_data['data'],
                        'period_comparison': processed_data['period_comparison']
                    }
                
                return {
                    'success': True,
                    'search_console_data': processed_data
                }
            
            return raw_data

        except Exception as e:
            logger.error(f"Error in Search Console tool: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'search_console_data': []
            }

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