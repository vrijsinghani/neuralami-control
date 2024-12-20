from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_http_methods
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from .models import Crew, CrewExecution, CrewMessage, Pipeline, Agent, CrewTask, Task
from .forms import CrewExecutionForm, HumanInputForm, AgentForm
from .tasks import execute_crew
from django.core.exceptions import ValidationError
import logging
import json
from django.urls import reverse
from django.core.cache import cache
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
import os
from apps.seo_manager.models import Client  # Import the Client model
from markdown_it import MarkdownIt  # Import markdown-it
from apps.common.utils import get_models

logger = logging.getLogger(__name__)
channel_layer = get_channel_layer()

# Initialize the MarkdownIt instance
md = MarkdownIt()

@login_required
@csrf_exempt
def connection_test(request):
    return render(request, 'agents/connection_test.html')

@login_required
def crewai_home(request):
    crews = Crew.objects.all()  # Get the first 3 crews for the summary
    recent_executions = CrewExecution.objects.filter(user=request.user).order_by('-created_at')[:10]
    clients = Client.objects.all()  # Get all clients
    
    # Get the selected client_id from the request, fallback to session
    selected_client_id = request.GET.get('client_id') or request.session.get('selected_client_id')
    
    if selected_client_id:
        request.session['selected_client_id'] = selected_client_id
    else:
        # If no client is selected, remove it from the session
        request.session.pop('selected_client_id', None)
    
    context = {
        'page_title': 'Crews Home',
        'crews': crews,
        'recent_executions': recent_executions,
        'clients': clients,
        'selected_client_id': selected_client_id,
    }
    return render(request, 'agents/crewai_home.html', context)

@login_required
def crew_list(request):
    logger.debug("Entering crew_list view")
    crews = Crew.objects.all()
    # Add page_title to the context
    context = {
        'crews': crews,
        'page_title': 'Crew List',
    }
    return render(request, 'agents/crew_list.html', context)

@login_required
def crew_detail(request, crew_id):
    crew = get_object_or_404(Crew, id=crew_id)
    recent_executions = CrewExecution.objects.filter(crew=crew).order_by('-created_at')[:5]
    
    # Get the selected client_id from the session
    selected_client_id = request.session.get('selected_client_id')
    selected_client = None
    if selected_client_id:
        selected_client = get_object_or_404(Client, id=selected_client_id)
    
    if request.method == 'POST':
        form = CrewExecutionForm(request.POST)
        if form.is_valid():
            execution = form.save(commit=False)
            execution.crew = crew
            execution.user = request.user
            execution.client = selected_client  # Associate the selected client with the execution
            
            # Handle input variables
            input_variables = json.loads(request.POST.get('input_variables', '{}'))
            execution.inputs = input_variables
            
            execution.save()
            
            # Start the execution
            execute_crew.delay(execution.id)
            
            messages.success(request, 'Crew execution started.')
            return JsonResponse({'status': 'success', 'execution_id': execution.id})
    else:
        form = CrewExecutionForm()
    
    context = {
        'page_title': 'Crew Detail',
        'crew': crew,
        'form': form,
        'recent_executions': recent_executions,
        'selected_client': selected_client,
    }
    return render(request, 'agents/crew_detail.html', context)

@login_required
def execution_list(request):
    logger.debug("Entering execution_list view")
    executions = CrewExecution.objects.filter(user=request.user).order_by('-created_at')
    crews = Crew.objects.all()

    # Apply filters
    crew_id = request.GET.get('crew')
    status = request.GET.get('status')

    if crew_id:
        executions = executions.filter(crew_id=crew_id)
    if status:
        executions = executions.filter(status=status)

    # Pagination
    paginator = Paginator(executions, 10)  # Show 10 executions per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_title': 'Execution List',
        'executions': page_obj,
        'crews': crews,
    }
    return render(request, 'agents/execution_list.html', context)

@login_required
def execution_detail(request, execution_id):
    execution = get_object_or_404(CrewExecution, id=execution_id)
    
    # Get all tasks for this crew through CrewTask
    crew_tasks = CrewTask.objects.filter(crew=execution.crew).select_related('task')
    kanban_tasks = []
    
    for crew_task in crew_tasks:
        task = crew_task.task
        stages = execution.stages.filter(task=task).order_by('created_at')
        
        stage_data = []
        for stage in stages:
            stage_data.append({
                'id': stage.id,
                'title': stage.title,
                'content': stage.content,
                'status': stage.status,
                'agent': stage.agent.name if stage.agent else None,
                'created_at': stage.created_at,
                'metadata': stage.metadata or {}
            })
        
        kanban_tasks.append({
            'id': task.id,
            'name': task.description,
            'stages': stage_data
        })
    
    context = {
        'page_title': 'Execution Detail',
        'execution': execution,
        'crew': execution.crew,
        'tasks': kanban_tasks
    }
    
    return render(request, 'agents/execution_detail.html', context)

@login_required
def execution_status(request, execution_id):
    try:
        execution = CrewExecution.objects.get(id=execution_id, user=request.user)
        
        # Get the last message ID from the request
        last_message_id = request.GET.get('last_message_id')
        
        # Only fetch new messages if there are any
        if last_message_id:
            messages = CrewMessage.objects.filter(
                execution=execution,
                id__gt=last_message_id
            ).order_by('timestamp')
        else:
            messages = CrewMessage.objects.filter(
                execution=execution
            ).order_by('timestamp')
        
        # Get status badge class
        status_classes = {
            'PENDING': 'info',
            'RUNNING': 'primary',
            'WAITING_FOR_HUMAN_INPUT': 'warning',
            'COMPLETED': 'success',
            'FAILED': 'danger'
        }
        status_class = status_classes.get(execution.status, 'secondary')
        
        response_data = {
            'status': execution.get_status_display(),
            'status_class': status_class,
            'updated_at': execution.updated_at.isoformat(),
            'outputs': execution.outputs,
            'human_input_request': execution.human_input_request,
            'messages': [{
                'id': msg.id,
                'agent': msg.agent,
                'content': msg.content,
                'timestamp': msg.timestamp.strftime("%d %b %H:%M")
            } for msg in messages],
        }
        return JsonResponse(response_data)
    except CrewExecution.DoesNotExist:
        return JsonResponse({'error': 'Execution not found'}, status=404)

@login_required
@csrf_protect
@require_POST
def provide_human_input(request, execution_id):
    try:
        execution = CrewExecution.objects.get(id=execution_id, user=request.user)
        if execution.status != 'WAITING_FOR_HUMAN_INPUT':
            return JsonResponse({'error': 'Execution is not waiting for human input'}, status=400)

        data = json.loads(request.body)
        user_input = data.get('input')

        if user_input is None:
            return JsonResponse({'error': 'No input provided'}, status=400)

        # Store the user input in the cache
        cache.set(f'human_input_response_{execution_id}', user_input, timeout=3600)

        logger.info(f"Stored user input for execution {execution_id}: {user_input}")

        # Update execution status
        execution.status = 'RUNNING'
        execution.save()

        # Send a WebSocket message to update the frontend
        async_to_sync(channel_layer.group_send)(
            f'crew_execution_{execution_id}',
            {
                'type': 'crew_execution_update',
                'status': 'RUNNING',
                'messages': [{'agent': 'Human', 'content': f'Input provided: {user_input}'}],
            }
        )

        # Return the actual user input
        return JsonResponse({'message': 'Human input received and processing resumed', 'input': user_input})
    except CrewExecution.DoesNotExist:
        return JsonResponse({'error': 'Execution not found'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error in provide_human_input: {str(e)}")
        return JsonResponse({'error': 'An unexpected error occurred'}, status=500)

@login_required
def manage_pipelines(request):
    pipelines = Pipeline.objects.all()
    context = {
        'page_title': 'Manage Pipelines',
        'pipelines': pipelines,
    }
    return render(request, 'agents/manage_pipelines.html', context)

@login_required
@require_POST
def submit_human_input(request, execution_id):
    input_key = request.POST.get('input_key')
    response = request.POST.get('response')
    
    if not input_key or not response:
        return JsonResponse({'error': 'Missing input_key or response'}, status=400)
    
    execution = get_object_or_404(CrewExecution, id=execution_id, user=request.user)
    
    # Store the response in the cache
    cache_key = f"{input_key}_response"
    cache.set(cache_key, response, timeout=3600)
    
    # Verify that the input was stored correctly
    stored_value = cache.get(cache_key)
    logger.info(f"Stored human input in cache for execution {execution_id}: key={cache_key}, value={response}")
    
    # Update execution status
    execution.status = 'RUNNING'
    execution.save()
    
    return JsonResponse({'message': 'Human input received and processed'})

@login_required
def chat_view(request):
    clients = Client.objects.all().order_by('name')
    print(f"Found {clients.count()} clients")  # Debug print
    
    context = {
        'agents': Agent.objects.all(),
        'models': get_models(),
        'default_model': settings.GENERAL_MODEL,
        'clients': clients,
    }
    return render(request, 'agents/chat.html', context)

