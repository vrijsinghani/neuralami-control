
from django.contrib.auth.models import User
from django.conf import settings

from apps.tasks.tasks import summarize_content
import mistune

from django.http import JsonResponse
from celery.result import AsyncResult
import logging
from apps.common.utils import get_models
from apps.common.tools.user_activity_tool import user_activity_tool  # Add this import

import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import SummarizerUsage



@login_required
def summarize_view(request):
  models = get_models()
  logging.info(f'request.user.id: {request.user.id}')
  model_selected = settings.SUMMARIZER
  
  if request.method == 'POST':
    text_to_summarize = request.POST.get('query_text_value')
    model_selected = request.POST.get('model_selected_value')
    task = summarize_content.delay(text_to_summarize, request.user.id, model_selected)
    
    # Log user activity
    user_activity_tool.run(
      user=request.user,
      category='summarize',
      action=f"Used summarizer with model: {model_selected}",
      details={"text_length": len(text_to_summarize)}
    )
    
    return JsonResponse({'task_id': task.id})
  
  user = User.objects.get(id=request.user.id)
  summarizations = SummarizerUsage.objects.filter(user=user).order_by('-created_at')
  
  for summ in summarizations:
    summ.html_result = mistune.html(summ.response + '\n\n---Detail---------\n\n'+summ.compressed_content)
    
  task_result = None
  task_status = None
  model_selected =  settings.SUMMARIZER
  context = {
    'task_result': task_result,
    'task_status': task_status,
    'summarizations': summarizations,
    'models': models,
    'model_selected': model_selected
  }
  
  # Log user activity for viewing summarize page
  user_activity_tool.run(
    user=request.user,
    category='view',
    action="Viewed summarize page"
  )
  
  return render(request, 'pages/apps/summarize.html', context)

def task_status(request, task_id):
    current_chunk = 0
    total_chunks = 1
    task_result = AsyncResult(task_id)
    if task_result.info is not None:
      if task_result.state == 'SUCCESS':
          result = task_result.result
          html_result = mistune.html(result)
          return JsonResponse({'status': 'SUCCESS', 'result': html_result})
      elif task_result.state == 'FAILURE':
          error = str(task_result.result)
          return JsonResponse({'status': 'FAILURE', 'result': error})
      elif task_result.status == 'processing':
          progress = task_result.info
          current_chunk = progress.get('current_chunk', 0)
          total_chunks = progress.get('total_chunks', 0)
          return JsonResponse({'status': task_result.status, 'current': current_chunk, 'total': total_chunks})
      else:
          if task_result.status:
              return JsonResponse({'status': task_result.status})
          else:
              return JsonResponse({'status': 'PENDING'})
    else:
        return JsonResponse({'status': 'PENDING'})