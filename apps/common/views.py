from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from asgiref.sync import async_to_sync

from .services.llm_service import LLMService

# Create your views here.

@require_GET
def get_llm_models(request):
    """Get available models for a provider."""
    provider = request.GET.get('provider')
    if not provider:
        return JsonResponse({'error': 'Provider parameter is required'}, status=400)
    
    try:
        # Initialize service and get models
        service = LLMService(user=request.user)
        models = async_to_sync(service.get_available_models)(provider_type=provider)
        
        if not models:
            return JsonResponse({'error': 'No models available for this provider'}, status=404)
            
        return JsonResponse(models)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
