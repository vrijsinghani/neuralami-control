from django.core.management.base import BaseCommand
from apps.seo_manager.models import Client, KeywordRankingHistory
from datetime import date
from dateutil.relativedelta import relativedelta

class Command(BaseCommand):
    help = 'Generate monthly SEO performance report'

    def handle(self, *args, **options):
        today = date.today()
        last_month = today - relativedelta(months=1)
        
        for client in Client.objects.all():
            # Get last month's rankings
            rankings = KeywordRankingHistory.objects.filter(
                client=client,
                date__year=last_month.year,
                date__month=last_month.month
            )

            # Analyze performance
            report = {
                'client': client.name,
                'period': last_month.strftime('%B %Y'),
                'targeted_keywords': {
                    'total': client.targeted_keywords.count(),
                    'improved': 0,
                    'declined': 0,
                    'unchanged': 0
                },
                'top_improvements': [],
                'needs_attention': []
            }

            # Calculate changes
            for keyword in client.targeted_keywords.all():
                change = keyword.get_position_change()
                if change:
                    if change > 0:
                        report['targeted_keywords']['improved'] += 1
                        if change > 5:  # Significant improvement
                            report['top_improvements'].append({
                                'keyword': keyword.keyword,
                                'improvement': change
                            })
                    elif change < 0:
                        report['targeted_keywords']['declined'] += 1
                        if change < -5:  # Significant decline
                            report['needs_attention'].append({
                                'keyword': keyword.keyword,
                                'decline': change
                            })
                    else:
                        report['targeted_keywords']['unchanged'] += 1

            self.stdout.write(
                self.style.SUCCESS(f"Report generated for {client.name}")
            )
            # You could email this report, save it to a file, etc.
