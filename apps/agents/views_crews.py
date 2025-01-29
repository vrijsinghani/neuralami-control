# This file was previously named views_admin.py
# The content remains the same, but you might want to remove any unused imports

import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from .models import Crew, CrewTask
from .forms import CrewForm
import json
from apps.seo_manager.models import Client
from django.conf import settings

logger = logging.getLogger(__name__)

def is_admin(user):
    return user.is_staff or user.is_superuser

@login_required
@user_passes_test(is_admin)
def manage_crews(request):
    crews = Crew.objects.all().order_by('name')
    
    # Get the selected client_id from the session
    selected_client_id = request.session.get('selected_client_id')
    selected_client = None
    
    if selected_client_id:
        selected_client = get_object_or_404(Client, id=selected_client_id)
        # Optionally, you can filter crews by the selected client if there's a relationship
        # crews = crews.filter(client=selected_client)
    
    context = {
        'page_title': 'Manage Crews',
        'crews': crews,
        'selected_client': selected_client,
    }
    return render(request, 'agents/manage_crews.html', context)

@login_required
@user_passes_test(is_admin)
def add_crew(request):
    if request.method == 'POST':
        form = CrewForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Crew added successfully.')
            return redirect('agents:manage_crews')
    else:
        initial_data = {
            'manager_llm': settings.GENERAL_MODEL,
            'function_calling_llm': settings.GENERAL_MODEL
        }
        logger.debug(f"Initial data for form: {initial_data}")
        form = CrewForm(initial=initial_data)
    # Add page_title to the context
    context = {
        'form': form,
        'page_title': 'Add Crew',
    }
    return render(request, 'agents/crew_form.html', context)

@login_required
@user_passes_test(is_admin)
def edit_crew(request, crew_id):
    crew = get_object_or_404(Crew, id=crew_id)
    if request.method == 'POST':
        form = CrewForm(request.POST, instance=crew)
        if form.is_valid():
            form.save()
            messages.success(request, 'Crew updated successfully.')
            return redirect('agents:manage_crews')
    else:
        form = CrewForm(instance=crew, initial={
            'manager_llm': settings.GENERAL_MODEL,
            'function_calling_llm': settings.GENERAL_MODEL
        })
    # Add page_title to the context
    context = {
        'form': form,
        'crew': crew,
        'page_title': 'Edit Crew',
    }
    return render(request, 'agents/crew_form.html', context)

@login_required
@user_passes_test(is_admin)
def delete_crew(request, crew_id):
    crew = get_object_or_404(Crew, id=crew_id)
    if request.method == 'POST':
        crew.delete()
        messages.success(request, 'Crew deleted successfully.')
        return redirect('agents:manage_crews')
    # Add page_title to the context
    context = {
        'object': crew,
        'type': 'crew',
        'page_title': 'Delete Crew',
    }
    return render(request, 'agents/confirm_delete.html', context)

@login_required
@user_passes_test(is_admin)
def update_crew_agents(request, crew_id):
    crew = get_object_or_404(Crew, id=crew_id)
    if request.method == 'POST':
        agent_ids = request.POST.getlist('agents')
        crew.agents.set(agent_ids)
        
        # Update manager_agent if it's in the POST data
        manager_agent_id = request.POST.get('manager_agent')
        if manager_agent_id:
            crew.manager_agent_id = manager_agent_id
        else:
            crew.manager_agent = None
        
        crew.save()
        messages.success(request, 'Crew agents updated successfully.')
    return redirect('agents:manage_crews')

@login_required
@user_passes_test(is_admin)
def manage_crews_card_view(request):
    crews = Crew.objects.all().order_by('name')
    
    # Get the selected client_id from the session
    selected_client_id = request.session.get('selected_client_id')
    selected_client = None
    
    if selected_client_id:
        selected_client = get_object_or_404(Client, id=selected_client_id)
        # Optionally, you can filter crews by the selected client if there's a relationship
        # crews = crews.filter(client=selected_client)
    
    context = {
        'page_title': 'Manage Crews',
        'crews': crews,
        'selected_client': selected_client,
    }
    return render(request, 'agents/manage_crews_card_view.html', context)

@login_required
def crew_create_or_update(request, crew_id=None):
    if crew_id:
        crew = get_object_or_404(Crew, id=crew_id)
    else:
        crew = None

    next_url = request.GET.get('next') or request.POST.get('next')

    if request.method == 'POST':
        form = CrewForm(request.POST, instance=crew)
        if form.is_valid():
            crew = form.save(commit=False)
            
            # Handle input variables - ensure it's a proper JSON array
            input_variables = request.POST.getlist('input_variables[]')
            # Filter out empty strings and convert to list
            input_variables = [var.strip() for var in input_variables if var.strip()]
            # Store as JSON array
            crew.input_variables = input_variables if input_variables else []
            
            crew.save()
            form.save_m2m()  # This is important for saving many-to-many relationships
            
            # Handle task order
            task_order = request.POST.getlist('task_order[]')
            CrewTask.objects.filter(crew=crew).delete()
            for index, task_id in enumerate(task_order):
                CrewTask.objects.create(crew=crew, task_id=task_id, order=index)
            
            messages.success(request, f'Crew {"updated" if crew_id else "created"} successfully.')
            
            if next_url:
                return redirect(next_url)
            else:
                return redirect('agents:manage_crews')
        else:
            messages.error(request, f'Error {"updating" if crew_id else "creating"} crew. Please check the form.')
    else:
        form = CrewForm(instance=crew)
        input_variables = crew.input_variables if crew and crew.input_variables else []

    context = {
        'page_title': 'Create or Update Crew',
        'form': form,
        'crew': crew,
        'input_variables_json': json.dumps(input_variables if input_variables else []),
        'next': next_url,
    }

    return render(request, 'agents/crew_form.html', context)
