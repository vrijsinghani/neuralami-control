import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from .models import Task
from .forms import TaskForm

logger = logging.getLogger(__name__)

def is_admin(user):
    return user.is_staff or user.is_superuser

@login_required
@user_passes_test(is_admin)
def manage_tasks(request):
    tasks = Task.objects.all().order_by('description')
    return render(request, 'agents/manage_tasks.html', {'tasks': tasks})

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
    return render(request, 'agents/task_form.html', {'form': form})

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
    return render(request, 'agents/task_form.html', {'form': form, 'task': task})

@login_required
@user_passes_test(is_admin)
def delete_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    if request.method == 'POST':
        task.delete()
        messages.success(request, 'Task deleted successfully.')
        return redirect('agents:manage_tasks')
    return render(request, 'agents/confirm_delete.html', {'object': task, 'type': 'task'})