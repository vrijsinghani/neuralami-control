from django.core.management.base import BaseCommand
from apps.seo_manager.models import Client
from apps.agents.tools.google_report_tool.google_rankings_tool import GoogleRankingsTool

class Command(BaseCommand):
    help = 'Backfill historical ranking data for all clients'

    def handle(self, *args, **options):
        tool = GoogleRankingsTool()
        clients = Client.objects.filter(sc_credentials__isnull=False)
        
        for client in clients:
            self.stdout.write(f"Processing client: {client.name}")
            tool._run(None, None, client.id)
