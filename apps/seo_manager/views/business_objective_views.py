from datetime import datetime
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render
from ..models import Client
from ..forms import BusinessObjectiveForm
from apps.common.tools.user_activity_tool import user_activity_tool
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

@login_required
def add_business_objective(request, client_id):
    if request.method == 'POST':
        client = get_object_or_404(Client, id=client_id)
        form = BusinessObjectiveForm(request.POST)
        
        if form.is_valid():
            new_objective = {
                'goal': form.cleaned_data['goal'],
                'metric': form.cleaned_data['metric'],
                'target_date': form.cleaned_data['target_date'].isoformat(),
                'status': form.cleaned_data['status'],
                'date_created': datetime.now().isoformat(),
                'date_last_modified': datetime.now().isoformat(),
            }
            
            if not client.business_objectives:
                client.business_objectives = []
            
            client.business_objectives.append(new_objective)
            client.save()
            
            user_activity_tool.run(
                request.user, 
                'create', 
                f"Added business objective for client: {client.name}", 
                client=client,
                details=new_objective
            )
            
            messages.success(request, "Business objective added successfully.")
        else:
            messages.error(request, "Error adding business objective. Please check the form.")
            
    return redirect('seo_manager:client_detail', client_id=client_id)

@login_required
def edit_business_objective(request, client_id, objective_index):
    client = get_object_or_404(Client, id=client_id)
    
    if request.method == 'POST':
        form = BusinessObjectiveForm(request.POST)
        if form.is_valid():
            updated_objective = {
                'goal': form.cleaned_data['goal'],
                'metric': form.cleaned_data['metric'],
                'target_date': form.cleaned_data['target_date'].isoformat(),
                'status': form.cleaned_data['status'],
                'date_created': client.business_objectives[objective_index]['date_created'],
                'date_last_modified': datetime.now().isoformat(),
            }
            client.business_objectives[objective_index] = updated_objective
            client.save()
            user_activity_tool.run(request.user, 'update', f"Updated business objective for client: {client.name}", client=client, details=updated_objective)
            messages.success(request, "Business objective updated successfully.")
            return redirect('seo_manager:client_detail', client_id=client.id)
    else:
        objective = client.business_objectives[objective_index]
        initial_data = {
            'goal': objective['goal'],
            'metric': objective['metric'],
            'target_date': datetime.fromisoformat(objective['target_date']),
            'status': objective['status'],
        }
        form = BusinessObjectiveForm(initial=initial_data)
    
    context = {
        'page_title': 'Edit Business Objective',
        'client': client,
        'form': form,
        'objective_index': objective_index,
    }
    
    return render(request, 'seo_manager/edit_business_objective.html', context)

@login_required
def delete_business_objective(request, client_id, objective_index):
    if request.method == 'POST':
        client = get_object_or_404(Client, id=client_id)
        deleted_objective = client.business_objectives.pop(objective_index)
        client.save()
        user_activity_tool.run(request.user, 'delete', f"Deleted business objective for client: {client.name}", client=client, details=deleted_objective)
        messages.success(request, "Business objective deleted successfully.")
    return redirect('seo_manager:client_detail', client_id=client_id)

@require_http_methods(["POST"])
def update_objective_status(request, client_id, objective_index):
    try:
        client = Client.objects.get(id=client_id)
        data = json.loads(request.body)
        new_status = data.get('status')
        
        # Get the objectives list
        objectives = client.business_objectives
        
        # Update the status of the specific objective
        if 0 <= objective_index < len(objectives):
            objectives[objective_index]['status'] = new_status == 'active'
            
            # Update the last modified date
            objectives[objective_index]['date_last_modified'] = datetime.now().isoformat()
            
            # Save the updated objectives
            client.business_objectives = objectives
            client.save()
            
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'success': False, 'error': 'Objective not found'})
            
    except Client.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Client not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
