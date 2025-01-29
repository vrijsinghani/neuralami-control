import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from .models import Task
from .forms import TaskForm
import traceback

logger = logging.getLogger(__name__)

def is_admin(user):
    return user.is_staff or user.is_superuser

@login_required
@user_passes_test(is_admin)
def manage_tasks(request):
    tasks = Task.objects.all().order_by('description')
    # Add page_title to the context
    context = {
        'tasks': tasks,
        'page_title': 'Manage Tasks',
    }
    return render(request, 'agents/manage_tasks.html', context)

@login_required
@user_passes_test(is_admin)
def add_task(request):
    if request.method == 'POST':
        form = TaskForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Task added successfully.')
            return redirect('agents:manage_tasks')
    else:
        form = TaskForm()
    # Add page_title to the context
    context = {
        'form': form,
        'page_title': 'Add Task',
    }
    return render(request, 'agents/task_form.html', context)

@login_required
@user_passes_test(is_admin)
def edit_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    if request.method == 'POST':
        form = TaskForm(request.POST, instance=task)
        if form.is_valid():
            form.save()
            messages.success(request, 'Task updated successfully.')
            return redirect('agents:manage_tasks')
    else:
        form = TaskForm(instance=task)
    # Add page_title to the context
    context = {
        'form': form,
        'task': task,
        'page_title': 'Edit Task',
    }
    return render(request, 'agents/task_form.html', context)

@login_required
@user_passes_test(is_admin)
def delete_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    if request.method == 'POST':
        task.delete()
        messages.success(request, 'Task deleted successfully.')
        return redirect('agents:manage_tasks')
    context = {
        'object': task,
        'type': 'task',
        'page_title': 'Delete Task',
    }
    return render(request, 'agents/confirm_delete.html', context)

@login_required
@user_passes_test(is_admin)
def duplicate_task(request, task_id):
    original_task = get_object_or_404(Task, id=task_id)
    if request.method == 'POST':
        try:
            # Get all field values except id and auto-generated fields
            field_values = {
                field.name: getattr(original_task, field.name)
                for field in original_task._meta.fields
                if not field.primary_key and not field.auto_created
            }
            
            # Modify the description for the copy
            field_values['description'] = f"{field_values['description']} (Copy)"
            
            # Create new task with copied values
            new_task = Task.objects.create(**field_values)
            
            # Copy many-to-many relationships if any
            for field in original_task._meta.many_to_many:
                getattr(new_task, field.name).set(getattr(original_task, field.name).all())
            
            messages.success(request, 'Task duplicated successfully.')
            
            # Check for next URL in POST data first, then GET
            next_url = request.POST.get('next') or request.GET.get('next')
            if next_url:
                return redirect(next_url)
            return redirect('agents:manage_tasks')
            
        except Exception as e:
            logger.error(f"Error duplicating task: {str(e)}\n{traceback.format_exc()}")
            messages.error(request, f"Error duplicating task: {str(e)}")
            next_url = request.POST.get('next') or request.GET.get('next')
            if next_url:
                return redirect(next_url)
            return redirect('agents:manage_tasks')
            
    return redirect('agents:manage_tasks')