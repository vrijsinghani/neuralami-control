"""
Admin interface for common app models.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Sum
from django.http import JsonResponse, StreamingHttpResponse
from django.urls import path
from django.shortcuts import render
from asgiref.sync import async_to_sync
import json
import logging
from django.utils import timezone

from .models import LLMConfiguration, TokenUsage, LLMTestHarnessModel

logger = logging.getLogger(__name__)


@admin.register(LLMConfiguration)
class LLMConfigurationAdmin(admin.ModelAdmin):
    """Admin interface for LLM configurations."""
    
    list_display = [
        'name',
        'provider_type',
        'default_model',
        'updated_at'
    ]
    list_filter = [
        'provider_type',
        'created_at'
    ]
    search_fields = ['name', 'description', 'default_model']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = [
        (None, {
            'fields': [
                'name',
                'description'
            ]
        }),
        ('Provider Configuration', {
            'fields': [
                'provider_type',
                'fallback_provider',
                'api_key',
                'api_key_secondary',
                'organization_id'
            ]
        }),
        ('Model Settings', {
            'fields': [
                'default_model',
                'model_parameters'
            ]
        }),
        ('Rate Limiting', {
            'fields': [
                'requests_per_minute',
                'tokens_per_minute'
            ]
        }),
        ('Caching', {
            'fields': [
                'enable_response_cache',
                'response_cache_ttl',
                'enable_model_cache',
                'model_cache_ttl'
            ]
        }),
        ('Advanced Settings', {
            'fields': [
                'provider_settings',
                'streaming_config'
            ],
            'classes': ['collapse']
        })
    ]

@admin.register(TokenUsage)
class TokenUsageAdmin(admin.ModelAdmin):
    list_display = ('user', 'model', 'prompt_tokens', 'completion_tokens', 'total_cost', 'timestamp', 'request_type')
    list_filter = ('model', 'request_type', 'provider_type', 'timestamp')
    search_fields = ('user__username', 'model', 'session_id')
    readonly_fields = ('timestamp',)

@admin.register(LLMTestHarnessModel)
class LLMTestHarnessAdmin(admin.ModelAdmin):
    """Admin interface for testing LLM providers."""
    
    change_list_template = 'admin/common/llm_test_harness.html'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('llmtestharnessmodel/models/', self.get_models_view, name='common_llmtestharnessmodel_llm-models'),
            path('llmtestharnessmodel/completion/', self.test_completion_view, name='common_llmtestharnessmodel_llm-test-completion'),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        """Override to redirect to test harness view."""
        return self.test_harness_view(request)

    def test_harness_view(self, request):
        # Get available configurations
        configs = LLMConfiguration.objects.all()
        
        # Serialize configs for JavaScript
        configs_data = [
            {
                'id': config.id,
                'provider_type': config.provider_type,
                'provider_display': config.get_provider_type_display(),
                'default_model': config.default_model
            }
            for config in configs
        ]
        
        context = {
            'configs': json.dumps(configs_data),  # For JavaScript
            'configs_list': configs_data,         # For template rendering
            'title': 'LLM Test Harness',
            'opts': self.model._meta,
            'is_nav_sidebar_enabled': True,
            'available_apps': self.admin_site.get_app_list(request),
            'has_permission': self.has_module_permission(request),
            'timestamp': timezone.now(),  # Add current timestamp
        }
        return render(request, 'admin/common/llm_test_harness.html', context)

    def test_completion_view(self, request):
        """Synchronous wrapper for async test_completion."""
        return async_to_sync(self._test_completion)(request)

    async def _test_completion(self, request):
        """Async implementation of test completion."""
        try:
            from .services.llm_service import LLMService
            
            # Parse JSON data from request
            data = json.loads(request.body)
            
            # Get parameters from request
            provider_type = data.get('provider_type')
            model = data.get('model')
            messages = data.get('messages', [])
            temperature = float(data.get('temperature', 0.7))
            max_tokens = int(data.get('max_tokens', 1000))
            stream = data.get('stream', False)
            
            # Initialize service
            service = LLMService(user=request.user)
            
            # Get completion
            if stream:
                # Return streaming response
                async def stream_response():
                    async for chunk in service.get_streaming_completion(
                        messages=messages,
                        provider_type=provider_type,
                        model_name=model,
                        temperature=temperature,
                        max_tokens=max_tokens
                    ):
                        yield chunk
                
                # Create a synchronous wrapper for the asynchronous generator
                from asgiref.sync import async_to_sync
                
                def sync_stream_generator():
                    # Get event loop or create one
                    import asyncio
                    loop = asyncio.get_event_loop()
                    # Create the asynchronous generator
                    agen = stream_response().__aiter__()
                    # Keep getting values until StopAsyncIteration
                    try:
                        while True:
                            # Run the coroutine in the event loop
                            yield loop.run_until_complete(agen.__anext__())
                    except StopAsyncIteration:
                        pass
                
                response = StreamingHttpResponse(
                    sync_stream_generator(),
                    content_type='text/event-stream'
                )
                response['Cache-Control'] = 'no-cache'
                return response
            else:
                # Return regular response
                completion, metadata = await service.get_completion(
                    messages=messages,
                    provider_type=provider_type,
                    model_name=model,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                return JsonResponse({
                    'completion': completion,
                    'metadata': metadata
                })
                
        except Exception as e:
            logger.error(f"Error in test completion: {str(e)}", exc_info=True)
            return JsonResponse({
                'error': str(e)
            }, status=500)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return True

    def has_module_permission(self, request):
        return True

    def get_models_view(self, request):
        """Synchronous wrapper for async get_models."""
        return async_to_sync(self._get_models)(request)

    async def _get_models(self, request):
        """Async implementation of get_models."""
        try:
            from .services.llm_service import LLMService
            
            provider_type = request.GET.get('provider')
            if not provider_type:
                return JsonResponse({'error': 'Provider type is required'}, status=400)
            
            service = LLMService(user=request.user)
            try:
                models = await service.get_available_models(provider_type)
            except Exception as e:
                logger.error(f"Error getting models from provider {provider_type}: {str(e)}")
                return JsonResponse({'error': str(e)}, status=500)
            
            # Format models for frontend dropdown
            formatted_models = {}
            if not models:
                logger.error(f"No models returned from provider {provider_type}")
                return JsonResponse({'error': 'No models available for this provider'}, status=404)
                
            for model_id, model_info in models.items():
                formatted_models[model_id] = {
                    'name': model_info.get('name', model_id),
                    'description': model_info.get('description', ''),
                    'context_window': model_info.get('context_window'),
                    'input_tokens': model_info.get('input_tokens'),
                    'output_tokens': model_info.get('output_tokens'),
                    'supports_vision': model_info.get('supports_vision', False),
                    'supports_json': model_info.get('supports_json', False),
                    'supports_functions': model_info.get('supports_functions', False)
                }
            
            if not formatted_models:
                logger.error(f"No formatted models for provider {provider_type}")
                return JsonResponse({'error': 'No models available for this provider'}, status=404)
            
            return JsonResponse(formatted_models)
            
        except Exception as e:
            logger.error(f"Error in _get_models: {str(e)}", exc_info=True)
            return JsonResponse({'error': str(e)}, status=500)
