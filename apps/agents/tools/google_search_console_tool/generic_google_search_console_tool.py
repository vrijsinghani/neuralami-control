import logging
from typing import Any, Type, List, Optional
from pydantic import BaseModel, Field, field_validator
from crewai_tools.tools.base_tool import BaseTool
from datetime import datetime
import json
from googleapiclient.errors import HttpError

# Import Django models
from django.core.exceptions import ObjectDoesNotExist
from apps.seo_manager.models import Client, SearchConsoleCredentials

logger = logging.getLogger(__name__)

class GoogleSearchConsoleRequest(BaseModel):
    """Input schema for the generic Google Search Console Request tool."""
    start_date: str = Field(
        description="Start date in YYYY-MM-DD format"
    )
    end_date: str = Field(
        description="End date in YYYY-MM-DD format"
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
        default=1000,
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

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_dates(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return value
        except ValueError:
            raise ValueError("Invalid date format. Use YYYY-MM-DD")

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

class GenericGoogleSearchConsoleTool(BaseTool):
    name: str = "Generic Google Search Console Data Fetcher"
    description: str = "Fetches Google Search Console data with customizable dimensions and filters."
    args_schema: Type[BaseModel] = GoogleSearchConsoleRequest

    def _run(self,
             client_id: int,
             start_date: str,
             end_date: str,
             dimensions: List[str] = ["query"],
             search_type: str = "web",
             row_limit: int = 1000,
             start_row: int = 0,
             aggregation_type: str = "auto",
             data_state: str = "final",
             dimension_filters: Optional[List[dict]] = None) -> dict:
        try:
            # Get client and credentials
            client = Client.objects.get(id=client_id)
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
                'startDate': start_date,
                'endDate': end_date,
                'dimensions': dimensions,
                'type': search_type,
                'rowLimit': row_limit,
                'startRow': start_row,
                'aggregationType': aggregation_type,
                'dataState': data_state
            }

            # Add dimension filters if provided
            if dimension_filters:
                request_body['dimensionFilterGroups'] = [{
                    'filters': dimension_filters
                }]

            # Execute the request
            response = service.searchanalytics().query(
                siteUrl=property_url,
                body=request_body
            ).execute()

            # Process and format the response
            return self._format_response(response, dimensions)

        except HttpError as e:
            logger.error(f"Google API Error: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': f"Google API Error: {str(e)}",
                'search_console_data': []
            }
        except Exception as e:
            logger.error(f"Error fetching Search Console data: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'search_console_data': []
            }

    def _format_response(self, response: dict, dimensions: List[str]) -> dict:
        """Format the Search Console API response into a structured format."""
        search_console_data = []
        
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