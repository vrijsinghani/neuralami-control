import csv
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from datetime import timedelta
from django.core.paginator import Paginator
from django.shortcuts import render
from django.db.models import Min, Max
from ..models import Client, KeywordRankingHistory
from ..forms import RankingImportForm
from apps.agents.tools.google_report_tool.google_rankings_tool import GoogleRankingsTool
import logging

logger = logging.getLogger(__name__)

@login_required
def ranking_import(request, client_id):
    if request.method == 'POST':
        form = RankingImportForm(request.POST, request.FILES)
        if form.is_valid():
            form.process_import(request.user)
            messages.success(request, "Rankings imported successfully.")
            return redirect('seo_manager:client_detail', client_id=client_id)
    else:
        form = RankingImportForm()
    
    return render(request, 'seo_manager/keywords/ranking_import.html', {
        'form': form,
        'client': get_object_or_404(Client, id=client_id)
    })

@login_required
@require_http_methods(["POST"])
def collect_rankings(request, client_id):
    try:
        tool = GoogleRankingsTool()
        # Get just the last 30 days of data
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=7)
        
        result = tool._run(
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d'),
            client_id=client_id
        )
        
        if result.get('success'):
            # Only show success if we actually stored some data
            if result.get('stored_rankings_count', 0) > 0:
                messages.success(request, "Latest rankings collected successfully")
                return JsonResponse({
                    'success': True,
                    'message': "Latest rankings data has been collected and stored"
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': "No ranking data was collected. Please check your Search Console credentials."
                })
        else:
            error_msg = result.get('error', 'Failed to collect rankings')
            if 'invalid_grant' in error_msg or 'expired' in error_msg:
                error_msg = "Your Search Console access has expired. Please reconnect your Search Console account."
            
            return JsonResponse({
                'success': False,
                'error': error_msg
            })
    except Exception as e:
        logger.error(f"Error in collect_rankings view: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
@require_http_methods(["POST"])
def backfill_rankings(request, client_id):
    try:
        tool = GoogleRankingsTool()
        # Pass None for start_date and end_date to trigger 12-month backfill
        result = tool._run(
            start_date=None,
            end_date=None,
            client_id=client_id
        )
        
        if result['success']:
            messages.success(request, "Historical rankings collected successfully")
            return JsonResponse({
                'success': True,
                'message': "12 months of historical ranking data has been collected and stored"
            })
        else:
            return JsonResponse({
                'success': False,
                'error': result.get('error', 'Unknown error occurred')
            })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
def ranking_data_management(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    
    # Get ranking data statistics
    ranking_stats = KeywordRankingHistory.objects.filter(
        client_id=client_id
    ).aggregate(
        earliest_date=Min('date'),
        latest_date=Max('date')
    )
    
    latest_collection_date = ranking_stats['latest_date']

    # Calculate data coverage in months
    data_coverage_months = 0
    if ranking_stats['earliest_date'] and ranking_stats['latest_date']:
        date_diff = ranking_stats['latest_date'] - ranking_stats['earliest_date']
        data_coverage_months = round(date_diff.days / 30)
    
    # Get search query
    search_query = request.GET.get('search', '')
    
    # Get sort parameters
    sort_by = request.GET.get('sort', '-date')  # Default sort by date descending
    if sort_by.startswith('-'):
        order_by = sort_by
        sort_dir = 'desc'
    else:
        order_by = sort_by
        sort_dir = 'asc'
    
    # Get items per page
    items_per_page = int(request.GET.get('items', 25))
    
    # Get rankings with filtering, sorting and pagination
    rankings_list = KeywordRankingHistory.objects.filter(client_id=client_id)
    
    # Apply search filter if provided
    if search_query:
        rankings_list = rankings_list.filter(keyword_text__icontains=search_query)
    
    # Apply sorting
    rankings_list = rankings_list.order_by(order_by)
    
    paginator = Paginator(rankings_list, items_per_page)
    page = request.GET.get('page')
    rankings = paginator.get_page(page)
    
    # Count unique keywords
    tracked_keywords_count = KeywordRankingHistory.objects.filter(
        client_id=client_id
    ).values('keyword_text').distinct().count()
    
    context = {
        'client': client,
        'latest_collection_date': latest_collection_date,
        'data_coverage_months': data_coverage_months,
        'tracked_keywords_count': tracked_keywords_count,
        'rankings': rankings,
        'sort_by': sort_by,
        'sort_dir': sort_dir,
        'search_query': search_query,
        'items': items_per_page,
    }
    
    return render(request, 'seo_manager/ranking_data_management.html', context)

@login_required
def export_rankings_csv(request, client_id):
    # Get search query
    search_query = request.GET.get('search', '')
    
    # Get rankings
    rankings = KeywordRankingHistory.objects.filter(client_id=client_id)
    if search_query:
        rankings = rankings.filter(keyword_text__icontains=search_query)
    
    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="rankings_{client_id}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Keyword', 'Position', 'Change', 'Impressions', 'Clicks', 'CTR', 'Date'])
    
    for ranking in rankings:
        writer.writerow([
            ranking.keyword_text,
            ranking.average_position,
            ranking.position_change,
            ranking.impressions,
            ranking.clicks,
            f"{ranking.ctr:.2f}%",
            ranking.date.strftime("%Y-%m-%d")
        ])
    
    return response
