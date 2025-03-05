import logging
from typing import Any, Type, List, Optional
from pydantic import BaseModel, Field, field_validator
from apps.agents.tools.base_tool import BaseTool
from datetime import datetime
import json
from googleapiclient.errors import HttpError

# Import Django models
from django.core.exceptions import ObjectDoesNotExist
from apps.seo_manager.models import (
    Client, 
    KeywordRankingHistory,
    TargetedKeyword
)
from django.db import transaction
from apps.seo_manager.utils import get_monthly_date_ranges

logger = logging.getLogger(__name__)

class GoogleRankingsToolInput(BaseModel):
    """Input schema for GoogleRankingsTool."""
    start_date: str = Field(description="The start date for the analytics data (YYYY-MM-DD).")
    end_date: str = Field(description="The end date for the analytics data (YYYY-MM-DD).")
    client_id: int = Field(description="The ID of the client to fetch Google Analytics data for.")

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_dates(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return value
        except ValueError:
            raise ValueError("Invalid date format. Use YYYY-MM-DD.")

class GoogleRankingsTool(BaseTool):
    name: str = "Google Search Console Rankings Fetcher"
    description: str = "Fetches and stores Google Search Console ranking data for a specified client and date range."
    args_schema: Type[BaseModel] = GoogleRankingsToolInput

    def _run(self, start_date: str, end_date: str, client_id: int, **kwargs: Any) -> Any:
        total_stored_rankings = 0
        try:
            client = Client.objects.get(id=client_id)
            sc_credentials = client.sc_credentials
            
            if not sc_credentials:
                raise ValueError("Missing Search Console credentials")
            
            # Get authenticated service using model method
            search_console_service = sc_credentials.get_service()
            if not search_console_service:
                raise ValueError("Failed to initialize Search Console service")
                
            # Get property URL using model method
            property_url = sc_credentials.get_property_url()
            if not property_url:
                raise ValueError("Missing or invalid Search Console property URL")
            
            # Check if specific dates were provided (for collect_rankings)
            if start_date and end_date:
                date_ranges = [(
                    datetime.strptime(start_date, '%Y-%m-%d').date(),
                    datetime.strptime(end_date, '%Y-%m-%d').date()
                )]
            else:
                # For backfill_rankings, get last 12 months
                date_ranges = get_monthly_date_ranges(12)
            
            for start_date, end_date in date_ranges:
                try:
                    logger.info(f"Fetching data for period: {start_date} to {end_date}")
                    
                    keyword_data = self._get_search_console_data(
                        search_console_service, 
                        property_url, 
                        start_date.strftime('%Y-%m-%d'),
                        end_date.strftime('%Y-%m-%d'),
                        'query'
                    )
                    
                    if keyword_data:  # Only process if we got data
                        # Calculate monthly averages and store
                        stored_count = self._log_monthly_rankings(client, keyword_data, start_date)
                        total_stored_rankings += stored_count
                    else:
                        logger.warning(f"No keyword data returned for period {start_date} to {end_date}")
                    
                except Exception as e:
                    logger.error(f"Error fetching data for period {start_date} to {end_date}: {str(e)}")
                    if 'invalid_grant' in str(e) or 'expired' in str(e):
                        raise  # Re-raise auth errors to be handled above
                    continue
            
            if total_stored_rankings > 0:
                return {
                    'success': True,
                    'message': f"Processed ranking data for {len(date_ranges)} period(s)",
                    'stored_rankings_count': total_stored_rankings
                }
            else:
                return {
                    'success': False,
                    'error': "No ranking data was collected",
                    'stored_rankings_count': 0
                }
            
        except Exception as e:
            logger.error(f"Error in ranking tool: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'stored_rankings_count': total_stored_rankings
            }

    @transaction.atomic
    def _log_monthly_rankings(self, client, keyword_data, month_date):
        """Log monthly average rankings"""
        try:
            # Get all targeted keywords for this client
            targeted_keywords = {
                kw.keyword.lower(): kw 
                for kw in TargetedKeyword.objects.filter(client=client)
            }
            
            # Delete existing rankings for this month
            KeywordRankingHistory.objects.filter(
                client=client,
                date__year=month_date.year,
                date__month=month_date.month
            ).delete()
            
            # Process and store rankings
            rankings_to_create = []
            
            for data in keyword_data:
                keyword_text = data['Keyword']
                
                ranking = KeywordRankingHistory(
                    client=client,
                    keyword_text=keyword_text,
                    date=month_date,  # Use first day of month as reference date
                    impressions=data['Impressions'],
                    clicks=data['Clicks'],
                    ctr=data['CTR (%)'] / 100,
                    average_position=data['Avg Position']
                )
                
                # Link to TargetedKeyword if exists
                targeted_keyword = targeted_keywords.get(keyword_text.lower())
                if targeted_keyword:
                    ranking.keyword = targeted_keyword
                
                rankings_to_create.append(ranking)
            
            # Bulk create new rankings
            KeywordRankingHistory.objects.bulk_create(
                rankings_to_create,
                batch_size=1000
            )
            
            logger.info(
                f"Stored {len(rankings_to_create)} rankings for {month_date.strftime('%B %Y')}"
            )
            
            return len(rankings_to_create)  # Return count of stored rankings
            
        except Exception as e:
            logger.error(f"Error logging monthly rankings: {str(e)}")
            raise

    def _get_search_console_data(self, service, property_url, start_date, end_date, dimension):
        try:
            # Parse the property URL if needed
            if isinstance(property_url, str) and '{' in property_url:
                try:
                    data = json.loads(property_url.replace("'", '"'))  # Replace single quotes with double quotes
                    site_url = data['url']
                except (json.JSONDecodeError, KeyError):
                    site_url = property_url
            elif isinstance(property_url, dict):
                site_url = property_url['url']
            else:
                site_url = property_url

            logger.info(f"Using Search Console property URL: {site_url}")

            response = service.searchanalytics().query(
                siteUrl=site_url,
                body={
                    'startDate': start_date,
                    'endDate': end_date,
                    'dimensions': [dimension],
                    'rowLimit': 1000
                }
            ).execute()
            
            search_console_data = []
            for row in response.get('rows', []):
                search_console_data.append({
                    'Keyword' if dimension == 'query' else 'Landing Page': row['keys'][0],
                    'Clicks': row['clicks'],
                    'Impressions': row['impressions'],
                    'CTR (%)': round(row['ctr'] * 100, 2),
                    'Avg Position': round(row['position'], 1)
                })
            
            search_console_data.sort(key=lambda x: x['Impressions'], reverse=True)
            return search_console_data[:1000]
        except HttpError as error:
            logger.error(f"An error occurred while fetching Search Console data: {error}")
            print(f"An error occurred while fetching Search Console data: {error}")
            return []
