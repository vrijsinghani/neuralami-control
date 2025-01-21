from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect
from django.utils import timezone
import json
from django.core.cache import cache
from celery import current_app

from .models import Crew, CrewExecution, ExecutionStage, Task, Agent, CrewTask
from apps.seo_manager.models import Client
from apps.agents.tasks.messaging.execution_bus import ExecutionMessageBus

import logging
logger = logging.getLogger(__name__)

@login_required
def crew_kanban(request, crew_id):
    crew = get_object_or_404(Crew, id=crew_id)
    client_id = request.GET.get('client_id')
    client = get_object_or_404(Client, id=client_id) if client_id else None
    
    # Get all tasks for this crew through CrewTask
    crew_tasks = CrewTask.objects.filter(crew=crew).select_related('task')
    kanban_tasks = []
    
    for crew_task in crew_tasks:
        task = crew_task.task
        # Get executions for this crew
        executions = CrewExecution.objects.filter(
            crew=crew,
            client=client
        ).prefetch_related('stages')
        
        execution_data = []
        for execution in executions:
            stages = execution.stages.all()
            stage_data = {}
            
            for stage in stages:
                stage_data[stage.stage_type] = {
                    'title': stage.title,
                    'content': stage.content,
                    'status': stage.status,
                    'agent': stage.agent.name if stage.agent else None
                }
                
                # Add stage-specific metadata
                if stage.metadata:
                    stage_data[stage.stage_type].update(stage.metadata)
            
            execution_data.append({
                'id': execution.id,
                'name': f'Execution #{execution.id}',
                'status': execution.status,
                'stages': stage_data
            })
        
        kanban_tasks.append({
            'id': task.id,
            'name': task.description,
            'executions': execution_data
        })
    
    # Add page_title to the context
    context = {
        'crew': crew,
        'client': client,
        'tasks': kanban_tasks,
        'page_title': 'Crew Run',
    }
    return render(request, 'agents/crew_kanban.html', context)

@login_required
@require_http_methods(['POST'])
@csrf_protect
def start_execution(request, crew_id):
    crew = get_object_or_404(Crew, id=crew_id)
    
    try:
        data = json.loads(request.body)
        client_id = data.get('client_id')
            
        if not client_id:
            return JsonResponse({
                'status': 'error',
                'message': 'Client ID is required'
            }, status=400)
            
        client = get_object_or_404(Client, id=client_id)
        
        # Get the first task for this crew
        crew_task = CrewTask.objects.filter(crew=crew).order_by('order').first()
        if not crew_task:
            return JsonResponse({
                'status': 'error',
                'message': 'No tasks found for this crew'
            }, status=400)
        
        # Create new execution
        execution = CrewExecution.objects.create(
            crew=crew,
            status='PENDING',
            inputs={
                'client_id': client_id
            },
            user=request.user,
            client=client
        )
        
        # Create initial stage
        stage = ExecutionStage.objects.create(
            execution=execution,
            stage_type='task_start',
            title='Starting New Execution',
            content='Initializing crew execution workflow',
            status='pending'
        )
        
        # Start the Celery task
        from .tasks import execute_crew
        task = execute_crew.delay(execution.id)
        
        # Update execution with task_id immediately
        execution.task_id = task.id
        execution.save()
        
        # Use ExecutionMessageBus for notifications
        message_bus = ExecutionMessageBus(execution.id)
        message_bus.publish('execution_update', {
            'status': 'PENDING',
            'message': 'New execution started',
            'crewai_task_id': crew_task.task.id,  # For proper board placement
            'stage': {
                'stage_type': 'task_start',
                'title': 'Starting New Execution',
                'content': 'Initializing crew execution workflow',
                'status': 'pending'
            }
        })
        
        return JsonResponse({
            'status': 'success',
            'execution_id': execution.id,
            'task_id': crew_task.task.id
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f'Error starting execution: {str(e)}', exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

@login_required
@require_http_methods(['GET'])
def get_active_executions(request, crew_id):
    """Get all active executions for a crew"""
    crew = get_object_or_404(Crew, id=crew_id)
    
    # Get all in-progress executions for this crew
    executions = CrewExecution.objects.filter(
        crew=crew,
        status__in=['pending', 'in_progress']
    ).prefetch_related('stages')
    
    execution_data = []
    for execution in executions:
        stages = execution.stages.all()
        stage_data = {}
        
        for stage in stages:
            stage_data[stage.stage_type] = {
                'title': stage.title,
                'content': stage.content,
                'status': stage.status,
                'agent': stage.agent.name if stage.agent else None
            }
            
            if stage.metadata:
                stage_data[stage.stage_type].update(stage.metadata)
        
        execution_data.append({
            'execution_id': execution.id,
            'task_id': execution.task_id if hasattr(execution, 'task_id') else None,
            'name': f'Execution #{execution.id}',
            'status': execution.status,
            'stages': stage_data
        })
    
    return JsonResponse({'executions': execution_data})

@login_required
@require_http_methods(['POST'])
@csrf_protect
def submit_human_input(request, execution_id):
    execution = get_object_or_404(CrewExecution, id=execution_id)
    
    try:
        data = json.loads(request.body)
        input_text = data.get('input')
        
        if not input_text:
            return JsonResponse({
                'status': 'error',
                'message': 'Input text is required'
            }, status=400)
        
        # Update execution with human input
        execution.human_input_response = {'input': input_text}
        execution.status = 'RUNNING'
        execution.save()
        
        # Set response in cache with correct key format
        input_key = f"execution_{execution_id}_task_0_input"  # We use task 0 as that's the current task
        cache.set(input_key, input_text, timeout=3600)
        
        # Create human input stage
        stage = ExecutionStage.objects.create(
            execution=execution,
            stage_type='human_input',
            title='Human Input Received',
            content=input_text,
            status='completed',
            metadata={
                'input_timestamp': timezone.now().isoformat()
            }
        )
        
        # Use ExecutionMessageBus for notifications
        message_bus = ExecutionMessageBus(execution_id)
        message_bus.publish('execution_update', {
            'status': 'RUNNING',
            'message': 'Human input received',
            'stage': {
                'stage_type': 'human_input',
                'title': stage.title,
                'content': stage.content,
                'status': stage.status,
                'completed': True,
                'agent': 'Human'
            }
        })
        
        return JsonResponse({'status': 'success'})
        
    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

@login_required
@require_http_methods(["POST"])
def cancel_execution(request, execution_id):
    execution = get_object_or_404(CrewExecution, id=execution_id)
    
    if execution.task_id:
        # Revoke the Celery task
        current_app.control.revoke(task_id=execution.task_id, terminate=True)
        
        # Update execution status
        execution.status = 'CANCELLED'
        execution.save()
        
        # Notify about cancellation
        message_bus = ExecutionMessageBus(execution_id)
        message_bus.publish('execution_update', {
            'status': 'CANCELLED',
            'message': 'Execution cancelled by user',
            'stage': {
                'stage_type': 'cancellation',
                'title': 'Execution Cancelled',
                'content': 'The execution was cancelled by the user',
                'status': 'cancelled',
                'agent': 'System'
            }
        })
        
        return JsonResponse({'status': 'success'})
    
    return JsonResponse({'status': 'error', 'message': 'No task ID found'}, status=404)

@login_required
def execution_detail(request, execution_id):
    execution = get_object_or_404(CrewExecution.objects.select_related('crew', 'crew_output'), id=execution_id)
    crew = execution.crew
    
    # Define the columns we want to show
    columns = [
        {'id': 'task_start', 'name': 'Task Start'},
        {'id': 'thinking', 'name': 'Thinking'},
        {'id': 'tool_usage', 'name': 'Tool Usage'},
        {'id': 'tool_results', 'name': 'Tool Results'},
        {'id': 'human_input', 'name': 'Human Input'},
        {'id': 'completion', 'name': 'Completion'}
    ]
    
    # Get all stages for this execution
    stages = execution.stages.all().select_related('agent').order_by('created_at')
    
    # Get all messages for this execution
    messages = execution.messages.all().order_by('timestamp')
    
    # Organize stages by stage_type
    kanban_columns = []
    for column in columns:
        column_stages = []
        
        # Add stages for this column
        for stage in stages:
            if stage.stage_type == column['id']:
                stage_data = {
                    'id': stage.id,
                    'title': stage.title,
                    'content': stage.content,
                    'status': stage.status,
                    'agent': stage.agent.name if stage.agent else None,
                    'created_at': stage.created_at,
                    'metadata': stage.metadata or {},
                    'type': 'stage'
                }
                column_stages.append(stage_data)
        
        # Add messages that might be related to this stage type
        if column['id'] == 'thinking':
            for message in messages:
                column_stages.append({
                    'id': f'msg_{message.id}',
                    'title': f'Message from {message.agent}',
                    'content': message.content,
                    'status': 'completed',
                    'agent': message.agent,
                    'created_at': message.timestamp,
                    'type': 'message'
                })
        
        # Add crew output to completion column
        if column['id'] == 'completion' and execution.crew_output:
            output_data = {
                'id': 'output',
                'title': 'Final Output',
                'content': execution.crew_output.raw,
                'status': 'completed',
                'created_at': execution.updated_at,
                'type': 'output',
                'metadata': {
                    'json_output': execution.crew_output.json_dict,
                    'token_usage': execution.crew_output.token_usage
                }
            }
            column_stages.append(output_data)
        
        kanban_columns.append({
            'id': column['id'],
            'name': column['name'],
            'stages': sorted(column_stages, key=lambda x: x['created_at'])
        })
    
    context = {
        'page_title': 'Execution Detail',
        'execution': execution,
        'crew': crew,
        'columns': kanban_columns
    }
    
    return render(request, 'agents/execution_detail.html', context)
