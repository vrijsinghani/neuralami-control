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
        #logger.debug(f"POST data: {request.POST}")
        if form.is_valid():
            tool = form.save(commit=False)
            tool_class = form.cleaned_data['tool_class']
            tool_subclass = form.cleaned_data['tool_subclass']
            
            #logger.debug(f"Adding tool: class={tool_class}, subclass={tool_subclass}")
            
            # Get the tool class object and its description
            tool_classes = get_tool_classes(tool_class)
            #logger.debug(f"Available tool classes: {[cls.__name__ for cls in tool_classes]}")
            if tool_classes:
                tool_class_obj = next((cls for cls in tool_classes if cls.__name__ == tool_subclass), None)
                if tool_class_obj:
                    #logger.debug(f"Tool class object: {tool_class_obj}")
                    
                    tool.description = get_tool_description(tool_class_obj)
                    #logger.debug(f"Tool description: {tool.description}")
                    
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
            #logger.debug(f"Found tool objects: {[obj.__name__ for obj in tool_objects]}")
            
            class_info = []
            for obj in tool_objects:
                description = get_tool_description(obj)
                #logger.debug(f"Tool: {obj.__name__}, Description: {description}")
                class_info.append({
                    'name': obj.__name__,
                    'description': description
                })
            
            #logger.debug(f"Returning class_info: {class_info}")
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
        
        
        manual_schema = {
            "type": "object",
            "properties": {}
        }

        # Access schema through Pydantic's model fields
        if hasattr(tool_class, 'model_fields') and 'args_schema' in tool_class.model_fields:
            
            schema_class = tool_class.model_fields['args_schema'].default
            
            if issubclass(schema_class, BaseModel):
                # Use Pydantic v2 method if available
                if hasattr(schema_class, 'model_json_schema'):
                    schema = schema_class.model_json_schema()
                else:
                    schema = schema_class.schema()
                
                for field_name, field_info in schema.get('properties', {}).items():
                    manual_schema['properties'][field_name] = {
                        "type": field_info.get('type', 'string'),
                        "title": field_info.get('title', field_name.capitalize()),
                        "description": field_info.get('description', '')
                    }

        if not manual_schema["properties"]:
            logger.warning("No properties found in schema")
            return JsonResponse({'error': 'No input fields found for this tool'}, status=400)

        return JsonResponse(manual_schema)
    except Exception as e:
        logger.error(f"Schema error: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@user_passes_test(is_admin)
def get_clients(request):
    """Get a list of clients for the tool testing form using organization context"""
    try:
        from apps.seo_manager.models import Client
        
        # First try to get organization from request
        organization = getattr(request, 'organization', None)
        
        # If not found, try to get from session
        if not organization and 'active_organization_id' in request.session:
            from django.apps import apps
            Organization = apps.get_model('organizations', 'Organization')
            try:
                organization = Organization.objects.get(id=request.session['active_organization_id'])
            except Exception as e:
                logger.warning(f"Failed to get organization from session: {e}")
        
        # If still not found, try to get the user's primary organization
        if not organization:
            from django.apps import apps
            OrganizationMembership = apps.get_model('organizations', 'OrganizationMembership')
            try:
                # Get the first active membership
                membership = OrganizationMembership.objects.filter(
                    user=request.user, 
                    status='active'
                ).select_related('organization').first()
                
                if membership:
                    organization = membership.organization
            except Exception as e:
                logger.warning(f"Failed to get user's organization membership: {e}")
        
        # If we still don't have an organization, fail with a clear message
        if not organization:
            logger.warning("No organization context found when fetching clients")
            return JsonResponse({
                'error': 'No active organization found. Please select an organization from the dropdown in the navigation bar.'
            }, status=400)
        
        # Log the organization we're using
        logger.info(f"Using organization: {organization.name} (ID: {organization.id}) for client list")
        
        # Get clients for the current organization
        clients = Client.objects.filter(organization=organization).values('id', 'name', 'website_url')
        clients_list = list(clients)
        
        # Log the number of clients found
        logger.info(f"Found {len(clients_list)} clients for organization {organization.name}")
        
        return JsonResponse(clients_list, safe=False)
    except Exception as e:
        logger.error(f"Error getting clients: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@user_passes_test(is_admin)
def get_client_attributes(request, client_id):
    """Get client attributes needed for tools, respecting organization context"""
    try:
        from apps.seo_manager.models import Client
        
        # First try to get organization from request
        organization = getattr(request, 'organization', None)
        
        # If not found, try to get from session
        if not organization and 'active_organization_id' in request.session:
            from django.apps import apps
            Organization = apps.get_model('organizations', 'Organization')
            try:
                organization = Organization.objects.get(id=request.session['active_organization_id'])
            except Exception as e:
                logger.warning(f"Failed to get organization from session: {e}")
        
        # If still not found, try to get the user's primary organization
        if not organization:
            from django.apps import apps
            OrganizationMembership = apps.get_model('organizations', 'OrganizationMembership')
            try:
                # Get the first active membership
                membership = OrganizationMembership.objects.filter(
                    user=request.user, 
                    status='active'
                ).select_related('organization').first()
                
                if membership:
                    organization = membership.organization
            except Exception as e:
                logger.warning(f"Failed to get user's organization membership: {e}")
        
        # If we still don't have an organization, fail with a clear message
        if not organization:
            logger.warning("No organization context found when fetching client attributes")
            return JsonResponse({
                'error': 'No active organization found. Please select an organization from the dropdown in the navigation bar.'
            }, status=400)
        
        # Log the organization we're using
        logger.info(f"Using organization: {organization.name} (ID: {organization.id}) for client attributes")
        
        # Get the client, ensuring it belongs to the current organization
        client = get_object_or_404(Client, id=client_id, organization=organization)
        
        # Begin with basic client information
        client_attributes = {
            'client_id': str(client.id),
            'client_name': client.name,
            'website_url': client.website_url,
        }
        
        # Add flags for available related models
        has_models = {}
        
        # Function to safely get attributes from a model instance
        def get_safe_model_attributes(model_instance, exclude_fields=None):
            if not model_instance:
                return {}
                
            if exclude_fields is None:
                exclude_fields = ['_state']
                
            # Try to convert the model to a dictionary
            model_dict = {}
            
            try:
                # First try model's to_dict method if it exists
                if hasattr(model_instance, 'to_dict') and callable(getattr(model_instance, 'to_dict')):
                    model_dict = model_instance.to_dict()
                # Otherwise use the model's fields
                else:
                    for field in model_instance._meta.fields:
                        field_name = field.name
                        if field_name not in exclude_fields:
                            model_dict[field_name] = getattr(model_instance, field_name)
                            
                # Handle special serialization cases
                safe_dict = {}
                for key, value in model_dict.items():
                    # Skip None values
                    if value is None:
                        safe_dict[key] = None
                        continue
                        
                    # Convert datetime objects to isoformat strings
                    if hasattr(value, 'isoformat'):
                        safe_dict[key] = value.isoformat()
                    # Convert UUID objects to strings
                    elif hasattr(value, 'hex'):
                        safe_dict[key] = str(value)
                    # Convert model instances to their ID or string representation
                    elif hasattr(value, '_meta') and hasattr(value, 'pk'):
                        # This is likely a Django model instance
                        safe_dict[key] = str(value.pk)
                    # Convert binary data to base64
                    elif isinstance(value, bytes):
                        import base64
                        safe_dict[key] = base64.b64encode(value).decode('utf-8')
                    # Handle querysets
                    elif hasattr(value, 'all') and callable(getattr(value, 'all')):
                        # Skip querysets/managers to prevent recursion
                        continue
                    # Handle any other types that might be serializable
                    else:
                        try:
                            # Test if it's JSON serializable
                            json.dumps(value)
                            safe_dict[key] = value
                        except (TypeError, OverflowError):
                            # If not serializable, use string representation
                            safe_dict[key] = str(value)
                
                # Replace model_dict with the sanitized version
                model_dict = safe_dict
                
                # Add any accessor methods that return useful data
                if hasattr(model_instance, 'get_property_id') and callable(getattr(model_instance, 'get_property_id')):
                    try:
                        property_id = model_instance.get_property_id()
                        # Make sure it's serializable
                        model_dict['property_id'] = str(property_id) if property_id is not None else None
                    except Exception as e:
                        logger.warning(f"Failed to get property_id: {e}")
                        
                if hasattr(model_instance, 'get_property_url') and callable(getattr(model_instance, 'get_property_url')):
                    try:
                        property_url = model_instance.get_property_url()
                        # Make sure it's serializable
                        model_dict['property_url'] = str(property_url) if property_url is not None else None
                    except Exception as e:
                        logger.warning(f"Failed to get property_url: {e}")
                
                return model_dict
            except Exception as e:
                logger.warning(f"Failed to convert model to dictionary: {e}")
                return {}
        
        # Handle Google Analytics credentials
        if hasattr(client, 'ga_credentials') and client.ga_credentials:
            has_models['has_analytics'] = True
            ga_creds = get_safe_model_attributes(client.ga_credentials)
            if ga_creds:
                client_attributes['analytics_credentials'] = ga_creds
                # Try to extract a property ID if not already included
                if 'property_id' in ga_creds:
                    client_attributes['analytics_property_id'] = ga_creds['property_id']
                elif 'view_id' in ga_creds:  # Fallback for older GA3 structure
                    client_attributes['analytics_property_id'] = ga_creds['view_id']
        else:
            has_models['has_analytics'] = False
        
        # Handle Search Console credentials
        if hasattr(client, 'sc_credentials') and client.sc_credentials:
            has_models['has_search_console'] = True
            sc_creds = get_safe_model_attributes(client.sc_credentials)
            if sc_creds:
                client_attributes['search_console_credentials'] = sc_creds
                # Try to extract a property URL if not already included
                if 'property_url' in sc_creds:
                    client_attributes['search_console_property_url'] = sc_creds['property_url']
                elif 'property_id' in sc_creds:  # Alternative property identifier
                    client_attributes['search_console_property_url'] = sc_creds['property_id']
        else:
            has_models['has_search_console'] = False
        
        # Handle targeted keywords - get only fields that exist
        if hasattr(client, 'targeted_keywords'):
            try:
                # First check which fields exist
                keyword_fields = [f.name for f in client.targeted_keywords.model._meta.fields 
                                if f.name not in ['id', 'client', 'client_id']]
                
                # Always include id
                keyword_fields = ['id'] + keyword_fields
                
                # Get keywords with available fields
                keywords = list(client.targeted_keywords.all().values(*keyword_fields))
                
                if keywords:
                    client_attributes['targeted_keywords'] = keywords
                    has_models['has_targeted_keywords'] = True
                    logger.info(f"Added {len(keywords)} targeted keywords with fields: {keyword_fields}")
                else:
                    has_models['has_targeted_keywords'] = False
            except Exception as e:
                logger.warning(f"Failed to fetch targeted keywords: {e}")
                has_models['has_targeted_keywords'] = False
        else:
            has_models['has_targeted_keywords'] = False
        
        # Add availability flags to the response
        client_attributes.update(has_models)
        
        return JsonResponse(client_attributes)
        
    except Exception as e:
        logger.error(f"Error getting client attributes: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@user_passes_test(is_admin)
@require_http_methods(["POST"])
def test_tool(request, tool_id):
    """Run a tool test using Celery for both sync and async tools"""
    logger.debug(f"Starting test_tool for tool_id: {tool_id}")
    tool = get_object_or_404(Tool, id=tool_id)
    logger.debug(f"Found tool: {tool.name}")
    
    # Get inputs from request
    inputs = {key: value for key, value in request.POST.items() if key != 'csrfmiddlewaretoken'}
    #logger.debug(f"Tool inputs: {inputs}")
    
    # Check if this is a tool that uses client attributes
    client_attributes_json = inputs.pop('client_attributes', None)
    
    # If we have client attributes JSON, parse and use those instead of client_id
    if client_attributes_json:
        try:
            client_attributes = json.loads(client_attributes_json)
            # Always remove client_id as it's not needed with the new multi-tenancy approach
            inputs.pop('client_id', None)
            if 'client_id' in client_attributes:
                del client_attributes['client_id']
            
            # Add relevant attributes to inputs
            for key, value in client_attributes.items():
                # Skip metadata flags and unnecessary fields
                if key.startswith('has_') or key == 'client_id':
                    continue
                # Add the attribute to the inputs
                inputs[key] = value
                
            #logger.debug(f"Added client attributes to inputs: {list(client_attributes.keys())}")
        except json.JSONDecodeError:
            logger.error("Failed to parse client attributes JSON")
    
    # Ensure all complex inputs are converted to JSON strings and types are correct
    # This is required because the Celery task expects all values to be either 
    # simple types or JSON strings that it can parse with json.loads()
    serialized_inputs = {}
    for key, value in inputs.items():
        # Always remove client_id
        if key == 'client_id':
            continue
            
        # Ensure specific fields are strings
        if key == 'analytics_property_id' and value is not None:
            serialized_inputs[key] = str(value)
            logger.debug(f"Converted {key} to string: {value}")
            
        # Convert dictionaries and lists to JSON strings
        elif isinstance(value, (dict, list)):
            try:
                serialized_inputs[key] = json.dumps(value)
                logger.debug(f"Serialized complex input: {key}")
            except (TypeError, ValueError) as e:
                logger.error(f"Failed to serialize {key}: {e}")
                # Fallback to string representation
                serialized_inputs[key] = str(value)
        else:
            # Keep simple values as they are
            serialized_inputs[key] = value
    
    # Log the final inputs being sent to the task
    logger.debug(f"Final serialized inputs: {list(serialized_inputs.keys())}")
    
    try:
        # Import and verify Celery app configuration
        from celery import current_app
        
        # Start Celery task with serialized inputs
        from .tasks.tools import run_tool
        task = run_tool.delay(tool_id, serialized_inputs)
        logger.debug(f"Task queued successfully with ID: {task.id}")
        
        return JsonResponse({
            'status': 'started',
            'task_id': task.id,
            'message': f'Tool execution started. Task ID: {task.id}'
        })
        
    except Exception as e:
        logger.error(f"Error starting tool execution: {str(e)}", exc_info=True)
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
        'status': task.status,
        'token_count': 0
    }
    
    # Get task meta information
    if task.status in ['PENDING', 'STARTED', 'PROGRESS']:
        # Try to get state meta information from different possible sources
        meta = None
        if hasattr(task, 'info') and task.info:
            meta = task.info
        elif hasattr(task, 'result') and isinstance(task.result, dict):
            meta = task.result
        elif task.backend and hasattr(task.backend, 'get_task_meta'):
            try:
                meta = task.backend.get_task_meta(task_id)
                if 'result' in meta and isinstance(meta['result'], dict):
                    meta = meta['result']
            except Exception as e:
                logger.warning(f"Failed to get task meta: {e}")
        
        if meta:
            # Include all meta information
            if isinstance(meta, dict):
                response.update(meta)
            #logger.debug(f"Task meta information: {meta}")
    
    if task.ready():
        if task.successful():
            try:
                result = task.get()
                #logger.debug(f"Raw task result: {result} (Type: {type(result)})")
                
                # Preserve existing response structure
                if isinstance(result, dict):
                    response.update({
                        'result': result.get('result', ''),
                        'error': result.get('error')
                    })
                else:
                    response['result'] = str(result)
                
                # Calculate tokens from the original result
                if isinstance(result, (dict, list)):
                    output_text = json.dumps(result, indent=2)
                else:
                    output_text = str(result)
                
                #logger.debug(f"Formatted output text for token counting: {output_text[:200]}...")  # Log first 200 chars
                token_count = count_tokens(output_text)
                #logger.debug(f"Calculated token count: {token_count}")
                response['token_count'] = token_count
                
            except Exception as e:
                logger.error(f"Error processing task result: {str(e)}")
                response.update({
                    'status': 'FAILURE',
                    'error': str(e)
                })
        else:
            logger.error(f"Task failed: {task.result}")
            response.update({
                'error': str(task.result)
            })
    
    #logger.debug(f"Returning status response: {response}")
    return JsonResponse(response)
