from datetime import timedelta
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views.generic import ListView, CreateView, DetailView
from django.urls import reverse_lazy
from django.db.models import Avg
import json
import logging
from ..models import Client, SEOProject
from ..forms import SEOProjectForm
from apps.common.tools.user_activity_tool import user_activity_tool
from apps.common.utils import create_box

logger = logging.getLogger(__name__)

class ProjectListView(LoginRequiredMixin, ListView):
    template_name = 'seo_manager/projects/project_list.html'
    context_object_name = 'projects'

    def get_queryset(self):
        return SEOProject.objects.filter(client_id=self.kwargs['client_id'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['client'] = get_object_or_404(Client, id=self.kwargs['client_id'])
        return context

class ProjectCreateView(LoginRequiredMixin, CreateView):
    model = SEOProject
    form_class = SEOProjectForm
    
    def get(self, request, *args, **kwargs):
        # Redirect GET requests to client detail page since we're using modal
        return redirect('seo_manager:client_detail', client_id=self.kwargs['client_id'])
    
    def post(self, request, *args, **kwargs):
        form = self.get_form()
        logger.info(f"Form data: {request.POST}")
        if form.is_valid():
            logger.info("Form is valid")
            return self.form_valid(form)
        else:
            logger.error(f"Form errors: {form.errors}")
            # Redirect back to client detail with form errors in session
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
            return redirect('seo_manager:client_detail', client_id=self.kwargs['client_id'])
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['client'] = get_object_or_404(Client, id=self.kwargs['client_id'])
        return kwargs

    def form_valid(self, form):
        form.instance.client_id = self.kwargs['client_id']
        # Capture initial rankings for targeted keywords
        initial_rankings = {}
        for keyword in form.cleaned_data['targeted_keywords']:
            latest_ranking = keyword.ranking_history.first()
            if latest_ranking:
                initial_rankings[keyword.keyword] = latest_ranking.average_position
        form.instance.initial_rankings = initial_rankings
        
        try:
            self.object = form.save()
            logger.info(f"Project saved successfully: {self.object.id}")
            user_activity_tool.run(self.request.user, 'create', f"Created SEO project: {form.instance.title}", client=form.instance.client)
            messages.success(self.request, 'Project created successfully!')
        except Exception as e:
            logger.error(f"Error saving project: {str(e)}")
            messages.error(self.request, f"Error creating project: {str(e)}")
            
        return redirect('seo_manager:client_detail', client_id=self.kwargs['client_id'])
class ProjectDetailView(LoginRequiredMixin, DetailView):
    model = SEOProject
    template_name = 'seo_manager/projects/project_detail.html'
    context_object_name = 'project'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        implementation_date = self.object.implementation_date
        pre_period_start = implementation_date - timedelta(days=30)
        post_period_end = implementation_date + timedelta(days=30)
        
        ranking_data = {
            'labels': [],
            'datasets': []
        }

        # Get impact analysis results with null check
        impact_analysis = self.object.analyze_impact() or {}
        performance_metrics = []

        for keyword in self.object.targeted_keywords.all():
            rankings = keyword.ranking_history.filter(
                date__range=(pre_period_start, post_period_end)
            ).order_by('date')

            # Get impact metrics with safe defaults
            keyword_impact = impact_analysis.get(keyword.keyword, {})
            current_ranking = keyword.ranking_history.first()
            
            metrics = {
                'keyword': keyword.keyword,
                'initial_position': self.object.initial_rankings.get(keyword.keyword),
                'current_position': current_ranking.average_position if current_ranking else None,
                'pre_avg': None,
                'post_avg': None,
                'improvement': None,
                'impressions_change': None,
                'clicks_change': None
            }
            
            # Safely get and round values only if they exist
            if keyword_impact.get('pre_implementation_avg') is not None:
                metrics['pre_avg'] = round(float(keyword_impact['pre_implementation_avg']), 1)
            
            if keyword_impact.get('post_implementation_avg') is not None:
                metrics['post_avg'] = round(float(keyword_impact['post_implementation_avg']), 1)
            
            if keyword_impact.get('improvement') is not None:
                metrics['improvement'] = round(float(keyword_impact['improvement']), 1)
            
            if keyword_impact.get('impressions_change') is not None:
                metrics['impressions_change'] = round(float(keyword_impact['impressions_change']), 1)
            
            if keyword_impact.get('clicks_change') is not None:
                metrics['clicks_change'] = round(float(keyword_impact['clicks_change']), 1)
            
            performance_metrics.append(metrics)

            # Prepare chart dataset
            dataset = {
                'label': keyword.keyword,
                'data': [],
                'borderColor': f'#{hash(keyword.keyword) % 0xFFFFFF:06x}',
                'tension': 0.4,
                'fill': False
            }

            for ranking in rankings:
                if ranking.date.isoformat() not in ranking_data['labels']:
                    ranking_data['labels'].append(ranking.date.isoformat())
                dataset['data'].append(ranking.average_position)

            ranking_data['datasets'].append(dataset)

        # Add implementation date marker to chart
        ranking_data['implementation_date'] = implementation_date.isoformat()

        context.update({
            'ranking_history_data': json.dumps(ranking_data),
            'performance_metrics': performance_metrics,
            'implementation_date': implementation_date,
            'pre_period_start': pre_period_start,
            'post_period_end': post_period_end
        })

        return context

        return context
@login_required
def edit_project(request, client_id, project_id):
    """View for editing an existing SEO project."""
    project = get_object_or_404(SEOProject, id=project_id, client_id=client_id)
    
    if request.method == 'POST':
        form = SEOProjectForm(request.POST, instance=project, client=project.client)
        if form.is_valid():
            form.save()
            messages.success(request, 'Project updated successfully.')
            return redirect('seo_manager:client_detail', client_id=client_id)
    else:
        form = SEOProjectForm(instance=project, client=project.client)
    
    context = {
        'page_title': 'Edit Project',
        'form': form,
        'project': project,
        'client_id': client_id,
    }
    
    return render(request, 'seo_manager/projects/edit_project.html', context)

@login_required
def delete_project(request, client_id, project_id):
    """View for deleting an SEO project."""
    project = get_object_or_404(SEOProject, id=project_id, client_id=client_id)
    
    if request.method == 'POST':
        project.delete()
        messages.success(request, 'Project deleted successfully.')
        return redirect('seo_manager:client_detail', client_id=client_id)
    
    return redirect('seo_manager:client_detail', client_id=client_id)
