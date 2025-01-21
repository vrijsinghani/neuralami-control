import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from .models import Agent, AgentToolSettings
from .forms import AgentForm
import traceback
from django.conf import settings

logger = logging.getLogger(__name__)

def is_admin(user):
    return user.is_staff or user.is_superuser

@login_required
@user_passes_test(is_admin)
def manage_agents(request):
    agents = Agent.objects.all().order_by('name')
    return render(request, 'agents/manage_agents.html', {'agents': agents})

@login_required
def manage_agents_card_view(request):
    agents = Agent.objects.prefetch_related('crew_set', 'task_set', 'tools').all().order_by('name')
    form = AgentForm()  # Now AgentForm is defined
    context = {
        'page_title': 'Manage Agents',
        'agents': agents,
        'form': form,
    }
    return render(request, 'agents/manage_agents_card_view.html', context)

@login_required
@user_passes_test(is_admin)
def add_agent(request):
    if request.method == 'POST':
        form = AgentForm(request.POST)
        if form.is_valid():
            try:
                agent = form.save(commit=False)
                agent.avatar = form.cleaned_data['avatar']
                agent.save()
                
                # Save many-to-many fields
                form.save_m2m()
                
                # Handle tool settings
                for tool in agent.tools.all():
                    force_output = request.POST.get(f'force_tool_output_{tool.id}') == 'on'
                    AgentToolSettings.objects.create(
                        agent=agent,
                        tool=tool,
                        force_output_as_result=force_output
                    )
                
                messages.success(request, 'Agent added successfully.')
                return redirect('agents:manage_agents')
            except Exception as e:
                messages.error(request, f"Error adding agent: {str(e)}")
    else:
        form = AgentForm()

    # Add page_title to the context
    context = {
        'form': form,
        'page_title': 'Add Agent',
    }
    return render(request, 'agents/agent_form.html', context)

@login_required
@user_passes_test(is_admin)
def edit_agent(request, agent_id):
    agent = get_object_or_404(Agent, id=agent_id)
    if request.method == 'POST':
        form = AgentForm(request.POST, instance=agent)
        if form.is_valid():
            try:
                agent = form.save(commit=False)
                agent.avatar = form.cleaned_data['avatar']
                agent.save()
                form.save_m2m()
                
                # Update tool settings
                agent.tool_settings.all().delete()  # Remove existing settings
                for tool in agent.tools.all():
                    force_output = request.POST.get(f'force_tool_output_{tool.id}') == 'on'
                    AgentToolSettings.objects.create(
                        agent=agent,
                        tool=tool,
                        force_output_as_result=force_output
                    )
                
                messages.success(request, 'Agent updated successfully.')
                return redirect('agents:manage_agents_card_view')
            except Exception as e:
                messages.error(request, f"Error updating agent: {str(e)}")
    else:
        form = AgentForm(instance=agent)
    
    # Add page_title to the context
    context = {
        'form': form,
        'agent': agent,
        'page_title': 'Edit Agent',
    }
    
    return render(request, 'agents/agent_form.html', context)

@login_required
@user_passes_test(is_admin)
def delete_agent(request, agent_id):
    agent = get_object_or_404(Agent, id=agent_id)
    if request.method == 'POST':
        agent.delete()
        messages.success(request, 'Agent deleted successfully.')
        return redirect('agents:manage_agents')
    # Add page_title to the context
    context = {
        'object': agent,
        'type': 'agent',
        'page_title': 'Delete Agent',
    }
    return render(request, 'agents/confirm_delete.html', context)