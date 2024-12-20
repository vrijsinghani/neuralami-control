import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
import traceback
from .models import Tool
from .forms import ToolForm
from .utils import get_available_tools, get_tool_classes, get_tool_description, get_tool_class_obj, load_tool
from pydantic import BaseModel
import inspect
import json
import tiktoken
import csv
from io import StringIO
import asyncio
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)

def is_admin(user):
    return user.is_staff or user.is_superuser

def count_tokens(text):
    encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
    return len(encoding.encode(text))

@login_required
@user_passes_test(is_admin)
def manage_tools(request):
    tools = Tool.objects.all().order_by('name')
    return render(request, 'agents/manage_tools.html', {'tools': tools, 'page_title': 'Manage Tools'})

@login_required
@user_passes_test(is_admin)
def add_tool(request):
    if request.method == 'POST':
        form = ToolForm(request.POST)
        logger.debug(f"POST data: {request.POST}")
        if form.is_valid():
            tool = form.save(commit=False)
            tool_class = form.cleaned_data['tool_class']
            tool_subclass = form.cleaned_data['tool_subclass']
            
            logger.debug(f"Adding tool: class={tool_class}, subclass={tool_subclass}")
            
            # Get the tool class object and its description
            tool_classes = get_tool_classes(tool_class)
            logger.debug(f"Available tool classes: {[cls.__name__ for cls in tool_classes]}")
            if tool_classes:
                tool_class_obj = next((cls for cls in tool_classes if cls.__name__ == tool_subclass), None)
                if tool_class_obj:
                    logger.debug(f"Tool class object: {tool_class_obj}")
                    
                    tool.description = get_tool_description(tool_class_obj)
                    logger.debug(f"Tool description: {tool.description}")
                    
                    # Save the tool
                    tool.save()
                    
                    messages.success(request, 'Tool added successfully.')
                    return redirect('agents:manage_tools')
                else:
                    messages.error(request, f'Tool subclass {tool_subclass} not found.')
            else:
                messages.error(request, 'Tool class not found.')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
            logger.error(f"Form errors: {form.errors}")
    else:
        form = ToolForm()
    # Add page_title to the context
    context = {
        'form': form,
        'page_title': 'Add Tool',
    }
    return render(request, 'agents/tool_form.html', context)

@login_required
@user_passes_test(is_admin)
def edit_tool(request, tool_id):
    tool = get_object_or_404(Tool, id=tool_id)
    if request.method == 'POST':
        form = ToolForm(request.POST, instance=tool)
        if form.is_valid():
            tool = form.save(commit=False)
            tool.name = form.cleaned_data['tool_subclass']
            tool_class = form.cleaned_data['tool_class']
            tool_subclass = form.cleaned_data['tool_subclass']
            
            tool_class_obj = get_tool_class_obj(tool_class, tool_subclass)
            tool.description = get_tool_description(tool_class_obj)
            tool.save()
            messages.success(request, 'Tool updated successfully.')
            return redirect('agents:manage_tools')
    else:
        form = ToolForm(instance=tool)
    # Add page_title to the context
    context = {
        'form': form,
        'tool': tool,
        'page_title': 'Edit Tool',
    }
    
    return render(request, 'agents/tool_form.html', context)

@login_required
@user_passes_test(is_admin)
def delete_tool(request, tool_id):
    tool = get_object_or_404(Tool, id=tool_id)
    if request.method == 'POST':
        tool.delete()
        messages.success(request, 'Tool deleted successfully.')
        return redirect('agents:manage_tools')
    return render(request, 'agents/confirm_delete.html', {'object': tool, 'type': 'tool', 'page_title': 'Delete Tool'})

@login_required
@user_passes_test(is_admin)
def get_tool_info(request):
    tool_class = request.GET.get('tool_class')
    logger.info(f"Received request for tool_class: {tool_class}")
    
    if tool_class:
        try:
            tool_objects = get_tool_classes(tool_class)
            logger.debug(f"Found tool objects: {[obj.__name__ for obj in tool_objects]}")
            
            class_info = []
            for obj in tool_objects:
                description = get_tool_description(obj)
                logger.debug(f"Tool: {obj.__name__}, Description: {description}")
                class_info.append({
                    'name': obj.__name__,
                    'description': description
                })
            
            logger.debug(f"Returning class_info: {class_info}")
            return JsonResponse({
                'classes': class_info
            })
        except ImportError as e:
            logger.error(f"ImportError: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return JsonResponse({'error': f"Failed to import tool module: {str(e)}"}, status=500)
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return JsonResponse({'error': f"An unexpected error occurred: {str(e)}"}, status=500)
    
    logger.warning("Invalid request: tool_class parameter is missing")
    return JsonResponse({'error': 'Invalid request: tool_class parameter is missing'}, status=400)

@login_required
@user_passes_test(is_admin)
def get_tool_schema(request, tool_id):
    tool = get_object_or_404(Tool, id=tool_id)
    try:
        tool_class = get_tool_class_obj(tool.tool_class, tool.tool_subclass)

        if tool_class is None:
            return JsonResponse({'error': 'Failed to load tool class'}, status=400)

        manual_schema = {
            "type": "object",
            "properties": {}
        }

        if hasattr(tool_class, 'args_schema') and issubclass(tool_class.args_schema, BaseModel):
            # Use Pydantic v2 method if available
            if hasattr(tool_class.args_schema, 'model_json_schema'):
                schema = tool_class.args_schema.model_json_schema()
            else:
                # Fallback for Pydantic v1
                schema = tool_class.args_schema.schema()

            for field_name, field_schema in schema.get('properties', {}).items():
                manual_schema['properties'][field_name] = {
                    "type": field_schema.get('type', 'string'),
                    "title": field_schema.get('title', field_name.capitalize()),
                    "description": field_schema.get('description', '')
                }
        else:
            # Fallback for tools without args_schema
            for param_name, param in inspect.signature(tool_class._run).parameters.items():
                if param_name not in ['self', 'kwargs']:
                    manual_schema['properties'][param_name] = {
                        "type": "string",
                        "title": param_name.capitalize(),
                        "description": ""
                    }

        if not manual_schema["properties"]:
            logger.error(f"No input fields found for tool: {tool_class}")
            return JsonResponse({'error': 'No input fields found for this tool'}, status=400)

        logger.debug(f"Generated schema for tool {tool_id}: {manual_schema}")
        return JsonResponse(manual_schema)
    except Exception as e:
        logger.error(f"Error getting tool schema: {str(e)}")
        return JsonResponse({'error': f'Error getting tool schema: {str(e)}'}, status=500)

@login_required
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def test_tool(request, tool_id):
    """Run a tool test using Celery for both sync and async tools"""
    tool = get_object_or_404(Tool, id=tool_id)
    
    # Get inputs from request
    inputs = {key: value for key, value in request.POST.items() if key != 'csrfmiddlewaretoken'}
    
    try:
        # Start Celery task
        from .tasks.tools import run_tool
        task = run_tool.delay(tool_id, inputs)
        
        return JsonResponse({
            'status': 'started',
            'task_id': task.id,
            'message': f'Tool execution started. Task ID: {task.id}'
        })
        
    except Exception as e:
        logger.error(f"Error starting tool execution: {str(e)}\n{traceback.format_exc()}")
        return JsonResponse({
            'error': str(e)
        }, status=400)

@login_required
@user_passes_test(is_admin)
def get_tool_status(request, task_id):
    """Get the status of a tool execution"""
    from celery.result import AsyncResult
    
    task = AsyncResult(task_id)
    
    response = {
        'status': task.status,  # This will be one of: PENDING, STARTED, SUCCESS, FAILURE
    }
    
    if task.ready():
        if task.successful():
            try:
                result = task.get()
                if isinstance(result, dict):
                    response.update({
                        'result': result.get('result', ''),
                        'error': result.get('error')
                    })
                else:
                    response['result'] = str(result)
            except Exception as e:
                response.update({
                    'status': 'FAILURE',
                    'error': str(e)
                })
        else:
            response.update({
                'error': str(task.result)
            })
    
    return JsonResponse(response)
