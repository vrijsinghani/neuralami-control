from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.urls import reverse
from .models import Research
from .forms import ResearchForm
from .tasks import run_research
from apps.common.utils import get_models
from django.conf import settings
import json
from django.views.decorators.http import require_POST
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import logging

@login_required
def research_create(request):
    available_models = get_models()
    selected_model = getattr(settings, 'GENERAL_MODEL', available_models[0] if available_models else None)
    
    if request.method == 'POST':
        form = ResearchForm(request.POST)
        if form.is_valid():
            research = form.save(commit=False)
            research.user = request.user
            research.save()
            
            # Get selected model from form
            model_name = request.POST.get('model', selected_model)
            
            # Start Celery task with selected model
            run_research.delay(research.id, model_name=model_name)
            
            return redirect('research:detail', research_id=research.id)
    else:
        form = ResearchForm()
    
    return render(request, 'research/create.html', {
        'form': form,
        'available_models': available_models,
        'selected_model': selected_model
    })

@login_required
def research_detail(request, research_id):
    research = get_object_or_404(Research, id=research_id, user=request.user)
    available_models = get_models()
    selected_model = getattr(settings, 'GENERAL_MODEL', available_models[0] if available_models else None)
    
    logger = logging.getLogger(__name__)
    logger.info(f"Research status: {research.status}")
    
    return render(request, 'research/detail.html', {
        'research': research,
        'available_models': json.dumps(available_models),
        'selected_model': selected_model
    })

@login_required
def research_list(request):
    researches = Research.objects.filter(user=request.user)
    return render(request, 'research/list.html', {
        'researches': researches
    })

@require_POST
@login_required
def cancel_research(request, research_id):
    research = get_object_or_404(Research, id=research_id, user=request.user)
    
    if research.status in ['pending', 'in_progress']:
        research.status = 'cancelled'
        research.save()
        
        # Send cancellation message through WebSocket
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"research_{research_id}",
            {
                "type": "research_update",
                "data": {
                    "update_type": "cancelled",
                }
            }
        )
        
        return JsonResponse({'status': 'success'})
    
    return JsonResponse({'status': 'error', 'message': 'Research cannot be cancelled'}, status=400) 