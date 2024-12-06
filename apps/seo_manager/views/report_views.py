import logging
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.template.loader import render_to_string
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from ..models import Client

logger = logging.getLogger(__name__)

@login_required
@require_http_methods(["POST"])
def generate_report(request, client_id):
    try:
        client = get_object_or_404(Client.objects.select_related(), id=client_id)
        
        # Get the report data
        today = timezone.now().date()
        last_month = today - relativedelta(months=1)
        
        # Use select_related to optimize queries
        keywords = client.targeted_keywords.select_related().all()
        
        report = {
            'period': last_month.strftime('%B %Y'),
            'keywords': {
                'total': keywords.count(),
                'improved': 0,
                'declined': 0,
                'unchanged': 0
            },
            'top_improvements': [],
            'needs_attention': []
        }

        # Process keyword data
        for keyword in keywords:
            change = keyword.get_position_change()
            if change:
                if change > 0:
                    report['keywords']['improved'] += 1
                    if change > 5:
                        report['top_improvements'].append({
                            'keyword': keyword.keyword,
                            'improvement': change
                        })
                elif change < 0:
                    report['keywords']['declined'] += 1
                    if change < -5:
                        report['needs_attention'].append({
                            'keyword': keyword.keyword,
                            'decline': abs(change)
                        })
                else:
                    report['keywords']['unchanged'] += 1

        # Sort improvements and needs attention lists
        report['top_improvements'].sort(key=lambda x: x['improvement'], reverse=True)
        report['needs_attention'].sort(key=lambda x: x['decline'], reverse=True)

        # Limit to top 5 for each list
        report['top_improvements'] = report['top_improvements'][:5]
        report['needs_attention'] = report['needs_attention'][:5]

        # Render the report template
        report_html = render_to_string(
            'seo_manager/reports/monthly_report.html',
            {'report': report, 'client': client},
            request=request
        )

        return JsonResponse({
            'success': True,
            'report_html': report_html
        })
        
    except Exception as e:
        logger.error(f"Error generating report: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f"Error generating report: {str(e)}"
        })
