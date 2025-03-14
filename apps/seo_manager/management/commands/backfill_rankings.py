from django.core.management.base import BaseCommand
from apps.seo_manager.models import Client, KeywordRankingHistory, TargetedKeyword
from apps.agents.tools.google_report_tool.google_rankings_tool import GoogleRankingsTool
import json
import logging
from datetime import datetime
from django.db import transaction

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Backfill historical ranking data for all clients'

    def handle(self, *args, **options):
        tool = GoogleRankingsTool()
        clients = Client.objects.filter(sc_credentials__isnull=False)
        
        for client in clients:
            self.stdout.write(f"Processing client: {client.name}")
            
            try:
                # Get Search Console credentials from the client
                if not hasattr(client, 'sc_credentials'):
                    self.stdout.write(self.style.WARNING(f"Client {client.name} has no Search Console credentials"))
                    continue
                
                sc_creds = client.sc_credentials
                
                # Extract credentials as dictionary for multi-tenant tool
                credentials = {
                    'sc_client_id': sc_creds.sc_client_id,
                    'client_secret': sc_creds.client_secret,
                    'refresh_token': sc_creds.refresh_token,
                    'token_uri': sc_creds.token_uri,
                    'access_token': sc_creds.access_token
                }
                
                # Get property URL
                property_url = sc_creds.get_property_url()
                if not property_url:
                    self.stdout.write(self.style.WARNING(f"No valid property URL for client {client.name}"))
                    continue
                
                # Call the tool with the extracted credentials (no client_id anymore)
                result = tool._run(
                    start_date=None,
                    end_date=None,
                    search_console_property_url=property_url,
                    search_console_credentials=credentials
                )
                
                # Parse the JSON result
                result_data = json.loads(result)
                
                if result_data.get('success', False):
                    # Process and store the data that was returned
                    total_stored = self._store_keyword_rankings(client, result_data.get('keyword_data', []))
                    
                    self.stdout.write(self.style.SUCCESS(
                        f"Processed and stored {total_stored} rankings for {client.name}"
                    ))
                else:
                    self.stdout.write(self.style.ERROR(
                        f"Failed to process rankings for {client.name}: {result_data.get('error', 'Unknown error')}"
                    ))
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error processing client {client.name}: {str(e)}"))
                logger.error(f"Error in backfill_rankings for client {client.name}: {str(e)}", exc_info=True)

    @transaction.atomic
    def _store_keyword_rankings(self, client, keyword_data_periods):
        """
        Store keyword rankings in the database.
        This logic was moved from the tool to maintain multi-tenancy.
        """
        total_stored = 0
        
        try:
            # Get all targeted keywords for this client
            targeted_keywords = {
                kw.keyword.lower(): kw 
                for kw in TargetedKeyword.objects.filter(client=client)
            }
            
            for period_data in keyword_data_periods:
                # Parse the date from the returned data
                month_date = datetime.strptime(period_data['date'], '%Y-%m-%d').date()
                keyword_data = period_data['data']
                
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
                if rankings_to_create:
                    KeywordRankingHistory.objects.bulk_create(
                        rankings_to_create,
                        batch_size=1000
                    )
                    
                    count = len(rankings_to_create)
                    total_stored += count
                    logger.info(
                        f"Stored {count} rankings for {month_date.strftime('%B %Y')}"
                    )
            
            return total_stored
                
        except Exception as e:
            logger.error(f"Error storing keyword rankings: {str(e)}")
            raise
