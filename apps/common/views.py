from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.contrib.admin.views.decorators import staff_member_required
from asgiref.sync import async_to_sync

from .services.llm_service import LLMService

# Create your views here.

@staff_member_required
@require_GET
def get_llm_models(request):
    """Get available models for a provider."""
    provider = request.GET.get('provider')
    if not provider:
        return JsonResponse({'error': 'Provider parameter is required'}, status=400)
    
    try:
        # Initialize service and get models
        service = LLMService()
        models = async_to_sync(service.get_available_models)(provider_type=provider)
        
        return JsonResponse(models.get(provider, {}))
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
