"""OpenRouter API provider implementation."""

import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple, Union
import httpx

from django.conf import settings
from apps.common.models import LLMConfiguration
from .base import BaseLLMProvider

logger = logging.getLogger(__name__)

class OpenRouterProvider(BaseLLMProvider):
    """Direct OpenRouter API provider."""
    
    def __init__(self, config: LLMConfiguration):
        """Initialize OpenRouter provider with configuration."""
        super().__init__(config)
        
        # Get provider settings
        self.api_base = config.api_base_url
        self.api_version = config.api_version
        self.max_retries = config.max_retries
        
        # Initialize client with proper settings
        self.client = httpx.AsyncClient(
            base_url=self.api_base or "https://openrouter.ai/api/v1",
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "HTTP-Referer": settings.ALLOWED_HOSTS[0],  # Required by OpenRouter
                "X-Title": "NeuralAMI Control",  # Application name
                "Content-Type": "application/json"
            },
            timeout=config.timeout
        )
        
        # Get model parameters
        model_params = config.get_model_parameters()
        self.temperature = model_params.get('temperature', 0.7)
        self.max_tokens = model_params.get('max_tokens', 32767)
        
        # Set default model if not specified
        self.model_name = config.default_model or 'openai/gpt-3.5-turbo'
        
        # Cache settings
        self._cache_config = config.get_cache_config()
        self._rate_limits = config.get_rate_limits()
        self._streaming_config = config.get_streaming_config()
        
        # Initialize models cache
        self.available_models = {}
    
    async def initialize(self):
        """Initialize provider and fetch available models."""
        try:
            if self._cache_config['enable_model_cache']:
                # TODO: Check cache first
                pass
                
            self.available_models = await self._fetch_available_models()
            
            # Validate model name
            if self.model_name not in self.available_models:
                logger.warning(f"Model {self.model_name} not found, falling back to openai/gpt-3.5-turbo")
                self.model_name = 'openai/gpt-3.5-turbo'
            
            # Update max tokens based on model limits
            self.max_tokens = min(
                self.max_tokens,
                self.available_models[self.model_name]['max_output_tokens']
            )
            
            if self._cache_config['enable_model_cache']:
                # TODO: Cache the models
                pass
                
        except Exception as e:
            logger.error(f"Error initializing OpenRouter provider: {str(e)}")
            raise
    
    async def get_completion(
        self,
        messages: list,
        stream: bool = False,
        **kwargs
    ) -> Union[Tuple[str, dict], AsyncGenerator[Any, None]]:
        """Get completion using OpenRouter API."""
        try:
            # Get model parameters with overrides
            model_params = self.config.get_model_parameters(
                kwargs.get('model_name', self.model_name)
            )
            
            # Get streaming config if needed
            stream_config = self._streaming_config if stream else {}
            
            # Prepare request data
            request_data = {
                "model": kwargs.get('model_name', self.model_name),
                "messages": messages,
                "stream": stream,
                "temperature": kwargs.get('temperature', model_params.get('temperature', self.temperature)),
                "max_tokens": kwargs.get('max_tokens', model_params.get('max_tokens', self.max_tokens)),
                "top_p": kwargs.get('top_p', model_params.get('top_p', 1.0)),
                "frequency_penalty": kwargs.get('frequency_penalty', model_params.get('frequency_penalty', 0)),
                "presence_penalty": kwargs.get('presence_penalty', model_params.get('presence_penalty', 0))
            }
            
            # Add provider routing if specified
            if kwargs.get('provider_order'):
                request_data["provider"] = {
                    "order": kwargs['provider_order'],
                    "allow_fallbacks": kwargs.get('allow_fallbacks', True)
                }
            
            # Add required parameters if specified
            if kwargs.get('require_parameters'):
                request_data["provider"] = {
                    "require_parameters": True
                }
            
            # Add response format if specified
            if kwargs.get('response_format'):
                request_data["response_format"] = kwargs['response_format']
            
            # Make request
            response = await self.client.post(
                "/chat/completions",
                json=request_data
            )
            response.raise_for_status()
            
            if stream:
                return self._process_stream(response)
            
            data = response.json()
            
            # Calculate costs
            model_info = self.available_models[self.model_name]
            input_tokens = data['usage']['prompt_tokens']
            output_tokens = data['usage']['completion_tokens']
            input_cost = (input_tokens / 1_000_000) * model_info['input_cost']
            output_cost = (output_tokens / 1_000_000) * model_info['output_cost']
            
            return data['choices'][0]['message']['content'], {
                'usage': {
                    'prompt_tokens': input_tokens,
                    'completion_tokens': output_tokens,
                    'total_tokens': data['usage']['total_tokens']
                },
                'model': data['model'],
                'cost': {
                    'input_cost': input_cost,
                    'output_cost': output_cost,
                    'total_cost': input_cost + output_cost
                },
                'finish_reason': data['choices'][0]['finish_reason']
            }
            
        except Exception as e:
            logger.error(f"OpenRouter completion error: {str(e)}")
            raise
    
    async def _process_stream(self, response) -> AsyncGenerator[str, None]:
        """Process streaming response from OpenRouter."""
        try:
            async for line in response.aiter_lines():
                if line.startswith('data: '):
                    data = json.loads(line[6:])
                    if data.get('choices'):
                        content = data['choices'][0].get('delta', {}).get('content', '')
                        if content:
                            yield content
        except Exception as e:
            logger.error(f"Error processing OpenRouter stream: {str(e)}")
            raise
    
    async def get_embeddings(self, text: str) -> list[float]:
        """Get embeddings using OpenRouter API."""
        try:
            response = await self.client.post("/embeddings", json={
                "model": "openai/text-embedding-3-small",
                "input": text
            })
            response.raise_for_status()
            data = response.json()
            return data['data'][0]['embedding']
        except Exception as e:
            logger.error(f"OpenRouter embeddings error: {str(e)}")
            raise 
    
    async def _fetch_available_models(self) -> Dict[str, dict]:
        """Fetch available models from OpenRouter API."""
        try:
            response = await self.client.get("/models")
            response.raise_for_status()
            data = response.json()
            
            models = {}
            for model in data:
                model_id = model['id']
                
                # Get pricing info
                pricing = model.get('pricing', {})
                input_cost = pricing.get('prompt', 0.0) * 1_000_000  # Convert to per million tokens
                output_cost = pricing.get('completion', 0.0) * 1_000_000  # Convert to per million tokens
                
                # Get context window info
                context_length = model.get('context_length', 4096)
                max_completion_tokens = model.get('max_completion_tokens', min(4096, context_length))
                
                # Get model capabilities
                supports_vision = model.get('multimodal', False)
                supports_functions = model.get('supports_functions', False)
                supports_json = model.get('format', '').lower() == 'json'
                
                # Get model status
                is_moderated = model.get('moderated', False)
                is_deprecated = model.get('deprecated', False)
                status = 'deprecated' if is_deprecated else ('stable' if is_moderated else 'experimental')
                
                # Build model info
                models[model_id] = {
                    'description': model.get('description', f"OpenRouter model: {model_id}"),
                    'input_tokens': context_length,
                    'output_tokens': max_completion_tokens,
                    'input_cost': input_cost,
                    'output_cost': output_cost,
                    'supports_vision': supports_vision,
                    'supports_json': supports_json,
                    'supports_functions': supports_functions,
                    'status': status,
                    'default_parameters': {
                        'temperature': model.get('default_temperature', 0.7),
                        'top_p': model.get('default_top_p', 0.95),
                        'top_k': model.get('default_top_k'),
                        'frequency_penalty': model.get('default_frequency_penalty', 0),
                        'presence_penalty': model.get('default_presence_penalty', 0)
                    },
                    'system_info': {
                        'id': model_id,
                        'provider': model.get('provider', {}).get('name'),
                        'architecture': model.get('architecture'),
                        'format': model.get('format'),
                        'created': model.get('created'),
                        'updated': model.get('updated'),
                        'status': status,
                        'context_length': context_length,
                        'max_completion_tokens': max_completion_tokens,
                        'moderated': is_moderated,
                        'deprecated': is_deprecated,
                        'pricing': {
                            'prompt': input_cost,
                            'completion': output_cost,
                            'currency': pricing.get('currency', 'USD')
                        }
                    }
                }
            
            # If no models found, return default set
            if not models:
                return {
                    'openai/gpt-3.5-turbo': {
                        'description': 'OpenAI GPT-3.5 Turbo via OpenRouter',
                        'input_tokens': 16385,
                        'output_tokens': 4096,
                        'input_cost': 0.5,
                        'output_cost': 1.5,
                        'supports_vision': False,
                        'supports_json': True,
                        'supports_functions': True,
                        'status': 'stable',
                        'default_parameters': {
                            'temperature': 0.7,
                            'top_p': 0.95,
                            'frequency_penalty': 0,
                            'presence_penalty': 0
                        }
                    }
                }
            
            return models
            
        except Exception as e:
            logger.error(f"Error fetching OpenRouter models: {str(e)}")
            # Return a minimal set of known models as fallback
            return {
                'openai/gpt-3.5-turbo': {
                    'description': 'OpenAI GPT-3.5 Turbo via OpenRouter',
                    'input_tokens': 16385,
                    'output_tokens': 4096,
                    'input_cost': 0.5,
                    'output_cost': 1.5,
                    'supports_vision': False,
                    'supports_json': True,
                    'supports_functions': True,
                    'status': 'stable',
                    'default_parameters': {
                        'temperature': 0.7,
                        'top_p': 0.95,
                        'frequency_penalty': 0,
                        'presence_penalty': 0
                    }
                }
            } 