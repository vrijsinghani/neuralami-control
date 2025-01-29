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
    context = {
        'object': agent,
        'type': 'agent',
        'page_title': 'Delete Agent',
    }
    return render(request, 'agents/confirm_delete.html', context)

@login_required
@user_passes_test(is_admin)
def duplicate_agent(request, agent_id):
    original_agent = get_object_or_404(Agent, id=agent_id)
    if request.method == 'POST':
        try:
            # Get all field values except id and auto-generated fields
            field_values = {
                field.name: getattr(original_agent, field.name)
                for field in original_agent._meta.fields
                if not field.primary_key and not field.auto_created
            }
            
            # Modify the name for the copy
            field_values['name'] = f"{field_values['name']} (Copy)"
            
            # Create new agent with copied values
            new_agent = Agent.objects.create(**field_values)
            
            # Copy many-to-many relationships
            for field in original_agent._meta.many_to_many:
                getattr(new_agent, field.name).set(getattr(original_agent, field.name).all())
            
            # Copy tool settings
            for tool_setting in original_agent.tool_settings.all():
                AgentToolSettings.objects.create(
                    agent=new_agent,
                    tool=tool_setting.tool,
                    force_output_as_result=tool_setting.force_output_as_result
                )
            
            messages.success(request, 'Agent duplicated successfully.')
            
            # Check for next URL in POST data first, then GET, then fall back to referer
            next_url = request.POST.get('next') or request.GET.get('next')
            if next_url:
                return redirect(next_url)
            
            # If no next parameter, check the referer
            referer = request.META.get('HTTP_REFERER', '')
            if 'card-view' in referer:
                return redirect('agents:manage_agents_card_view')
            return redirect('agents:manage_agents')
            
        except Exception as e:
            logger.error(f"Error duplicating agent: {str(e)}\n{traceback.format_exc()}")
            messages.error(request, f"Error duplicating agent: {str(e)}")
            # Check for next URL in POST data first, then GET, then fall back to referer
            next_url = request.POST.get('next') or request.GET.get('next')
            if next_url:
                return redirect(next_url)
            
            # If no next parameter, check the referer
            referer = request.META.get('HTTP_REFERER', '')
            if 'card-view' in referer:
                return redirect('agents:manage_agents_card_view')
            return redirect('agents:manage_agents')
            
    return redirect('agents:manage_agents')