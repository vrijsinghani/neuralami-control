import csv
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from datetime import datetime, timedelta
from django.core.paginator import Paginator
from django.shortcuts import render
from django.db.models import Min, Max
from django.db import transaction
from ..models import Client, KeywordRankingHistory, TargetedKeyword
from ..forms import RankingImportForm
from apps.agents.tools.google_report_tool.google_ranking_data_tool import GoogleRankingDataTool
import logging
import json

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
        # Get the client
        client = get_object_or_404(Client, id=client_id)

        # Ensure client has Search Console credentials
        if not hasattr(client, 'sc_credentials'):
            return JsonResponse({
                'success': False,
                'error': "This client does not have Search Console credentials configured."
            })

        sc_creds = client.sc_credentials

        # Extract credentials for multi-tenant tool
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
            return JsonResponse({
                'success': False,
                'error': "No valid Search Console property URL configured for this client."
            })

        tool = GoogleRankingDataTool()
        # Get just the last 30 days of data
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=30)

        # Call the tool with explicit parameters instead of client_id
        result_json = tool._run(
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d'),
            search_console_property_url=property_url,
            search_console_credentials=credentials,
            historical=False
        )

        # Parse the JSON result
        result = json.loads(result_json)

        if result.get('success'):
            # Log what we received
            keyword_data = result.get('keyword_data', [])
            logger.info(f"Received {len(keyword_data)} periods of keyword data")
            for i, period in enumerate(keyword_data):
                logger.info(f"Period {i+1}: {period.get('date')} with {len(period.get('data', []))} keywords")

            # Process and store the data in the database
            total_stored = store_keyword_rankings(client, keyword_data)

            # Only show success if we actually stored some data
            if total_stored > 0:
                messages.success(request, "Latest rankings collected successfully")
                return JsonResponse({
                    'success': True,
                    'message': "Latest rankings data has been collected and stored",
                    'stored_count': total_stored
                })
            else:
                logger.warning(f"No rankings stored. Result: {result}")
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
        # Get the client
        client = get_object_or_404(Client, id=client_id)

        # Ensure client has Search Console credentials
        if not hasattr(client, 'sc_credentials'):
            return JsonResponse({
                'success': False,
                'error': "This client does not have Search Console credentials configured."
            })

        sc_creds = client.sc_credentials

        # Extract credentials for multi-tenant tool
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
            return JsonResponse({
                'success': False,
                'error': "No valid Search Console property URL configured for this client."
            })

        tool = GoogleRankingDataTool()

        # Call the tool with explicit parameters instead of client_id
        result_json = tool._run(
            start_date=None,
            end_date=None,
            search_console_property_url=property_url,
            search_console_credentials=credentials,
            historical=True
        )

        # Parse the JSON result
        result = json.loads(result_json)

        if result.get('success'):
            # Log what we received
            keyword_data = result.get('keyword_data', [])
            logger.info(f"Received {len(keyword_data)} periods of keyword data for historical backfill")
            for i, period in enumerate(keyword_data):
                logger.info(f"Period {i+1}: {period.get('date')} with {len(period.get('data', []))} keywords")

            # Process and store the data in the database
            total_stored = store_keyword_rankings(client, keyword_data)

            if total_stored > 0:
                messages.success(request, "Historical rankings collected successfully")
                return JsonResponse({
                    'success': True,
                    'message': "12 months of historical ranking data has been collected and stored",
                    'stored_count': total_stored
                })
            else:
                logger.warning(f"No historical rankings stored. Result: {result}")
                return JsonResponse({
                    'success': False,
                    'error': "No ranking data was collected. Please check your Search Console credentials."
                })
        else:
            return JsonResponse({
                'success': False,
                'error': result.get('error', 'Unknown error occurred')
            })
    except Exception as e:
        logger.error(f"Error in backfill_rankings view: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@transaction.atomic
def store_keyword_rankings(client, keyword_data_periods):
    """
    Store keyword rankings in the database.
    This handles the database operations that were previously in the tool.
    """
    total_stored = 0

    try:
        # Log what we received
        logger.info(f"store_keyword_rankings: Received {len(keyword_data_periods)} periods for client {client.name}")

        # Get all targeted keywords for this client
        targeted_keywords = {
            kw.keyword.lower(): kw
            for kw in TargetedKeyword.objects.filter(client=client)
        }

        logger.info(f"store_keyword_rankings: Found {len(targeted_keywords)} targeted keywords for client")

        for period_data in keyword_data_periods:
            # Parse the date from the returned data
            month_date = datetime.strptime(period_data['date'], '%Y-%m-%d').date()
            keyword_data = period_data['data']

            logger.info(f"store_keyword_rankings: Processing period {month_date} with {len(keyword_data)} keywords")

            # Delete existing rankings for this month
            deleted_count = KeywordRankingHistory.objects.filter(
                client=client,
                date__year=month_date.year,
                date__month=month_date.month
            ).delete()

            logger.info(f"store_keyword_rankings: Deleted {deleted_count} existing rankings for {month_date.strftime('%B %Y')}")

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
                logger.info(f"store_keyword_rankings: Creating {len(rankings_to_create)} new rankings")
                try:
                    KeywordRankingHistory.objects.bulk_create(
                        rankings_to_create,
                        batch_size=1000
                    )

                    count = len(rankings_to_create)
                    total_stored += count
                    logger.info(
                        f"Stored {count} rankings for {month_date.strftime('%B %Y')}"
                    )
                except Exception as e:
                    logger.error(f"Error bulk creating rankings: {str(e)}")
                    raise
            else:
                logger.warning(f"No rankings to create for {month_date.strftime('%B %Y')}")

        return total_stored

    except Exception as e:
        logger.error(f"Error storing keyword rankings: {str(e)}")
        raise

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
        'page_title': 'Rankings',
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

@login_required
def ranking_data_insights(request, client_id):
    """New view for the enhanced ranking data management with insights"""
    client = get_object_or_404(Client, id=client_id)

    # Get date range from request or default to 90 days
    date_range = int(request.GET.get('date_range', 90))

    # Get ranking data statistics
    ranking_stats = KeywordRankingHistory.objects.filter(
        client_id=client_id
    ).aggregate(
        earliest_date=Min('date'),
        latest_date=Max('date')
    )

    latest_collection_date = ranking_stats['latest_date']

    # Calculate data for insights
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=date_range)

    # Get rankings within the date range
    rankings = KeywordRankingHistory.objects.filter(
        client_id=client_id,
        date__gte=start_date,
        date__lte=end_date
    )

    # Mock data for the initial implementation
    # In a real implementation, these would be calculated from the database
    context = {
        'page_title': 'Ranking Insights',
        'client': client,
        'date_range': date_range,
        'latest_collection_date': latest_collection_date,
        'opportunities_count': 24,
        'improving_count': 142,
        'declining_count': 38,
        'high_potential_count': 56,
        'avg_position': 14.3,
        'position_improvement': 1.2,
        'performance_improvement': 30
    }

    return render(request, 'seo_manager/ranking_data_management_insights.html', context)

# Placeholder functions for HTMX interactions
@login_required
def update_dashboard_settings(request, client_id):
    """Placeholder for updating dashboard settings"""
    # In a real implementation, this would save the settings to the database
    return JsonResponse({'success': True, 'message': 'Settings updated successfully'})

@login_required
def reset_dashboard_settings(request, client_id):
    """Placeholder for resetting dashboard settings to defaults"""
    # In a real implementation, this would reset settings to defaults
    return render(request, 'seo_manager/partials/ranking_insights/_quick_insights.html', {
        'client': get_object_or_404(Client, id=client_id),
        'opportunities_count': 24,
        'improving_count': 142,
        'declining_count': 38,
        'high_potential_count': 56
    })

@login_required
def save_dashboard_view(request, client_id):
    """Placeholder for saving the current dashboard view"""
    # In a real implementation, this would save the current view configuration
    return JsonResponse({'success': True, 'message': 'Dashboard view saved successfully'})

@login_required
def export_rankings(request, client_id):
    """Placeholder for exporting rankings data"""
    # In a real implementation, this would generate and return a file
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="rankings_export_{client_id}.csv"'
    return response

@login_required
def keyword_impact_map(request, client_id):
    """Placeholder for keyword impact map data"""
    # In a real implementation, this would return the impact map data
    return render(request, 'seo_manager/partials/ranking_insights/_keyword_impact_map_content.html', {
        'client': get_object_or_404(Client, id=client_id)
    })

@login_required
def analyze_keywords(request, client_id):
    """Placeholder for keyword analysis"""
    # In a real implementation, this would analyze keywords and return results
    return render(request, 'seo_manager/partials/ranking_insights/_keyword_analysis.html', {
        'client': get_object_or_404(Client, id=client_id)
    })

@login_required
def filter_top_keywords(request, client_id):
    """Placeholder for filtering top keywords"""
    # In a real implementation, this would filter keywords based on criteria
    return render(request, 'seo_manager/partials/ranking_insights/_top_keywords_list.html', {
        'client': get_object_or_404(Client, id=client_id)
    })

@login_required
def view_opportunity_keywords(request, client_id):
    """Placeholder for viewing opportunity keywords"""
    # In a real implementation, this would show keywords near ranking breakthroughs
    return render(request, 'seo_manager/partials/ranking_insights/_opportunity_keywords.html', {
        'client': get_object_or_404(Client, id=client_id)
    })

@login_required
def view_high_potential_keywords(request, client_id):
    """Placeholder for viewing high potential keywords"""
    # In a real implementation, this would show high-impression, low-CTR keywords
    return render(request, 'seo_manager/partials/ranking_insights/_high_potential_keywords.html', {
        'client': get_object_or_404(Client, id=client_id)
    })

@login_required
def view_declining_keywords(request, client_id):
    """Placeholder for viewing declining keywords"""
    # In a real implementation, this would show keywords losing positions
    return render(request, 'seo_manager/partials/ranking_insights/_declining_keywords.html', {
        'client': get_object_or_404(Client, id=client_id)
    })

@login_required
def create_optimization_task(request, client_id):
    """Placeholder for creating optimization task"""
    # In a real implementation, this would create a task for keyword optimization
    return render(request, 'seo_manager/partials/ranking_insights/_optimization_task_form.html', {
        'client': get_object_or_404(Client, id=client_id)
    })

@login_required
def update_meta_tags(request, client_id):
    """Placeholder for updating meta tags"""
    # In a real implementation, this would show a form to update meta tags
    return render(request, 'seo_manager/partials/ranking_insights/_meta_tags_form.html', {
        'client': get_object_or_404(Client, id=client_id)
    })

@login_required
def audit_content(request, client_id):
    """Placeholder for content audit"""
    # In a real implementation, this would show content audit results
    return render(request, 'seo_manager/partials/ranking_insights/_content_audit.html', {
        'client': get_object_or_404(Client, id=client_id)
    })

@login_required
def benchmark_keywords(request, client_id):
    """Placeholder for keyword benchmarking"""
    # In a real implementation, this would show keyword benchmarking data
    return render(request, 'seo_manager/partials/ranking_insights/_keyword_benchmark.html', {
        'client': get_object_or_404(Client, id=client_id)
    })

@login_required
def competitor_analysis(request, client_id):
    """Placeholder for competitor analysis"""
    # In a real implementation, this would show competitor analysis data
    return render(request, 'seo_manager/partials/ranking_insights/_competitor_analysis.html', {
        'client': get_object_or_404(Client, id=client_id)
    })

@login_required
def historical_data(request, client_id):
    """Placeholder for historical data"""
    # In a real implementation, this would show historical ranking data
    return render(request, 'seo_manager/partials/ranking_insights/_historical_data.html', {
        'client': get_object_or_404(Client, id=client_id)
    })

@login_required
def create_task_board(request, client_id):
    """Placeholder for creating a task board"""
    # In a real implementation, this would create a task board
    return redirect('seo_manager:ranking_data_insights', client_id=client_id)

@login_required
def new_keyword_group_form(request, client_id):
    """Placeholder for new keyword group form"""
    # In a real implementation, this would show a form to create a new keyword group
    return render(request, 'seo_manager/partials/ranking_insights/_new_group_form.html', {
        'client': get_object_or_404(Client, id=client_id)
    })

@login_required
def edit_keyword_group(request, client_id):
    """Placeholder for editing a keyword group"""
    # In a real implementation, this would show a form to edit a keyword group
    return render(request, 'seo_manager/partials/ranking_insights/_edit_group_form.html', {
        'client': get_object_or_404(Client, id=client_id),
        'group_id': request.GET.get('group_id')
    })

@login_required
def view_group_keywords(request, client_id):
    """Placeholder for viewing keywords in a group"""
    # In a real implementation, this would show keywords in a group
    return render(request, 'seo_manager/partials/ranking_insights/_group_keywords.html', {
        'client': get_object_or_404(Client, id=client_id),
        'group_id': request.GET.get('group_id')
    })

@login_required
def delete_keyword_group(request, client_id):
    """Placeholder for deleting a keyword group"""
    # In a real implementation, this would delete a keyword group
    return render(request, 'seo_manager/partials/ranking_insights/_keyword_groups_container.html', {
        'client': get_object_or_404(Client, id=client_id)
    })

@login_required
def group_performance(request, client_id):
    """Placeholder for group performance data"""
    # In a real implementation, this would show performance data for a keyword group
    return render(request, 'seo_manager/partials/ranking_insights/_group_performance.html', {
        'client': get_object_or_404(Client, id=client_id),
        'group_id': request.GET.get('group_id')
    })

@login_required
def export_keyword_analysis(request, client_id):
    """Placeholder for exporting keyword analysis"""
    # In a real implementation, this would generate and return a file
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="keyword_analysis_{client_id}.csv"'
    return response

@login_required
def all_keywords(request, client_id):
    """Placeholder for viewing all keywords"""
    # In a real implementation, this would show all keywords for a client
    return render(request, 'seo_manager/partials/ranking_insights/_all_keywords.html', {
        'client': get_object_or_404(Client, id=client_id)
    })
