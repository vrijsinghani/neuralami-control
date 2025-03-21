from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from django.template.loader import render_to_string
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from django.conf import settings
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import json
import logging

from .models import Research
from .forms import ResearchForm
from .tasks import run_research
from apps.common.utils import get_models
from apps.organizations.utils import get_current_organization

logger = logging.getLogger(__name__)
channel_layer = get_channel_layer()

@login_required
def research_create(request):
    """Create a new research task."""
    available_models = get_models()
    selected_model = getattr(settings, 'GENERAL_MODEL', available_models[0] if available_models else None)
    
    if request.method == 'POST':
        form = ResearchForm(request.POST)
        if form.is_valid():
            # Create and save the research object
            research = form.save(commit=False)
            research.user = request.user
            research.save()
            
            # Get selected model from form
            model_name = request.POST.get('model', selected_model)
            
            # Get current organization
            organization = get_current_organization()
            organization_id = organization.id if organization else None
            
            # Start Celery task with selected model and organization context
            run_research.delay(
                research_id=research.id,
                model_name=model_name,
                tool_params={
                    'llm_model': model_name
                },
                organization_id=organization_id
            )
            
            return redirect('research:detail', research_id=research.id)
    else:
        form = ResearchForm()
    
    return render(request, 'research/create.html', {
        'form': form,
        'available_models': available_models,
        'selected_model': selected_model
    })

@ensure_csrf_cookie
@login_required
def research_detail(request, research_id):
    """View details of a research task."""
    research = get_object_or_404(Research, id=research_id, user=request.user)
    available_models = get_models()
    selected_model = getattr(settings, 'GENERAL_MODEL', available_models[0] if available_models else None)
    
    return render(request, 'research/detail.html', {
        'research': research,
        'available_models': json.dumps(available_models),
        'selected_model': selected_model
    })

@login_required
def research_list(request):
    """List all research tasks for the current user."""
    researches = Research.objects.filter(user=request.user)
    return render(request, 'research/list.html', {
        'researches': researches
    })

@require_POST
@login_required
def cancel_research(request, research_id):
    """Cancel a running research task."""
    try:
        # Log current user for debugging
        logger.info(f"Cancel research request for ID {research_id} by user {request.user.email} (ID: {request.user.id})")
        
        # Use get_object_or_404 with just the ID - the objects manager will filter by organization automatically
        research = get_object_or_404(Research, id=research_id)
        
        # Log for debugging
        logger.info(f"Found research {research_id}, owned by user {research.user.email} (ID: {research.user.id})")
        
        # Extra security check that this is the user's research
        if research.user.id != request.user.id:
            logger.warning(f"User mismatch: request user {request.user.id} != research user {research.user.id}")
            return HttpResponse(status=403)
        
        if research.status in ['pending', 'in_progress']:
            # Update status in database
            research.status = 'cancelled'
            research.save(update_fields=['status'])
            
            # Log for debugging
            logger.info(f"Research {research_id} cancelled successfully")
            
            # Send cancellation message through WebSocket
            async_to_sync(channel_layer.group_send)(
                f"research_{research_id}",
                {
                    "type": "status_update",
                    "status": "cancelled",
                    "message": "Research cancelled by user",
                    "progress": 0
                }
            )
            
            return HttpResponse(status=200)
        else:
            logger.info(f"Research {research_id} status is {research.status}, cannot cancel")
            return HttpResponse(status=400)
    except Exception as e:
        logger.error(f"Error cancelling research {research_id}: {str(e)}", exc_info=True)
        return HttpResponse(status=500)

@login_required
def research_progress(request, research_id):
    """HTMX endpoint for progress updates."""
    if not request.headers.get('HX-Request'):
        return HttpResponse(status=400)
        
    research = get_object_or_404(Research, id=research_id, user=request.user)
    
    # Calculate progress percentage
    progress = 0
    if research.status == 'completed':
        progress = 100
    elif research.status == 'in_progress':
        # Estimate progress based on steps
        step_count = len(research.reasoning_steps)
        expected_total = 10  # Typical number of steps
        progress = min(95, int((step_count / expected_total) * 100))
    
    return render(request, 'research/partials/progress.html', {
        'research': research,
        'progress': progress
    })

@login_required
def research_sources(request, research_id):
    """HTMX endpoint for sources updates."""
    if not request.headers.get('HX-Request'):
        return HttpResponse(status=400)
        
    research = get_object_or_404(Research, id=research_id, user=request.user)
    
    return render(request, 'research/partials/sources.html', {
        'research': research
    })

@login_required
def research_reasoning(request, research_id):
    """HTMX endpoint for reasoning chain updates."""
    if not request.headers.get('HX-Request'):
        return HttpResponse(status=400)
        
    research = get_object_or_404(Research, id=research_id, user=request.user)
    
    return render(request, 'research/partials/steps.html', {
        'research': research
    }) 