import csv
import io
import logging
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views.generic import ListView, CreateView, UpdateView
from django.urls import reverse_lazy
from django.http import JsonResponse
from ..models import Client, TargetedKeyword, KeywordRankingHistory, SearchConsoleCredentials
from ..forms import TargetedKeywordForm, KeywordBulkUploadForm
from apps.common.tools.user_activity_tool import user_activity_tool
import json
from datetime import datetime, timedelta
from .search_console_views import get_search_console_data

logger = logging.getLogger(__name__)

class KeywordListView(LoginRequiredMixin, ListView):
    template_name = 'seo_manager/keywords/keyword_list.html'
    context_object_name = 'keywords'

    def get_queryset(self):
        return TargetedKeyword.objects.filter(client_id=self.kwargs['client_id'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['client'] = get_object_or_404(Client, id=self.kwargs['client_id'])
        context['import_form'] = KeywordBulkUploadForm()
        return context

class KeywordCreateView(LoginRequiredMixin, CreateView):
    model = TargetedKeyword
    form_class = TargetedKeywordForm
    template_name = 'seo_manager/keywords/keyword_form.html'

    def form_valid(self, form):
        form.instance.client_id = self.kwargs['client_id']
        response = super().form_valid(form)
        user_activity_tool.run(self.request.user, 'create', f"Added keyword: {form.instance.keyword}", client=form.instance.client)
        return response

    def get_success_url(self):
        return reverse_lazy('seo_manager:client_detail', kwargs={'client_id': self.kwargs['client_id']})

class KeywordUpdateView(LoginRequiredMixin, UpdateView):
    model = TargetedKeyword
    form_class = TargetedKeywordForm
    template_name = 'seo_manager/keywords/keyword_form.html'

    def get_queryset(self):
        # Ensure the keyword belongs to the correct client
        return TargetedKeyword.objects.filter(
            client_id=self.kwargs['client_id']
        )

    def form_valid(self, form):
        response = super().form_valid(form)
        user_activity_tool.run(
            self.request.user, 
            'update', 
            f"Updated keyword: {form.instance.keyword}", 
            client=form.instance.client
        )
        messages.success(self.request, "Keyword updated successfully.")
        return response

    def get_success_url(self):
        return reverse_lazy('seo_manager:client_detail', 
                          kwargs={'client_id': self.kwargs['client_id']})

@login_required
def keyword_import(request, client_id):
    if request.method == 'POST':
        form = KeywordBulkUploadForm(request.POST, request.FILES)
        if form.is_valid():
            client = get_object_or_404(Client, id=client_id)
            csv_file = request.FILES['csv_file']
            decoded_file = csv_file.read().decode('utf-8')
            csv_data = csv.DictReader(io.StringIO(decoded_file))
            
            for row in csv_data:
                TargetedKeyword.objects.create(
                    client=client,
                    keyword=row['keyword'],
                    priority=int(row['priority']),
                    notes=row.get('notes', '')
                )
            
            user_activity_tool.run(request.user, 'import', f"Imported keywords from CSV", client=client)
            messages.success(request, "Keywords imported successfully.")
            return redirect('seo_manager:client_detail', client_id=client_id)
    
    messages.error(request, "Invalid form submission.")
    return redirect('seo_manager:client_detail', client_id=client_id)

@login_required
def debug_keyword_data(request, client_id, keyword_id):
    """Debug view to check keyword data"""
    keyword = get_object_or_404(TargetedKeyword, id=keyword_id, client_id=client_id)
    
    rankings = KeywordRankingHistory.objects.filter(
        keyword=keyword
    ).order_by('-date')
    
    data = {
        'keyword': keyword.keyword,
        'current_position': keyword.current_position,
        'position_change': keyword.get_position_change(),
        'rankings': [
            {
                'date': r.date.strftime('%Y-%m-%d'),
                'position': r.average_position,
                'impressions': r.impressions,
                'clicks': r.clicks,
                'ctr': r.ctr
            }
            for r in rankings
        ]
    }
    
    return JsonResponse(data)

@login_required
def import_from_search_console(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    
    if request.method == 'POST':
        try:
            keywords_data = json.loads(request.body)
            imported_count = 0
            
            for keyword_data in keywords_data:
                keyword = keyword_data.get('keyword')
                if keyword:
                    # Check if keyword already exists
                    if not TargetedKeyword.objects.filter(client=client, keyword=keyword).exists():
                        # Create the keyword
                        keyword_obj = TargetedKeyword.objects.create(
                            client=client,
                            keyword=keyword,
                            notes=f"""Imported from Search Console
Initial Position: {keyword_data.get('position', 'N/A')}
Clicks: {keyword_data.get('clicks', 0)}
Impressions: {keyword_data.get('impressions', 0)}
CTR: {keyword_data.get('ctr', 0)}%"""
                        )

                        # Create initial ranking history entry
                        KeywordRankingHistory.objects.create(
                            keyword=keyword_obj,
                            client=client,
                            keyword_text=keyword,
                            date=datetime.now().date(),
                            average_position=keyword_data.get('position', 0),
                            clicks=keyword_data.get('clicks', 0),
                            impressions=keyword_data.get('impressions', 0),
                            ctr=keyword_data.get('ctr', 0)
                        )
                        
                        imported_count += 1
            
            user_activity_tool.run(
                request.user, 
                'import', 
                f"Imported {imported_count} keywords from Search Console", 
                client=client
            )
            
            return JsonResponse({
                'success': True,
                'message': f'Successfully imported {imported_count} keywords'
            })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid data format'
            }, status=400)
        except Exception as e:
            logger.error(f"Error importing keywords: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
            
    return JsonResponse({
        'success': False,
        'error': 'Invalid request method'
    }, status=405)

@login_required
def search_console_keywords(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    search_console_data = []
    
    try:
        sc_credentials = SearchConsoleCredentials.objects.get(client=client)
        if sc_credentials:
            service = sc_credentials.get_service()
            if service:
                property_url = sc_credentials.get_property_url()
                if property_url:
                    # Get last 90 days of data
                    end_date = datetime.now().strftime('%Y-%m-%d')
                    start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
                    search_console_data = get_search_console_data(
                        service, 
                        property_url,
                        start_date,
                        end_date
                    )
    except SearchConsoleCredentials.DoesNotExist:
        pass
    except Exception as e:
        logger.error(f"Error fetching search console data: {str(e)}")
    
    context = {
        'page_title': 'Search Console Keywords',
        'client': client,
        'search_console_data': search_console_data,
    }
    return render(request, 'seo_manager/keywords/search_console_keywords.html', context)
