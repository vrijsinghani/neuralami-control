import logging
from typing import Any, Type, List, Optional, Dict, Union
from pydantic import BaseModel, Field, field_validator
from apps.agents.tools.base_tool import BaseTool
from datetime import datetime, timedelta
import json
import re
from googleapiclient.errors import HttpError
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

logger = logging.getLogger(__name__)

# --- Constants for Categorization ---
MIN_CLICKS = 1
MIN_IMPRESSIONS = 10
STRIKING_DISTANCE_MIN_POS = 5
STRIKING_DISTANCE_MAX_POS = 20
LOW_CTR_THRESHOLD = 2.0  # Percentage
LOW_RANK_THRESHOLD = 20
TOP_N = 50  # Default value for top N keywords
# --- End Constants ---

# Question-based query patterns
QUESTION_PATTERNS = [
    r'\b(what|how|why|where|when|who|which)\b',  # Question words
    r'\b(best|top|vs|versus|compare|difference|review)\b',  # Comparison/evaluation terms
    r'\b(guide|tutorial|steps|instructions|tips)\b',  # Instructional terms
    r'\?',  # Actual question marks
]

class GoogleRankingsToolInput(BaseModel):
    """Input schema for GoogleRankingsTool."""
    start_date: Optional[str] = Field(
        None,
        description="The start date for the analytics data (YYYY-MM-DD). If None, defaults to 90 days ago."
    )
    end_date: Optional[str] = Field(
        None,
        description="The end date for the analytics data (YYYY-MM-DD). If None, defaults to yesterday."
    )
    search_console_property_url: str = Field(
        description="The Search Console property URL"
    )
    search_console_credentials: Dict[str, Any] = Field(
        description="Credentials for Search Console API"
    )
    top_n: Optional[int] = Field(
        TOP_N,
        description=f"Number of top keywords to include in topN categories. Default is {TOP_N}."
    )

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_dates(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return value
        except ValueError:
            raise ValueError("Invalid date format. Use YYYY-MM-DD.")

    @field_validator("top_n")
    @classmethod
    def validate_top_n(cls, value: Optional[int]) -> int:
        if value is None:
            return TOP_N
        if value <= 0:
            raise ValueError("top_n must be a positive integer")
        return value

class GoogleRankingsTool(BaseTool):
    name: str = "Google Search Console Categorized Rankings Fetcher"
    description: str = (
        "Fetches and categorizes Google Search Console ranking data for a specified property and date range. "
        "Categories include 'striking_distance_keywords', 'high_impression_low_ctr', 'high_impression_low_rank', "
        "'question_based_queries', 'top_n_by_impressions', and 'top_n_by_rank'. "
        f"Filters data for Clicks > {MIN_CLICKS} and Impressions > {MIN_IMPRESSIONS}. "
        f"The top_n parameter (default: {TOP_N}) controls how many keywords to include in the topN categories."
    )
    args_schema: Type[BaseModel] = GoogleRankingsToolInput

    def _run(
        self,
        start_date: Optional[str],
        end_date: Optional[str],
        search_console_property_url: str,
        search_console_credentials: Dict[str, Any],
        top_n: Optional[int] = TOP_N,
        **kwargs: Any
    ) -> str:
        """
        Fetch, filter, and categorize ranking data from Google Search Console.
        Returns the categorized data in JSON format.
        """
        try:
            # Use the provided top_n or the default
            top_n = top_n or TOP_N

            # Validate credentials
            sc_required_fields = ['sc_client_id', 'client_secret', 'refresh_token']
            sc_missing_fields = [field for field in sc_required_fields if field not in search_console_credentials]

            if sc_missing_fields:
                sc_missing_fields_str = ', '.join(sc_missing_fields)
                logger.error(f"Missing required Search Console credential fields: {sc_missing_fields_str}")
                raise ValueError(f"Incomplete Search Console credentials. Missing: {sc_missing_fields_str}")

            # Create Search Console service
            search_console_service = self._create_search_console_service(search_console_credentials)
            if not search_console_service:
                raise ValueError("Failed to initialize Search Console service")

            if not search_console_property_url:
                raise ValueError("Missing or invalid Search Console property URL")

            # Determine date range (default to last 90 days if none provided)
            if not start_date or not end_date:
                today = datetime.now().date()
                default_end_date = today - timedelta(days=1)  # GSC data lags
                default_start_date = default_end_date - timedelta(days=89)  # 90 days total
                final_start_date_str = start_date or default_start_date.strftime('%Y-%m-%d')
                final_end_date_str = end_date or default_end_date.strftime('%Y-%m-%d')
                logger.info(f"Using date range: {final_start_date_str} to {final_end_date_str}")
            else:
                # Validate provided dates
                try:
                    datetime.strptime(start_date, '%Y-%m-%d')
                    datetime.strptime(end_date, '%Y-%m-%d')
                    final_start_date_str = start_date
                    final_end_date_str = end_date
                except ValueError:
                    raise ValueError("Invalid date format provided. Use YYYY-MM-DD.")

            # Fetch raw data for the single period
            raw_keyword_data = self._get_search_console_data(
                search_console_service,
                search_console_property_url,
                final_start_date_str,
                final_end_date_str,
                'query'
            )

            # Filter and Categorize Data
            categorized_data = {
                "striking_distance_keywords": [],
                "high_impression_low_ctr": [],
                "high_impression_low_rank": [],
                "question_based_queries": [],
                "top_n_by_impressions": [],
                "top_n_by_rank": [],
            }

            # Apply base filters first (for all categories except topN)
            filtered_data = []
            for item in raw_keyword_data:
                clicks = item.get('Clicks', 0)
                impressions = item.get('Impressions', 0)

                if clicks >= MIN_CLICKS and impressions >= MIN_IMPRESSIONS:
                    filtered_data.append(item)

            # Create topN categories first (these don't use the processed_keywords tracking)
            # Top N by Impressions
            by_impressions = sorted(raw_keyword_data, key=lambda x: x.get('Impressions', 0), reverse=True)
            categorized_data["top_n_by_impressions"] = by_impressions[:top_n]

            # Top N by Rank (lowest position number = best rank)
            by_rank = sorted(raw_keyword_data, key=lambda x: x.get('Avg Position', 999))
            categorized_data["top_n_by_rank"] = by_rank[:top_n]

            # Now process the other categories with mutual exclusivity
            processed_keywords = set()  # Track keywords already categorized

            # Process question-based queries first (these can be important for content strategy)
            for item in filtered_data:
                keyword = item.get('Keyword', '')

                # Check if it's a question-based query
                is_question = any(re.search(pattern, keyword, re.IGNORECASE) for pattern in QUESTION_PATTERNS)

                if is_question and keyword not in processed_keywords:
                    categorized_data["question_based_queries"].append(item)
                    processed_keywords.add(keyword)

            # Now process the remaining categories
            for item in filtered_data:
                keyword = item.get('Keyword', '')
                if keyword in processed_keywords:
                    continue  # Skip if already categorized

                position = item.get('Avg Position', 999)
                ctr = item.get('CTR (%)', 0)

                # Striking Distance
                if STRIKING_DISTANCE_MIN_POS < position <= STRIKING_DISTANCE_MAX_POS:
                    categorized_data["striking_distance_keywords"].append(item)
                    processed_keywords.add(keyword)
                    continue

                # High Impression, Low CTR
                if ctr < LOW_CTR_THRESHOLD:
                    categorized_data["high_impression_low_ctr"].append(item)
                    processed_keywords.add(keyword)
                    continue

                # High Impression, Low Rank
                if position > LOW_RANK_THRESHOLD:
                    categorized_data["high_impression_low_rank"].append(item)
                    processed_keywords.add(keyword)
                    continue

            # Build the response structure
            response = {
                'success': True,
                'property_url': search_console_property_url,
                'start_date': final_start_date_str,
                'end_date': final_end_date_str,
                'filters_applied': {
                    'min_clicks': MIN_CLICKS,
                    'min_impressions': MIN_IMPRESSIONS,
                    'top_n': top_n
                },
                'categorization_criteria': {
                    'striking_distance': f"Position > {STRIKING_DISTANCE_MIN_POS} and <= {STRIKING_DISTANCE_MAX_POS}",
                    'high_impression_low_ctr': f"CTR < {LOW_CTR_THRESHOLD}%",
                    'high_impression_low_rank': f"Position > {LOW_RANK_THRESHOLD}",
                    'question_based_queries': "Contains question words, comparison terms, or question marks",
                    'top_n_by_impressions': f"Top {top_n} keywords by impression volume",
                    'top_n_by_rank': f"Top {top_n} keywords by position (lowest position number first)"
                },
                'category_counts': {
                    category: len(keywords) for category, keywords in categorized_data.items()
                },
                'categorized_data': categorized_data,
                'total_keywords_fetched': len(raw_keyword_data),
                'total_keywords_filtered': len(filtered_data),
                'total_unique_keywords_categorized': len(processed_keywords) + top_n * 2,  # Approximate, may have overlap
                'error': None
            }

            if len(raw_keyword_data) == 0:
                response['message'] = "No keyword data returned from Search Console for the specified period."
                response['success'] = False
            elif len(filtered_data) == 0:
                response['message'] = f"Data fetched, but no keywords met the minimum criteria of {MIN_CLICKS} clicks and {MIN_IMPRESSIONS} impressions."
                response['success'] = True  # Still successful, just no data met criteria

            return json.dumps(response, indent=2)

        except Exception as e:
            logger.error(f"Error in categorized ranking tool: {str(e)}")
            error_response = {
                'success': False,
                'error': str(e),
                'property_url': search_console_property_url,
                'start_date': start_date,
                'end_date': end_date,
                'top_n': top_n
            }
            return json.dumps(error_response, indent=2)

    def _create_search_console_service(self, credentials: Dict[str, Any]):
        """Create Search Console service from credentials dictionary"""
        try:
            credentials_obj = Credentials(
                None,
                refresh_token=credentials.get('refresh_token'),
                token_uri='https://oauth2.googleapis.com/token',
                client_id=credentials.get('sc_client_id'),
                client_secret=credentials.get('client_secret')
            )
            credentials_obj.refresh(Request())
            search_console_service = build('searchconsole', 'v1', credentials=credentials_obj)
            return search_console_service
        except Exception as e:
            logger.error(f"Error creating Search Console service: {str(e)}")
            if 'invalid_grant' in str(e) or 'expired' in str(e):
                raise ValueError(f"Search Console authentication error: {str(e)}") from e
            return None

    def _get_search_console_data(self, service, property_url, start_date, end_date, dimension):
        """Fetch data from Google Search Console API"""
        try:
            # Simplified URL handling assuming it's usually just the URL string
            site_url = property_url
            logger.info(f"Using Search Console property URL: {site_url} for {start_date} to {end_date}")

            # Increase rowLimit to get more data before filtering
            ROW_LIMIT = 5000  # Fetch more rows initially

            response = service.searchanalytics().query(
                siteUrl=site_url,
                body={
                    'startDate': start_date,
                    'endDate': end_date,
                    'dimensions': [dimension],
                    'rowLimit': ROW_LIMIT,
                    'dataState': 'all'  # Include fresh data if available
                }
            ).execute()

            search_console_data = []
            for row in response.get('rows', []):
                search_console_data.append({
                    'Keyword': row['keys'][0],
                    'Clicks': row.get('clicks', 0),
                    'Impressions': row.get('impressions', 0),
                    'CTR (%)': round(row.get('ctr', 0) * 100, 2),
                    'Avg Position': round(row.get('position', 999), 1)
                })

            logger.info(f"Fetched {len(search_console_data)} rows from Search Console.")
            return search_console_data

        except HttpError as error:
            logger.error(f"An HTTP error occurred while fetching Search Console data: {error.resp.status} {error.content}")
            error_details = f"HTTP {error.resp.status}"
            try:
                content = json.loads(error.content)
                error_details += f": {content.get('error', {}).get('message', 'No specific message')}"
            except json.JSONDecodeError:
                error_details += f": {error.content.decode('utf-8', errors='ignore')}"

            if error.resp.status in [403, 404]:
                raise ValueError(f"Search Console API Error: Check property URL ('{site_url}') and permissions. Details: {error_details}") from error
            else:
                raise RuntimeError(f"Search Console API Error: {error_details}") from error

        except Exception as e:
            logger.error(f"Unexpected error fetching Search Console data: {str(e)}")
            raise RuntimeError(f"Unexpected error during Search Console fetch: {str(e)}") from e