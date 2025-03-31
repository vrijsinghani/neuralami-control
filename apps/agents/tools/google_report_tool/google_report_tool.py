import logging
from typing import Any, Type, List, Optional, Dict, Union
from pydantic import BaseModel, Field, field_validator
from apps.agents.tools.base_tool import BaseTool
# Removed direct Google API imports:
# from google.analytics.data_v1beta import BetaAnalyticsDataClient
# from google.analytics.data_v1beta.types import (
#     DateRange,
#     Metric,
#     Dimension,
#     RunReportRequest,
#     OrderBy,
#     FilterExpression,
#     Filter,
#     MetricAggregation,
# )
from datetime import datetime
import json
# Removed direct Google API client build imports:
# from googleapiclient.errors import HttpError
# from googleapiclient.discovery import build
# from google.oauth2.credentials import Credentials
# from google.auth.transport.requests import Request
# Removed pandas import, handled by generic tool
# import pandas as pd

# Import the generic tools
from apps.agents.tools.google_analytics_tool.generic_google_analytics_tool import GenericGoogleAnalyticsTool, GoogleAnalyticsRequest, TimeGranularity, DataFormat
from apps.agents.tools.google_search_console_tool.generic_google_search_console_tool import GenericGoogleSearchConsoleTool, GoogleSearchConsoleRequest

# Remove direct Django model imports if not needed
# from django.core.exceptions import ObjectDoesNotExist

logger = logging.getLogger(__name__)

class GoogleReportToolInput(BaseModel):
    """Input schema for GoogleReportTool."""
    start_date: str = Field(description="The start date for the analytics data (YYYY-MM-DD).")
    end_date: str = Field(description="The end date for the analytics data (YYYY-MM-DD).")
    analytics_property_id: Union[str, int] = Field(
        description="The Google Analytics property ID to use for fetching data."
    )
    analytics_credentials: Dict[str, Any] = Field(
        description="The credentials needed to authenticate with Google Analytics. Must contain access_token, refresh_token, ga_client_id, client_secret."
    )
    search_console_property_url: str = Field(
        description="The Search Console property URL"
    )
    search_console_credentials: Dict[str, Any] = Field(
        description="Credentials for Search Console API. Must contain access_token, refresh_token, sc_client_id, client_secret."
    )
    client_id: Optional[Union[str, int]] = Field(
        None,
        description="Optional client ID for reference purposes only."
    )

    # Keep date validation if needed, generic tools also validate
    @field_validator("start_date", "end_date")
    @classmethod
    def validate_dates(cls, value: str) -> str:
        try:
            # Allow relative dates handled by generic tool
            if not any(suffix in value for suffix in ['daysAgo', 'monthsAgo', 'today', 'yesterday']):
                datetime.strptime(value, "%Y-%m-%d")
            return value
        except ValueError:
            raise ValueError("Invalid date format. Use YYYY-MM-DD or relative format (e.g., 7daysAgo).")

    @field_validator("analytics_property_id")
    @classmethod
    def ensure_property_id_is_string(cls, value) -> str:
        if value is None:
            raise ValueError("Analytics property ID cannot be None")
        return str(value)

    @field_validator("client_id")
    @classmethod
    def ensure_client_id_is_string(cls, value) -> Optional[str]:
        # If None, keep it None
        if value is None:
            return None
        # Convert int to string if needed
        return str(value)

class GoogleReportTool(BaseTool):
    name: str = "Google Analytics and Search Console Report Fetcher"
    description: str = "Fetches a predefined set of Google Analytics and Search Console reports for a specified client and date range."
    args_schema: Type[BaseModel] = GoogleReportToolInput

    def _run(
        self,
        start_date: str,
        end_date: str,
        analytics_property_id: Union[str, int],
        analytics_credentials: Dict[str, Any],
        search_console_property_url: str,
        search_console_credentials: Dict[str, Any],
        client_id: Optional[Union[str, int]] = None
    ) -> str:
        # Validate input using Pydantic schema
        try:
            input_data = GoogleReportToolInput(
                start_date=start_date,
                end_date=end_date,
                analytics_property_id=analytics_property_id,
                analytics_credentials=analytics_credentials,
                search_console_property_url=search_console_property_url,
                search_console_credentials=search_console_credentials,
                client_id=client_id  # This will be converted to str by the validator
            )
            # Convert property ID back to string after validation if needed
            analytics_property_id_str = str(input_data.analytics_property_id)
            # Ensure client_id is a string if not None
            client_id_str = str(input_data.client_id) if input_data.client_id is not None else None
        except ValueError as e:
            logger.error(f"Input validation error: {e}", exc_info=True)
            return json.dumps({'success': False, 'error': f"Input validation failed: {e}"})

        # Instantiate generic tools within _run
        ga_tool = GenericGoogleAnalyticsTool()
        sc_tool = GenericGoogleSearchConsoleTool()

        analytics_reports = {}
        analytics_error = None
        keyword_data = []
        landing_page_data = []
        search_console_error = None

        # --- Define GA Reports ---
        reports_config = [
            {
                "name": "traffic_sources",
                "metrics": "sessions,engagementRate,conversions",
                "dimensions": "sessionSource,sessionMedium",
                "limit": 10,
            },
            {
                "name": "page_performance",
                "metrics": "screenPageViews,engagementRate",
                "dimensions": "pagePath",
                "limit": 10,
            },
            {
                "name": "device_usage",
                "metrics": "sessions,engagementRate",
                "dimensions": "deviceCategory",
                "limit": 10,
            },
            {
                "name": "geographic_analysis_florida",
                "metrics": "sessions,engagementRate",
                "dimensions": "city,region",
                "dimension_filter": "region==Florida", # String format for generic tool
                "limit": 10,
            },
            {
                "name": "channel_performance",
                "metrics": "sessions,engagementRate,conversions",
                "dimensions": "sessionDefaultChannelGroup",
                "limit": 10,
            },
            {
                "name": "overall_traffic_trend",
                "metrics": "sessions,totalUsers,screenPageViews,conversions",
                "dimensions": "date",
                "time_granularity": TimeGranularity.WEEKLY, # Use enum for generic tool
                "limit": 366 # Let generic tool handle aggregation limit
            },
        ]

        # --- Fetch GA Reports using Generic Tool ---
        logger.info(f"Starting GA report fetching for property: {analytics_property_id_str}")
        for config in reports_config:
            report_name = config["name"]
            logger.info(f"Fetching GA report: {report_name}")
            try:
                # Map config to generic tool parameters
                ga_params = {
                    "analytics_property_id": analytics_property_id_str,
                    "analytics_credentials": analytics_credentials,
                    "start_date": start_date,
                    "end_date": end_date,
                    "metrics": config["metrics"],
                    "dimensions": config["dimensions"],
                    "limit": config.get("limit", 1000),
                    "dimension_filter": config.get("dimension_filter"),
                    "time_granularity": config.get("time_granularity", TimeGranularity.AUTO), # Pass granularity
                    "data_format": DataFormat.RAW # Get raw data, processing handled by generic tool if needed later
                }

                # Run the generic GA tool using the local variable
                ga_result_json = ga_tool._run(**ga_params)
                
                # Process result (could be dict or JSON string)
                try:
                    # Check if result is already a dict (not a JSON string)
                    if isinstance(ga_result_json, dict):
                        ga_result = ga_result_json
                    else:
                        # Try to parse as JSON string if it's not already a dict
                        ga_result = json.loads(ga_result_json)
                except (TypeError, json.JSONDecodeError) as e:
                    logger.error(f"Error processing GA tool result for {report_name}: {str(e)}")
                    ga_result = {
                        'success': False, 
                        'error': f"Failed to process GA tool result: {str(e)}",
                        'analytics_data': []
                    }

                if ga_result.get('success'):
                    analytics_reports[report_name] = ga_result.get('analytics_data', [])
                    logger.info(f"Successfully fetched GA report: {report_name} ({len(analytics_reports[report_name])} rows)")
                else:
                    error_msg = ga_result.get('error', 'Unknown GA tool error')
                    logger.error(f"Error fetching GA report '{report_name}': {error_msg}")
                    analytics_reports[report_name] = {"error": error_msg}
                    # If one report fails, store the error and continue? Or stop?
                    # Let's store the first critical error and potentially stop GA fetches
                    if not analytics_error: # Store first error
                        analytics_error = f"GA report '{report_name}': {error_msg}"
                    if "credentials" in error_msg or "permission" in error_msg or "quota" in error_msg:
                        logger.warning(f"Stopping further GA report fetches due to critical error: {error_msg}")
                        break # Stop fetching more GA reports on critical errors

            except Exception as e:
                error_msg = f"Exception calling GenericAnalyticsTool for report '{report_name}': {str(e)}"
                logger.error(error_msg, exc_info=True)
                analytics_reports[report_name] = {"error": error_msg}
                if not analytics_error: # Store first error
                    analytics_error = error_msg
                # Decide whether to break on general exceptions too
                # break

        # --- Fetch SC Reports using Generic Tool ---
        logger.info(f"Starting SC report fetching for property: {search_console_property_url}")
        sc_dimensions_to_fetch = ["query", "page"]
        sc_data_map = {"query": keyword_data, "page": landing_page_data}

        for dim in sc_dimensions_to_fetch:
            logger.info(f"Fetching SC report for dimension: {dim}")
            try:
                sc_params = {
                    "search_console_property_url": search_console_property_url,
                    "search_console_credentials": search_console_credentials,
                    "start_date": start_date,
                    "end_date": end_date,
                    "dimensions": [dim],
                    "row_limit": 50, # Fetch top 50
                    "data_format": DataFormat.RAW # Get raw data
                }

                # Run the generic SC tool using the local variable
                sc_result_json = sc_tool._run(**sc_params)
                
                # Process result (could be dict or JSON string)
                try:
                    # Check if result is already a dict (not a JSON string)
                    if isinstance(sc_result_json, dict):
                        sc_result = sc_result_json
                    else:
                        # Try to parse as JSON string if it's not already a dict
                        sc_result = json.loads(sc_result_json)
                except (TypeError, json.JSONDecodeError) as e:
                    logger.error(f"Error processing SC tool result for dimension '{dim}': {str(e)}")
                    sc_result = {
                        'success': False, 
                        'error': f"Failed to process SC tool result: {str(e)}",
                        'search_console_data': []
                    }

                if sc_result.get('success'):
                    fetched_data = sc_result.get('search_console_data', [])
                    if dim == "query":
                        keyword_data.extend(fetched_data)
                    elif dim == "page":
                        landing_page_data.extend(fetched_data)
                    logger.info(f"Successfully fetched SC report for dimension: {dim} ({len(fetched_data)} rows)")
                else:
                    error_msg = sc_result.get('error', 'Unknown SC tool error')
                    logger.error(f"Error fetching SC report for dimension '{dim}': {error_msg}")
                    # Store the first SC error
                    if not search_console_error:
                        search_console_error = f"SC dimension '{dim}': {error_msg}"
                    if "credentials" in error_msg or "permission" in error_msg or "quota" in error_msg:
                        logger.warning(f"Stopping further SC report fetches due to critical error: {error_msg}")
                        break # Stop fetching more SC reports

            except Exception as e:
                error_msg = f"Exception calling GenericSearchConsoleTool for dimension '{dim}': {str(e)}"
                logger.error(error_msg, exc_info=True)
                if not search_console_error: # Store first error
                    search_console_error = error_msg
                # break


        # --- Consolidate Results and Check Status ---
        final_analytics_reports = {k: v for k, v in analytics_reports.items() if not (isinstance(v, dict) and 'error' in v)}
        has_analytics_data = any(isinstance(v, list) and v for v in final_analytics_reports.values())
        has_search_console_data = bool(keyword_data or landing_page_data)

        combined_error_message = ""
        if analytics_error: combined_error_message += f"Analytics Error Summary: {analytics_error}. "
        if search_console_error: combined_error_message += f"Search Console Error Summary: {search_console_error}"
        combined_error_message = combined_error_message.strip()

        # Include detailed errors per report if available
        ga_report_errors = {k: v['error'] for k, v in analytics_reports.items() if isinstance(v, dict) and 'error' in v}

        final_payload = {
            'analytics_reports': final_analytics_reports,
            'keyword_data': keyword_data,
            'landing_page_data': landing_page_data,
            'start_date': start_date,
            'end_date': end_date,
            'analytics_property_id': analytics_property_id_str,
            'search_console_property_url': search_console_property_url,
            'client_id': client_id_str,
            # Include detailed GA errors if any occurred
            'analytics_errors': ga_report_errors if ga_report_errors else None
        }


        if not has_analytics_data and not has_search_console_data:
            if combined_error_message:
                # No data AND errors occurred
                final_payload['success'] = False
                final_payload['error'] = f"No data collected. Errors: {combined_error_message}"
                # Remove None error fields before returning
                final_payload = {k: v for k, v in final_payload.items() if v is not None}
                return json.dumps(final_payload)

            else:
                # No data and no specific errors reported (maybe just empty results)
                final_payload['success'] = True
                final_payload['message'] = "No data found for the specified criteria in Google Analytics or Search Console."
                # Remove None error fields before returning
                final_payload = {k: v for k, v in final_payload.items() if v is not None}
                return json.dumps(final_payload)

        # --- Format Final Success Output ---
        final_payload['success'] = True
        if combined_error_message:
            final_payload['partial_error'] = f"Operation partially succeeded. Errors: {combined_error_message}"

        # Remove None error fields before returning
        final_payload = {k: v for k, v in final_payload.items() if v is not None}
        return json.dumps(final_payload)

    # --- Remove Old Helper Methods ---
    # def _validate_credentials(...): removed
    # def _create_analytics_service(...): removed
    # def _create_search_console_service(...): removed
    # def _fetch_multiple_analytics_reports(...): removed
    # def _process_report_response(...): removed
    # def _aggregate_trend_to_weekly(...): removed
    # def _get_search_console_data(...): removed
