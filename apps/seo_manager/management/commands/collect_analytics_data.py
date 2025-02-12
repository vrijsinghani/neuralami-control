import csv
from datetime import datetime
import logging
from django.core.management.base import BaseCommand
from apps.seo_manager.models import Client, ClientGroup
from apps.agents.tools.google_analytics_tool.generic_google_analytics_tool import GenericGoogleAnalyticsTool

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Collect Google Analytics data for clients in Floors & More group'

    def handle(self, *args, **options):
        try:
            # Get the Floors & More group
            group = ClientGroup.objects.filter(name='Floors & More').first()
            if not group:
                self.stdout.write(self.style.ERROR('Group "Floors & More" not found'))
                return

            # Get all clients in the group
            clients = Client.objects.filter(group=group, status='active')
            if not clients.exists():
                self.stdout.write(self.style.ERROR('No active clients found in Floors & More group'))
                return

            # Initialize the analytics tool
            analytics_tool = GenericGoogleAnalyticsTool()

            # Prepare CSV file
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'floors_and_more_analytics_{timestamp}.csv'
            
            with open(filename, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                # Write header
                writer.writerow(['Client Name', 'Date', 'Thank You Page Views'])

                # Process each client
                for client in clients:
                    self.stdout.write(f'Processing client: {client.name}')
                    
                    try:
                        # Call the analytics tool
                        result = analytics_tool._run(
                            client_id=client.id,
                            start_date='5monthsAgo',
                            end_date='today',
                            metrics='screenPageViews',
                            dimensions='date',
                            time_granularity='monthly',
                            dimension_filter='pagePath==/thank-you/'
                        )

                        if result.get('success'):
                            analytics_data = result.get('analytics_data', [])
                            for data_point in analytics_data:
                                writer.writerow([
                                    client.name,
                                    data_point.get('date'),
                                    data_point.get('screenPageViews', 0)
                                ])
                        else:
                            error_msg = result.get('error', 'Unknown error')
                            logger.error(f'Error collecting data for {client.name}: {error_msg}')
                            self.stdout.write(self.style.WARNING(f'Failed to collect data for {client.name}: {error_msg}'))

                    except Exception as e:
                        logger.error(f'Error processing client {client.name}: {str(e)}', exc_info=True)
                        self.stdout.write(self.style.WARNING(f'Error processing client {client.name}: {str(e)}'))
                        continue

            self.stdout.write(self.style.SUCCESS(f'Data collection completed. Results saved to {filename}'))

        except Exception as e:
            logger.error('Error in collect_analytics_data command', exc_info=True)
            self.stdout.write(self.style.ERROR(f'Command failed: {str(e)}')) 