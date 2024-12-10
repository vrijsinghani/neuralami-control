from datetime import timedelta
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views.generic import ListView, CreateView, DetailView
from django.urls import reverse_lazy
from django.db.models import Avg
import json
from ..models import Client, SEOProject
from ..forms import SEOProjectForm
from apps.common.tools.user_activity_tool import user_activity_tool

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
    template_name = 'seo_manager/projects/project_form.html'

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
        
        response = super().form_valid(form)
        user_activity_tool.run(self.request.user, 'create', f"Created SEO project: {form.instance.title}", client=form.instance.client)
        return response

    def get_success_url(self):
        return reverse_lazy('seo_manager:client_detail', kwargs={'client_id': self.kwargs['client_id']})

class ProjectDetailView(LoginRequiredMixin, DetailView):
    model = SEOProject
    template_name = 'seo_manager/projects/project_detail.html'
    context_object_name = 'project'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get the implementation date
        implementation_date = self.object.implementation_date
        
        # Calculate periods for comparison
        pre_period_start = implementation_date - timedelta(days=30)
        post_period_end = implementation_date + timedelta(days=30)
        
        # Prepare data for the ranking history chart and performance metrics
        ranking_data = {
            'labels': [],
            'datasets': []
        }
        
        performance_metrics = []
        
        for keyword in self.object.targeted_keywords.all():
            # Get rankings for before and after implementation
            rankings = keyword.ranking_history.filter(
                date__range=(pre_period_start, post_period_end)
            ).order_by('date')
            
            # Calculate average positions for before and after
            pre_avg = rankings.filter(
                date__lt=implementation_date
            ).aggregate(Avg('average_position'))['average_position__avg']
            
            post_avg = rankings.filter(
                date__gte=implementation_date
            ).aggregate(Avg('average_position'))['average_position__avg']
            
            # Calculate improvement
            improvement = pre_avg - post_avg if pre_avg and post_avg else None
            
            # Add to performance metrics
            performance_metrics.append({
                'keyword': keyword.keyword,
                'initial_position': self.object.initial_rankings.get(keyword.keyword),
                'current_position': keyword.ranking_history.first().average_position if keyword.ranking_history.exists() else None,
                'pre_avg': round(pre_avg, 1) if pre_avg else None,
                'post_avg': round(post_avg, 1) if post_avg else None,
                'improvement': round(improvement, 1) if improvement else None
            })
            
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
