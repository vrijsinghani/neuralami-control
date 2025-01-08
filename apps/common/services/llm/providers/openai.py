"""OpenAI API provider implementation."""

import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple, Union
from openai import AsyncOpenAI
import httpx

from django.conf import settings
from apps.common.models import LLMConfiguration
from .base import BaseLLMProvider

logger = logging.getLogger(__name__)

class OpenAIProvider(BaseLLMProvider):
    """Direct OpenAI API provider."""
    
    def __init__(self, config: LLMConfiguration):
        """Initialize OpenAI provider with configuration."""
        super().__init__(config)
        
        # Get provider settings
        self.api_base = config.api_base_url
        self.api_version = config.api_version
        self.max_retries = config.max_retries
        
        # Initialize client with proper settings
        self.client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=self.api_base or "https://api.openai.com/v1",
            max_retries=self.max_retries,
            timeout=httpx.Timeout(config.timeout)
        )
        
        # Get model parameters
        model_params = config.get_model_parameters()
        self.temperature = model_params.get('temperature', 0.7)
        self.max_tokens = model_params.get('max_tokens', 1000)
        
        # Set default model if not specified
        self.model_name = config.default_model or 'gpt-3.5-turbo'
        
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
                logger.warning(f"Model {self.model_name} not found, falling back to gpt-3.5-turbo")
                self.model_name = 'gpt-3.5-turbo'
            
            # Update max tokens based on model limits
            self.max_tokens = min(
                self.max_tokens,
                self.available_models[self.model_name]['output_tokens']
            )
            
            if self._cache_config['enable_model_cache']:
                # TODO: Cache the models
                pass
                
        except Exception as e:
            logger.error(f"Error initializing OpenAI provider: {str(e)}")
            raise
    
    async def get_completion(
        self,
        messages: list,
        stream: bool = False,
        **kwargs
    ) -> Union[Tuple[str, dict], AsyncGenerator[Any, None]]:
        """Get completion using OpenAI API."""
        try:
            # Get model parameters with overrides
            model_params = self.config.get_model_parameters(
                kwargs.get('model_name', self.model_name)
            )
            
            # Get streaming config if needed
            stream_config = self._streaming_config if stream else {}
            
            response = await self.client.chat.completions.create(
                model=kwargs.get('model_name', self.model_name),
                messages=[{
                    'role': msg.get('role', 'user'),
                    'content': msg.get('content', '')
                } for msg in messages],
                temperature=kwargs.get('temperature', model_params.get('temperature', self.temperature)),
                stream=stream,
                max_tokens=kwargs.get('max_tokens', model_params.get('max_tokens', self.max_tokens)),
                top_p=kwargs.get('top_p', model_params.get('top_p', 1.0)),
                presence_penalty=kwargs.get('presence_penalty', model_params.get('presence_penalty', 0)),
                frequency_penalty=kwargs.get('frequency_penalty', model_params.get('frequency_penalty', 0)),
                response_format=kwargs.get('response_format'),
                tools=kwargs.get('tools'),
                tool_choice=kwargs.get('tool_choice')
            )
            
            if stream:
                return response
            
            # Calculate costs
            model_info = self.available_models[self.model_name]
            input_cost = (response.usage.prompt_tokens / 1_000_000) * model_info['input_cost']
            output_cost = (response.usage.completion_tokens / 1_000_000) * model_info['output_cost']
            
            return response.choices[0].message.content, {
                'usage': {
                    'prompt_tokens': response.usage.prompt_tokens,
                    'completion_tokens': response.usage.completion_tokens,
                    'total_tokens': response.usage.total_tokens
                },
                'model': response.model,
                'cost': {
                    'input_cost': input_cost,
                    'output_cost': output_cost,
                    'total_cost': input_cost + output_cost
                },
                'finish_reason': response.choices[0].finish_reason,
                'tool_calls': response.choices[0].message.tool_calls if hasattr(response.choices[0].message, 'tool_calls') else None
            }
            
        except Exception as e:
            logger.error(f"OpenAI completion error: {str(e)}")
            raise
    
    async def get_embeddings(self, text: str) -> list[float]:
        """Get embeddings using OpenAI API."""
        try:
            response = await self.client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"OpenAI embeddings error: {str(e)}")
            raise 
    
    async def _fetch_available_models(self) -> Dict[str, dict]:
        """Fetch available models from OpenAI API."""
        try:
            response = await self.client.models.list()
            
            models = {}
            for model in response.data:
                model_id = model.id
                
                # Skip non-chat and non-embedding models
                if not (model_id.startswith('gpt-') or model_id.startswith('text-embedding-')):
                    continue
                
                # Determine model capabilities and pricing tiers
                is_gpt4 = 'gpt-4' in model_id
                is_gpt4_turbo = 'gpt-4-turbo' in model_id
                is_gpt4_vision = 'vision' in model_id
                is_gpt35 = 'gpt-3.5' in model_id
                is_embedding = 'embedding' in model_id
                is_preview = 'preview' in model_id
                
                if is_embedding:
                    # Embedding models
                    is_large = 'large' in model_id
                    models[model_id] = {
                        'description': f"OpenAI embedding model: {model_id}",
                        'input_tokens': 8191,
                        'output_dimension': 3072 if is_large else 1536,
                        'input_cost': 0.13 if is_large else 0.02,
                        'supports_batch': True,
                        'status': 'stable',
                        'system_info': {
                            'id': model.id,
                            'created': model.created,
                            'owned_by': model.owned_by
                        }
                    }
                else:
                    # Chat models
                    if is_gpt4_turbo:
                        input_cost = 10.0
                        output_cost = 30.0
                        context_window = 128000
                    elif is_gpt4:
                        input_cost = 30.0
                        output_cost = 60.0
                        context_window = 32768 if is_preview else 8192
                    else:  # GPT-3.5
                        input_cost = 0.5
                        output_cost = 1.5
                        context_window = 16385
                    
                    models[model_id] = {
                        'description': f"OpenAI {'GPT-4' if is_gpt4 else 'GPT-3.5'} model",
                        'input_tokens': context_window,
                        'output_tokens': 4096,
                        'input_cost': input_cost,
                        'output_cost': output_cost,
                        'supports_vision': is_gpt4_vision,
                        'supports_json': True,
                        'supports_functions': True,
                        'status': 'preview' if is_preview else 'stable',
                        'default_parameters': {
                            'temperature': 0.7,
                            'top_p': 0.95,
                            'frequency_penalty': 0,
                            'presence_penalty': 0
                        },
                        'system_info': {
                            'id': model.id,
                            'created': model.created,
                            'owned_by': model.owned_by
                        }
                    }
            
            # If no models found, return default set
            if not models:
                return {
                    'gpt-3.5-turbo': {
                        'description': 'OpenAI GPT-3.5 model',
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
            logger.error(f"Error fetching OpenAI models: {str(e)}")
            # Return a minimal set of known models as fallback
            return {
                'gpt-3.5-turbo': {
                    'description': 'OpenAI GPT-3.5 model',
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