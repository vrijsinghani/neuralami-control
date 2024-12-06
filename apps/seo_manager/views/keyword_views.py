import csv
import io
import logging
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views.generic import ListView, CreateView, UpdateView
from django.urls import reverse_lazy
from django.http import JsonResponse
from ..models import Client, TargetedKeyword, KeywordRankingHistory
from ..forms import TargetedKeywordForm, KeywordBulkUploadForm
from apps.common.tools.user_activity_tool import user_activity_tool

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
