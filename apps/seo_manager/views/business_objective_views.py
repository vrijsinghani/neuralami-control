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

@login_required
def update_objective_status(request, client_id, objective_index):
    if request.method == 'POST':
        try:
            client = get_object_or_404(Client, id=client_id)
            data = json.loads(request.body)
            new_status = data.get('status')
            
            if objective_index < len(client.business_objectives):
                objective = client.business_objectives[objective_index]
                old_status = objective['status']
                objective['status'] = new_status
                client.save()
                
                # Log the activity
                user_activity_tool.run(
                    request.user,
                    'update',
                    f"Updated objective status from {old_status} to {new_status}",
                    client=client
                )
                
                return JsonResponse({
                    'success': True,
                    'message': 'Objective status updated successfully'
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'Objective not found'
                }, status=404)
                
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)
            
    return JsonResponse({
        'success': False,
        'error': 'Invalid request method'
    }, status=405)
