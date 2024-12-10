import json
import logging
import os
import csv
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.conf import settings
from django.db.models import Min, Max, Q
from ..models import Client, KeywordRankingHistory, UserActivity, SearchConsoleCredentials
from ..forms import ClientForm, BusinessObjectiveForm, TargetedKeywordForm, KeywordBulkUploadForm, SEOProjectForm, ClientProfileForm
from apps.common.tools.user_activity_tool import user_activity_tool
from apps.agents.tools.client_profile_tool.client_profile_tool import ClientProfileTool
from apps.agents.models import Tool
from datetime import datetime, timedelta
from markdown_it import MarkdownIt  # Import markdown-it
from django.urls import reverse
from .search_console_views import get_search_console_data

logger = logging.getLogger(__name__)
__all__ = [
    'dashboard',
    'client_list',
    'add_client',
    'client_detail',
    'edit_client',
    'delete_client',
    'update_client_profile',
    'generate_magic_profile',
    'load_more_activities',
    'export_activities',
    'client_integrations',
]

@login_required
def dashboard(request):
    clients = Client.objects.all().order_by('name')
    form = ClientForm()
    return render(request, 'seo_manager/dashboard.html', {'page_title': 'Dashboard', 'clients': clients, 'form': form})

@login_required
def client_list(request):
    clients = Client.objects.all().order_by('name').select_related('group')
    form = ClientForm()
    return render(request, 'seo_manager/client_list.html', {'page_title': 'Clients', 'clients': clients, 'form': form})

@login_required
def add_client(request):
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save()
            user_activity_tool.run(request.user, 'create', f"Added new client: {client.name}", client=client)
            messages.success(request, f"Client '{client.name}' has been added successfully.")
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': f"Client '{client.name}' has been added successfully.",
                    'redirect_url': reverse('seo_manager:client_detail', args=[client.id])
                })
            
            return redirect('seo_manager:client_detail', client_id=client.id)
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': form.errors
                })
    else:
        form = ClientForm()
    
    return render(request, 'seo_manager/add_client.html', {'form': form})

@login_required
def client_detail(request, client_id):
    logger.debug(f"Accessing client_detail view for client_id: {client_id}")

    # Prefetch all related data in a single query
    client = get_object_or_404(
        Client.objects.prefetch_related(
            'targeted_keywords',
            'targeted_keywords__ranking_history',
            'seo_projects',
            'seo_projects__targeted_keywords',
            'seo_projects__targeted_keywords__ranking_history'
        ), 
        id=client_id
    )
    
    # Get keyword history in a single query
    keyword_history = KeywordRankingHistory.objects.filter(
        client_id=client_id
    ).select_related('keyword').order_by('-date')
    
    # Create a dictionary to store history by keyword
    history_by_keyword = {}
    for history in keyword_history:
        if history.keyword_id not in history_by_keyword:
            history_by_keyword[history.keyword_id] = []
        history_by_keyword[history.keyword_id].append(history)
    
    # Attach history to keywords
    for keyword in client.targeted_keywords.all():
        keyword.ranking_data = history_by_keyword.get(keyword.id, [])
    
    # Get client activities
    important_categories = ['create', 'update', 'delete', 'export', 'import', 'other']
    client_activities = UserActivity.objects.filter(
        client=client,
        category__in=important_categories
    ).select_related('user').order_by('-timestamp')[:10]

    # Initialize forms
    keyword_form = TargetedKeywordForm()
    import_form = KeywordBulkUploadForm()
    project_form = SEOProjectForm(client=client)
    business_objective_form = BusinessObjectiveForm()
    
    # Get meta tags files
    meta_tags_dir = os.path.join(settings.MEDIA_ROOT, 'meta-tags', str(client.id))
    meta_tags_files = []
    if os.path.exists(meta_tags_dir):
        meta_tags_files = sorted(
            [f for f in os.listdir(meta_tags_dir) if f.endswith('.json')],
            key=lambda x: os.path.getmtime(os.path.join(meta_tags_dir, x)),
            reverse=True
        )

    # Get ranking stats in a single query
    ranking_stats = keyword_history.aggregate(
        earliest_date=Min('date'),
        latest_date=Max('date')
    )
    
    latest_collection_date = ranking_stats['latest_date']
    logger.debug(f"Latest collection date: {latest_collection_date}")
    
    data_coverage_months = 0
    if ranking_stats['earliest_date'] and ranking_stats['latest_date']:
        date_diff = ranking_stats['latest_date'] - ranking_stats['earliest_date']
        data_coverage_months = round(date_diff.days / 30)
    
    tracked_keywords_count = keyword_history.values('keyword_text').distinct().count()

    # Get Search Console data
    search_console_data = []
    try:
        sc_credentials = getattr(client, 'sc_credentials', None)
        if sc_credentials:
            service = sc_credentials.get_service()
            if service:
                property_url = sc_credentials.get_property_url()
                if property_url:
                    end_date = datetime.now().strftime('%Y-%m-%d')
                    start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
                    search_console_data = get_search_console_data(
                        service, 
                        property_url,
                        start_date,
                        end_date
                    )
    except Exception as e:
        logger.error(f"Error fetching search console data: {str(e)}")

    context = {
        'page_title': 'Client Detail',
        'client': client,
        'client_activities': client_activities,
        'business_objectives': client.business_objectives,
        'business_objective_form': business_objective_form,
        'keyword_form': keyword_form,
        'import_form': import_form,
        'project_form': project_form,
        'meta_tags_files': meta_tags_files,
        'client_profile_html': client.client_profile,
        'profile_form': ClientProfileForm(initial={'client_profile': client.client_profile}),
        'latest_collection_date': latest_collection_date,
        'data_coverage_months': data_coverage_months,
        'tracked_keywords_count': tracked_keywords_count,
        'search_console_data': search_console_data,
    }
    
    return render(request, 'seo_manager/client_detail.html', context)

@login_required
def edit_client(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            user_activity_tool.run(request.user, 'update', f"Updated client details: {client.name}", client=client)
            
            # Check if request is AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': f"Client '{client.name}' has been updated successfully.",
                })
            
            messages.success(request, f"Client '{client.name}' has been updated successfully.")
            return redirect('seo_manager:client_detail', client_id=client.id)
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': {field: [str(error) for error in errors] 
                              for field, errors in form.errors.items()}
                })
            
    else:
        form = ClientForm(instance=client)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': False,
            'errors': {'form': ['Invalid form submission']}
        })
        
    return render(request, 'seo_manager/edit_client.html', {'form': form, 'client': client})

@login_required
def delete_client(request, client_id):
    if request.method == 'POST':
        client = get_object_or_404(Client, id=client_id)
        user_activity_tool.run(request.user, 'delete', f"Deleted client: {client.name}", client=client)
        client.delete()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False}, status=400)

@login_required
def update_client_profile(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    
    if request.method == 'POST':
        client_profile = request.POST.get('client_profile', '')
        client.client_profile = client_profile
        client.save()
        
        user_activity_tool.run(
            request.user,
            'update',
            f"Updated client profile for: {client.name}",
            client=client
        )
        
        messages.success(request, "Client profile updated successfully.")
        return redirect('seo_manager:client_detail', client_id=client.id)
    
    messages.error(request, "Invalid form submission.")
    return redirect('seo_manager:client_detail', client_id=client.id)

@login_required
def generate_magic_profile(request, client_id):
    if request.method == 'POST':
        try:
            # Get the tool ID
            tool = get_object_or_404(Tool, tool_subclass='ClientProfileTool')
            
            # Start Celery task
            from apps.agents.tasks import run_tool
            task = run_tool.delay(tool.id, {'client_id': str(client_id)})
            
            return JsonResponse({
                'success': True,
                'task_id': task.id,
                'message': 'Profile generation started'
            })
                
        except Exception as e:
            logger.error(f"Error generating magic profile: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            })
            
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
def load_more_activities(request, client_id):
    page = int(request.GET.get('page', 1))
    per_page = 10
    start = (page - 1) * per_page
    end = start + per_page

    client = get_object_or_404(Client, id=client_id)
    important_categories = ['create', 'update', 'delete', 'export', 'import', 'other']
    
    activities = UserActivity.objects.filter(
        client=client,
        category__in=important_categories
    ).order_by('-timestamp')[start:end + 1]  # Get one extra to check if there are more

    has_more = len(activities) > per_page
    activities = activities[:per_page]  # Remove the extra item if it exists

    # Render activities to HTML
    html = render(request, 'seo_manager/includes/activity_items.html', {
        'client_activities': activities
    }).content.decode('utf-8')

    return JsonResponse({
        'success': True,
        'activities': html,
        'has_more': has_more
    })

@login_required
def export_activities(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    filter_type = request.GET.get('filter', 'all')
    
    # Get activities based on filter
    activities = UserActivity.objects.filter(client=client).order_by('-timestamp')
    if filter_type != 'all':
        activities = activities.filter(category=filter_type)
    
    # Create the HttpResponse object with CSV header
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{client.name}_activities_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    
    # Create CSV writer
    writer = csv.writer(response)
    writer.writerow(['Timestamp', 'User', 'Category', 'Action', 'Details'])
    
    # Write data
    for activity in activities:
        writer.writerow([
            activity.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            activity.user.username if activity.user else 'System',
            activity.get_category_display(),
            activity.action,
            activity.details if activity.details else ''
        ])
    
    # Log the export activity
    user_activity_tool.run(
        request.user,
        'export',
        f"Exported {filter_type} activities",
        client=client
    )
    
    return response

@login_required
def client_integrations(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    context = {
        'page_title': 'Client Integrations',
        'client': client,
        'segment': 'clients',
        'subsegment': 'integrations'
    }
    return render(request, 'seo_manager/client_integrations.html', context)
